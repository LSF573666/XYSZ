from multiprocessing.pool import AsyncResult
import time
import os, csv
import traceback
from celery import shared_task
from celery.signals import worker_ready

from django.conf import settings
from django.http import HttpResponse
import pandas as pd
from datetime import datetime
from django.core.cache import cache
import numpy as np
from xysz.config import get_api_balance
from xysz.env.Strategy import calculate_ema, define_KC_samtrstrategy, define_KC_strategy, define_KC_smartstrategy, define_grid_strategy, calculate_vi_manual, df_Martin_strategy, df_MoneyToad_strategy, df_ferry_strategy
from xysz.env.MockAccount import MockAccount
import aiohttp
import asyncio

from asgiref.sync import sync_to_async
import nest_asyncio

# Ferry 用 period=480 + atr=14，至少需要 494 根；统一拉 500+
KLINE_LIMIT = 500
OKX_KLINE_LIMIT = 300  # OKX 单次最多 300，需分页凑满
BINANCE_FUTURES_KLINES_URL = 'https://fapi.binance.com/fapi/v1/klines'
OKX_CANDLES_URL = 'https://www.okx.com/api/v5/market/candles'
OKX_HISTORY_CANDLES_URL = 'https://www.okx.com/api/v5/market/history-candles'
OKX_INTERVAL_MAP = {
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '1h': '1H',
}

nest_asyncio.apply()

last_strategy_signal = None
last_processed_time = None
buy_close_price = None
result = None   # 用于记录上
has_traded_in_block = False
KLRT_side = {}
stop_five_transaction = False
strategy_result = None
balance = get_api_balance()

# 清理价格数据
def clean_price(price_str):
    return price_str.replace('$', '').replace(' 附近', '').replace('附近', '').strip()

def process_kline_data(exchange, symbol, interval, data):
    """
    处理不同交易所的K线数据，标准化为统一格式
    
    参数:
        exchange: 交易所名称 (bitget, okx, binance)
        symbol: 交易对 (btc, eth等)
        interval: K线间隔 (1m, 5m, 15m, 1h)
        data: 原始K线数据
        
    返回:
        pd.DataFrame: 标准化后的K线数据
    """
    # 定义时间间隔对应的秒数和分钟数
    interval_mapping = {
        '1m': {'seconds': 60, 'minutes': 1},
        '5m': {'seconds': 300, 'minutes': 5},
        '15m': {'seconds': 900, 'minutes': 15},
        '1h': {'seconds': 3600, 'minutes': 60}
    }
    
    time_params = interval_mapping.get(interval, {'seconds': 60, 'minutes': 1})
    
    try:
        if exchange == 'okx':
            # 处理OKX数据格式
            klines = data['data'] if 'data' in data else []
            df = pd.DataFrame(
                klines,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                         'volCcy', 'volCcyQuote', 'confirm']
            )
            # 只保留需要的列
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            # print(klines)
            # print(df)

            
        elif exchange == 'bitget':
            # 处理Bitget数据格式 - 修正版
            if isinstance(data, list) and len(data) > 0:
                # 检查数据格式：如果是字符串列表
                if isinstance(data[0], list) and isinstance(data[0][0], str):
                    df = pd.DataFrame(
                        data,
                        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy']
                    )
                else:
                    # 如果是其他格式，尝试直接创建DataFrame
                    df = pd.DataFrame(data)
                    # 确保有足够的列
                    if len(df.columns) >= 6:
                        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
                    else:
                        raise ValueError(f"Bitget数据列数不足: {len(df.columns)}")
            else:
                raise ValueError(f"Bitget数据格式异常: {type(data)}")
            
        elif exchange == 'binance':
            # 处理Binance数据格式
            df = pd.DataFrame(
                data,
                columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades',
                    'taker_buy_base', 'taker_buy_quote', 'ignore'
                ]
            )
            # 只保留需要的列
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
        
        # 转换数据类型
        df['timestamp'] = df['timestamp'].astype('int64')
        df['open'] = df['open'].astype('float64')
        df['high'] = df['high'].astype('float64')
        df['low'] = df['low'].astype('float64')
        df['close'] = df['close'].astype('float64')
        df['volume'] = df['volume'].astype('float64')
        
        # 排序并重置索引
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 转换时间戳为可读格式
        df['timestamp'] = df['timestamp'].apply(
            lambda x: datetime.fromtimestamp(x/1000).strftime('%Y-%m-%d %H:%M:%S')
        )
        if df.empty:
            raise ValueError(f"{exchange}, {symbol}, {interval}处理后数据为空")
        return df, time_params
    
    except Exception as e:
        print(f"处理{exchange}数据时出错: {str(e)}")
        return pd.DataFrame(), time_params

@shared_task(bind=True, max_retries=3)
def FB_strategy(self, exchange, symbol, interval, data, label):
    try:
        df, time_params = process_kline_data(exchange, symbol, interval, data)
        # time = time_params['seconds']      # 获取秒数 → 300
        # timelevel = time_params['minutes']      # 获取分钟数 → 5

        last_timestamp = df['timestamp'].iloc[-1]
        symbol = symbol.upper()
        exchange = exchange.upper()

        # 修复：使用统一的缓存键命名，移除interval部分
        cache_key_1m = f"fb_{exchange}_{symbol}_1m_data"  # 移除_{interval}
        cache_key_15m = f"fb_{exchange}_{symbol}_15m_data"  # 移除_{interval}
        cache_key_lock = f"fb_{exchange}_{symbol}_lock"
        cache_key_processed = f"fb_{exchange}_{symbol}_{last_timestamp}"
        if df.empty:
            return
        # 检查是否已处理过
        if cache.get(cache_key_processed):
            return {"status": "skipped", "reason": "already_processed"}

        # 存储数据到缓存
        if interval == '1m':
            cache.set(cache_key_1m, {'data': df, 'timestamp': last_timestamp}, timeout=20)  # 延长超时时间
            # print(f"存储1m数据: {symbol}, 时间: {last_timestamp}")
        elif interval == '15m':
            cache.set(cache_key_15m, {'data': df, 'timestamp': last_timestamp}, timeout=20)  # 延长超时时间
            # print(f"存储15m数据: {symbol}, 时间: {last_timestamp}")
        else:
            return {"status": "skipped", "reason": "unsupported_interval"}

        # 检查两个时间框架的数据是否都可用
        data_1m = cache.get(cache_key_1m)
        data_15m = cache.get(cache_key_15m)
        
        # print(f"FB策略数据检查: {symbol}, 1m_exists={bool(data_1m)}, 15m_exists={bool(data_15m)}")
        
        if data_1m and data_15m:
            # print(f"数据完整，准备处理: {symbol}")
            
            # 获取分布式锁
            if not cache.add(cache_key_lock, True, timeout=20):
                # print(f"等待锁释放: {symbol}")
                self.retry(countdown=2, max_retries=3)
                return {"status": "retrying", "reason": "lock_not_acquired"}

            try:
                # 再次检查数据
                data_1m = cache.get(cache_key_1m)
                data_15m = cache.get(cache_key_15m)
                
                if not data_1m or not data_15m:
                    # print(f"数据在获取锁后已过期: {symbol}")
                    return {"status": "waiting", "reason": "data_expired_after_lock"}

                fast_data = data_1m['data']
                middle_data = data_15m['data']
                
                # print(f"开始执行FB策略: {symbol}, 1m数据: {len(fast_data)}, 15m数据: {len(middle_data)}")
                
                FB_key = 2 
                strategy_result = define_grid_strategy(exchange, symbol, fast_data, middle_data, FB_key)
                
                # 标记为已处理
                cache.set(cache_key_processed, True, timeout=20)
                # print(f"FB策略完成: {symbol}, 结果: {strategy_result}")
                
                # 清理缓存数据，避免重复处理
                cache.delete(cache_key_1m)
                cache.delete(cache_key_15m)
                
                return {"status": "success", "result": strategy_result}
                
            finally:
                cache.delete(cache_key_lock)
        else:
            # print(f"等待另一个时间框架数据: {symbol}, 当前收到: {interval}")
            return {"status": "waiting", "reason": "incomplete_data"}
            
    except Exception as e:
        print(f"FB_task报错_{exchange}_{symbol}, {e}")
        if '锁' in str(e):
            self.retry(countdown=3)
        return {"status": "error", "message": str(e)}

@shared_task(bind=True)
def KC_strategy(self, exchange, symbol, interval, data, label):
    global has_traded_in_block,account
    try:
        fast_data, time_params = process_kline_data(exchange, symbol, interval, data)
        time = time_params['seconds']      # 获取秒数 → 300
        timelevel = time_params['minutes']      # 获取分钟数 → 5

        # print(type(fast_data))
        # print(fast_data.iloc[-1])
        # print(fast_data['timestamp'].iloc[-1])
        exchange = exchange.upper()
        symbol = symbol.upper()

        plan = "KC"
        if fast_data.empty:
            return
        cache_key = f"kcline_{exchange}_{symbol}_{timelevel}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        kc_grid = 3
        result = define_KC_strategy(exchange, symbol, time, fast_data, kc_grid)
        if not isinstance(result, tuple):
            return f"KC_strategy_{exchange}_{symbol}跳过"
        exchange, adx_value = result

        return f"KC_strategy_{exchange}_{symbol}完成"

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"KC_task_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg
    
@shared_task(bind=True)
def KC_smartstrategy(self, exchange, symbol, interval, data, label):
    global has_traded_in_block,account
    try:
        fast_data, time_params = process_kline_data(exchange, symbol, interval, data)
        time = time_params['seconds']      # 获取秒数 → 300
        timelevel = time_params['minutes']      # 获取分钟数 → 5

        # print(type(fast_data))
        # print(fast_data)
        exchange = exchange.upper()
        symbol = symbol.upper()
        plan = "kc_smart"
        if fast_data.empty:
            return
        cache_key = f"kcsmartline_{exchange}_{symbol}_{timelevel}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        kc_grid = 4
        
        result = define_KC_smartstrategy(exchange, symbol, time, fast_data, kc_grid)
        if not isinstance(result, tuple):
            return f"KC_smart_{exchange}_{symbol}跳过"
        exchange, adx_value = result

        return f"KC_smart_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"KC_smarttask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg

@shared_task(bind=True)
def KC_samtrstrategy(self, exchange, symbol, interval, data, label):
    global has_traded_in_block,account
    try:
        fast_data, time_params = process_kline_data(exchange, symbol, interval, data)
        time = time_params['seconds']      # 获取秒数 → 300
        timelevel = time_params['minutes']      # 获取分钟数 → 5

        # print(type(fast_data))
        # print(fast_data)
        exchange = exchange.upper()
        symbol = symbol.upper()
        plan = "KC_samtr"
        if fast_data.empty:
            return
        cache_key = f"kcsamtrline_{exchange}_{symbol}_{timelevel}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        kc_sa = 6
        
        exchange, adx_value = define_KC_samtrstrategy(exchange, symbol, time, fast_data, kc_sa)
    
        return f"KC_samtr_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"KC_samtrtask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg

@shared_task(bind=True)
def Ferrystrategy(self, exchange, symbol, interval, data, label):
    global has_traded_in_block,account
    try:
        if interval not in ['5m', '1m']:
            return
        fast_data, time_params = process_kline_data(exchange, symbol, interval, data)
        time = time_params['seconds']      # 获取秒数 → 300
        timelevel = time_params['minutes']      # 获取分钟数 → 5
        # print(type(fast_data))
        # print(len(fast_data))
        # print(fast_data)
        exchange = exchange.upper()
        symbol = symbol.upper()
        plan = "Ferry"
        if fast_data.empty:
            return
        cache_key = f"Ferryline_{exchange}_{symbol}_{timelevel}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        Ferryv = 5

        # side, mode = None, None
        if timelevel == 1 :
            period=200
        elif timelevel == 5 :
            period=200

        df_ferry_strategy(exchange, plan, symbol, time, fast_data, Ferryv, period)
        
            # execute_sell_action(result, symbol, buy_date, close1, pv=kc_grid)
            # execute_buy_action(result, symbol, buy_date, close1, pv=kc_grid)
        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        return f"Ferry_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"Ferrytask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg


@shared_task(bind=True)
def MoneyToadtrategy(self, exchange, symbol, interval, data, label):
    global has_traded_in_block
    try:
        # print(接收到"exchange, symbol, interval")
        if symbol != 'eth':
            return
        if interval not in ['5m', '1m', '15m']:
            return
        fast_data, time_params = process_kline_data(exchange, symbol, interval, data)
        time = time_params['seconds']      # 获取秒数 → 300
        timelevel = time_params['minutes']      # 获取分钟数 → 5
        # print(type(fast_data))
        # print(len(fast_data))
        # print(fast_data)
        exchange = exchange.upper()
        symbol = symbol.upper()
        plan = "MoneyToad"
        if fast_data.empty:
            return
        cache_key = f"MoneyToadline_{exchange}_{symbol}_{timelevel}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        MoneyToadv = 8

        df_MoneyToad_strategy(exchange, plan, symbol, time, fast_data, MoneyToadv)
        
        return f"MoneyToad_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"MoneyToadvtask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg
    

@shared_task(bind=True)
def Martinstrategy(self, exchange, symbol, interval, data, label):
    global has_traded_in_block
    try:
        if interval not in ['5m', '1m', '15m']:
            return

        fast_data, time_params = process_kline_data(exchange, symbol, interval, data)
        time = time_params['seconds']
        timelevel = time_params['minutes']
        exchange = exchange.upper()
        symbol = symbol.upper()
        plan = "Martin"
        if fast_data.empty:
            return
        cache_key = f"Martin_{exchange}_{symbol}_{timelevel}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            return
        Martinv = 9

        df_Martin_strategy(exchange, plan, symbol, time, fast_data, Martinv)
        cache.set(cache_key, 1, timeout=max(time, 60))
        return f"Martin_{exchange}_{symbol}完成 "

    except Exception as e:
        error_msg = f"Martintask_{exchange}_{symbol}报错: {str(e)}"
        return error_msg

# @shared_task(bind=True)
# def CashCowstrategy(self, data):
#     try:
#         plan = "CashCow"
#         # print(f"{plan}接收到数据: {data}")
#         trading_s = data['15分钟价格预测']['交易策略']
#         timestamp = data['时间戳']  # '2025-11-26T16:02:23.073708'

#         # 转换为 datetime 对象
#         dt = datetime.fromisoformat(timestamp)

#         # 转换成 14:55 格式
#         time_str = dt.strftime('%H:%M')
#         time = 900
#         symbol = "ETH"
#         exchange = "BINANCE"
    
#         # print("=== 交易策略分析 ===")
#         print(f"主要策略: {trading_s['主要策略']}")
#         print(f"做单方向: {trading_s['做单方向']}")
#         print(f"入场区域: {trading_s['入场区域']}")
#         print(f"目标价位: {trading_s['目标价位']}")
#         print(f"激进目标: {trading_s['激进目标']}")
#         print(f"止损建议: {trading_s['止损建议']}")
#         print(f"持仓时间: {trading_s['持仓时间']}")
#         print(f"风险级别: {trading_s['风险级别']}")

        

#         if trading_s['主要策略'] == '趋势跟随':
#             mode = 1
#         elif trading_s['主要策略'] == '区间':
#             mode = 2

#         if trading_s['做单方向'] == '做多':
#             side = "OPEN_LONG"
#         elif trading_s['做单方向'] == '做空':
#             side = "OPEN_SHORT"

#         price = clean_price(trading_s['入场区域'])
#         tpPrice = clean_price(trading_s['目标价位'])
#         slPrice = clean_price(trading_s['止损建议'])

#         # 风险级别判断
#         if trading_s['风险级别'] == '较高':
#             print("⚠️ 风险提示：高风险交易，请控制仓位")
#         elif trading_s['风险级别'] == '中等':
#             print("🚨 风险提示：极高风险，建议轻仓或观望")
#         # elif trading_s['风险级别'] == '低':
#             # 震荡区不做单
#             # print("ℹ️ 风险提示：中等风险，正常仓位")

#         if mode == 1 :
#             base_key = f"{exchange}_{plan}_{symbol}_{time}"
#             full_key = f"{base_key}_{plan}_{mode}_{side}_{price}_{tpPrice}_{slPrice}"
#             current_params = f"{plan}_{mode}_{side}_{price}_{tpPrice}_{slPrice}"

#             # 获取缓存中的历史记录（只存储最新的一条）
#             last_params = cache.get(base_key)

#             # print(fast_atr)
#             # log_message = f"KCsamtr{exchange}_{symbol}_{time}_{signal_time},中轨2:{Medium_2},中轨1:{Medium_track},close2:{close2},close1:{close1},adx:{adx_last},atr:{current_atr}"
#             # print(log_message)

#             # CSV文件路径
#             today = datetime.now().date()
#             # csv_file = f"./kcsamtrsignal{today}_{time}.csv"

#             if last_params is None:
#                 # 首次发送信号，并存储参数组合
#                 set_result = True
#                 if set_result:
#                     # 存储新记录
#                     cache.set(base_key, current_params, timeout=30)
#             else:
#                 if last_params != current_params:
#                     # print(f"震荡趋势有变化")
#                     set_result = True
#                     if set_result:
#                         # 更新记录
#                         cache.set(base_key, current_params, timeout=30)

#         return f"CashCow_{exchange}_{symbol}完成 "
#     except Exception as e:
#         # 返回简单的字符串而不是复杂的字典
#         error_msg = f"CashCowtask_{exchange}_{symbol}报错: {str(e)}"
#         # print(error_msg)  # 记录错误日志
#         return error_msg


async def fetch_exchange_klines(session, exchange, symbol, interval):
    """
    直接从交易所拉取K线，返回 process_kline_data 可解析的原始格式。
    - binance: list[list]（U本位合约）
    - okx: {"data": list[list]}（USDT永续 SWAP）
    """
    exchange = exchange.lower()
    symbol = symbol.lower()
    interval = interval.lower()

    try:
        if exchange == 'binance':
            params = {
                'symbol': f'{symbol.upper()}USDT',
                'interval': interval,
                'limit': KLINE_LIMIT,
            }
            async with session.get(
                BINANCE_FUTURES_KLINES_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f'HTTP {resp.status}: {text[:200]}')
                data = await resp.json()
                if not isinstance(data, list) or not data:
                    raise ValueError(f'空数据或格式异常: {type(data)}')
                return data

        if exchange == 'okx':
            bar = OKX_INTERVAL_MAP.get(interval)
            if not bar:
                raise ValueError(f'不支持的OKX周期: {interval}')
            inst_id = f'{symbol.upper()}-USDT-SWAP'
            # OKX 单次最多 300，分页拉取直到凑满策略所需根数
            collected = []
            after_ts = None
            pages = 0
            max_pages = (KLINE_LIMIT + OKX_KLINE_LIMIT - 1) // OKX_KLINE_LIMIT + 1
            while len(collected) < KLINE_LIMIT and pages < max_pages:
                params = {
                    'instId': inst_id,
                    'bar': bar,
                    'limit': str(OKX_KLINE_LIMIT),
                }
                # 首页用最新 candles；更早数据用 history-candles + after
                if after_ts is None:
                    url = OKX_CANDLES_URL
                else:
                    url = OKX_HISTORY_CANDLES_URL
                    params['after'] = str(after_ts)

                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise ValueError(f'HTTP {resp.status}: {text[:200]}')
                    payload = await resp.json()
                    if str(payload.get('code', '')) != '0':
                        raise ValueError(f"OKX错误: {payload.get('msg') or payload}")
                    batch = payload.get('data') or []

                pages += 1
                if not batch:
                    break
                collected.extend(batch)
                # OKX 按时间倒序返回，最后一条是本页最旧
                after_ts = batch[-1][0]
                if len(batch) < OKX_KLINE_LIMIT:
                    break

            if not collected:
                raise ValueError('OKX返回空K线')

            # 按时间戳去重，保持倒序（process_kline_data 会再升序排序）
            dedup = {}
            for row in collected:
                dedup[str(row[0])] = row
            candles = sorted(dedup.values(), key=lambda x: int(x[0]), reverse=True)
            if len(candles) < 494:
                print(f"警告: OKX {symbol}/{interval} 仅拿到 {len(candles)} 根，Ferry 可能仍不足")
            return {'data': candles}

        raise ValueError(f'不支持的交易所: {exchange}')
    except Exception as e:
        print(f"拉取K线失败 {exchange}/{symbol}/{interval}: {e}")
        return None


async def fetch_and_distribute_exchange_data():
    """从币安/欧意拉取K线并分发给策略任务（替代原 Redis 取数）。"""
    target_exchanges = ('binance', 'okx')
    target_symbols = ('btc', 'eth')
    # Ferry: 1m/5m；MoneyToad: 1m/5m/15m；保留 1h 供其他策略启用
    target_intervals = ('1m', '5m', '15m', '1h')
    label = None  # 合约行情

    start_time = time.time()
    total_tasks = 0
    successful_tasks = 0
    fetch_ok = 0
    fetch_fail = 0

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            fetch_jobs = [
                (exchange, symbol, interval, fetch_exchange_klines(session, exchange, symbol, interval))
                for exchange in target_exchanges
                for symbol in target_symbols
                for interval in target_intervals
            ]
            results = await asyncio.gather(
                *(job[3] for job in fetch_jobs),
                return_exceptions=True,
            )

        tasks_to_dispatch = []
        for (exchange, symbol, interval, _), result in zip(fetch_jobs, results):
            if isinstance(result, Exception):
                fetch_fail += 1
                print(f"拉取异常 {exchange}/{symbol}/{interval}: {result}")
                continue
            if result is None:
                fetch_fail += 1
                continue
            fetch_ok += 1
            tasks_to_dispatch.append({
                'exchange': exchange,
                'symbol': symbol,
                'interval': interval,
                'data': result,
                'label': label,
            })

        print(f"交易所拉取完成: 成功 {fetch_ok}, 失败 {fetch_fail}, 待分发 {len(tasks_to_dispatch)}")

        for task_info in tasks_to_dispatch:
            exchange = task_info['exchange']
            symbol = task_info['symbol']
            interval = task_info['interval']
            args = (exchange, symbol, interval, task_info['data'], task_info['label'])
            try:
                # 只分发各策略支持的周期/币种，避免一堆 succeeded: None / unsupported_interval 日志
                if interval in ('1m', '15m'):
                    FB_strategy.delay(*args)
                    total_tasks += 1
                KC_strategy.delay(*args)
                total_tasks += 1
                KC_smartstrategy.delay(*args)
                total_tasks += 1
                if interval in ('1m', '5m'):
                    Ferrystrategy.delay(*args)
                    total_tasks += 1
                if symbol.lower() == 'eth' and interval in ('1m', '5m', '15m'):
                    MoneyToadtrategy.delay(*args)
                    total_tasks += 1
                if interval in ('1m', '5m', '15m'):
                    Martinstrategy.delay(*args)
                    total_tasks += 1
                successful_tasks += 1
            except Exception as e:
                print(f"分发任务失败: {exchange}/{symbol}/{interval} - {e}")

        duration = time.time() - start_time
        print(f"总任务: {total_tasks}, 成功: {successful_tasks}, 耗时: {duration:.2f}s")
        return {
            'total_tasks': total_tasks,
            'successful_tasks': successful_tasks,
            'fetch_ok': fetch_ok,
            'fetch_fail': fetch_fail,
            'duration': round(duration, 2),
        }
    except Exception as e:
        print(f"交易所取数错误: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc()
        }


@shared_task(bind=True, time_limit=60, soft_time_limit=55)
def fetch_klines_task(self):
    try:
        result = asyncio.run(fetch_and_distribute_exchange_data())
        return {"status": "success", "data": result}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# Worker 就绪后立刻拉一次，之后由 Celery Beat 每 20 秒继续调度（无需浏览器手动触发）
@worker_ready.connect
def _autofetch_on_worker_ready(sender=None, **kwargs):
    try:
        async_result = fetch_klines_task.delay()
        print(f"[auto] Celery Worker 已就绪，已自动触发 fetch_klines_task id={async_result.id}")
    except Exception as e:
        print(f"[auto] 自动触发 fetch_klines_task 失败: {e}")
