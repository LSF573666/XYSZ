import json
from multiprocessing.pool import AsyncResult
import time
import os, csv
import traceback
from celery import shared_task

import redis
from django.conf import settings
from django.http import HttpResponse
import pandas as pd
from datetime import datetime
from django.core.cache import cache
import numpy as np
from redis.asyncio import Redis
from xysz.config import get_api_balance
from xysz.env.BacktestEnv import calculate_ema, define_KC_samtrstrategy, define_KC_strategy, define_KC_smartstrategy, define_grid_strategy
from xysz.env.MockAccount import MockAccount
# import aiohttp
import asyncio
from xysz.tests import send_mode_signal

# from asgiref.sync import sync_to_async
# import nest_asyncio
# nest_asyncio.apply()

last_strategy_signal = None
last_processed_time = None
buy_close_price = None
result = None   # 用于记录上
has_traded_in_block = False
KLRT_side = {}
stop_five_transaction = False
strategy_result = None
balance = get_api_balance()
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
            if isinstance(data, list):
                df = pd.DataFrame(
                    data,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy']
                )
            
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
def FB_strategy(self, exchange, symbol, interval, data):
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
def KC_strategy(self, exchange, symbol, interval, data):
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
        exchange, adx_value = define_KC_strategy(exchange, symbol, time, fast_data, kc_grid)

        # last_row = fast_data.iloc[-1]
        # buy_date = last_row['timestamp']
        # close1 = last_row['close']
        # # prev_row = slow_his_data.iloc[-2]
        # # close2 = prev_row['close']
        # current_time = pd.to_datetime(buy_date)
        # current_minute = current_time.minute
        # current_hour = current_time.hour
        # total_minutes = current_hour * 60 + current_minute
        # strategy_now = ((total_minutes - 1) // timelevel) * timelevel 
        # # print(strategy_result)
        # # five_key = f"KC_{symbol}_{five_now}"
        # strategy_key = f"KC_{exchange}_{symbol}_{timelevel}_{strategy_now}"
        # if strategy_key not in cache:
        #     has_traded_in_block = False  # 重置交易标志
        #     # adx_value = 27
        #     if 25 < adx_value <= 30:
        #         account = MockAccount(initial_balance=balance)
        #         position_info = account.get_strategy_positions(strategy=plan, exchange=exchange, symbol=symbol)
        #         position_data = position_info.get(exchange, {}).get(symbol)
        #         if position_data:
        #             # entry_price = float(position_data.get("entry_price", 0))
        #             buy_side = position_data.get("position_side")
        #             if 25 < adx_value <= 30:
        #                 if buy_side == 2:
        #                     result = 1
        #                     execute_sell_action(result, exchange, symbol, time, buy_date, close1, grid=kc_grid)
        #                     has_traded_in_block = True 
        #                     cache.set(strategy_key, True, timeout=time)
        #                 elif buy_side == 1:
        #                     result = 2
        #                     execute_sell_action(result, exchange, symbol, time, buy_date, close1, grid=kc_grid)
        #                     has_traded_in_block = True 
        #                     cache.set(strategy_key, True, timeout=time)
            # result = 2
            # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
            # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        return f"KC_strategy_{exchange}_{symbol}完成"

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"KC_task_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg
    
@shared_task(bind=True)
def KC_smartstrategy(self, exchange, symbol, interval, data):
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
        
        exchange, adx_value = define_KC_smartstrategy(exchange, symbol, time, fast_data, kc_grid)
        last_row = fast_data.iloc[-1]
        buy_date = last_row['timestamp']
        close1 = last_row['close']
        # print(f"时间戳打印:{exchange}, {symbol}, {interval},{buy_date}")
        # prev_row = slow_his_data.iloc[-2]
        # close2 = prev_row['close']
        # print(f"buy_date 的值是: {buy_date}, 类型是: {type(buy_date)}")

        current_time = pd.to_datetime(buy_date)
        current_minute = current_time.minute
        current_hour = current_time.hour
        total_minutes = current_hour * 60 + current_minute
        five_now = ((total_minutes - 1) // timelevel) * timelevel 
        smartstrategy_key = f"KCsmart_{exchange}_{symbol}_{timelevel}_{five_now}"

        # if smartstrategy_key not in cache:
        #     has_traded_in_block = False  # 重置交易标志
        #     account = MockAccount(initial_balance=balance)
        #     position_info = account.get_strategy_positions(strategy=plan, exchange=exchange, symbol=symbol)
        #     # print(position_info)
        #     position_data = position_info.get(exchange, {}).get(symbol)
        #     # print(position_data)
        #     # adx_value = 27
        #     if position_data:
        #         # entry_price = float(position_data.get("entry_price", 0))
        #         buy_side = position_data.get("position_side")
        #         # print(buy_side)
            
        #         if 25 < adx_value <= 30:
        #             if buy_side == 2:
        #                 result = 1
        #                 execute_sell_action(result, exchange, symbol, time, buy_date, close1, grid=kc_grid)
        #                 has_traded_in_block = True 
        #                 cache.set(smartstrategy_key, True, timeout=time)
        #             elif buy_side == 1:
        #                 result = 2
        #                 execute_sell_action(result, exchange, symbol, time, buy_date, close1, grid=kc_grid)
        #                 has_traded_in_block = True 
        #                 cache.set(smartstrategy_key, True, timeout=time)
            # result = 2
            # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
            # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        return f"KC_smart_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"KC_smarttask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg

@shared_task(bind=True)
def KC_samtrstrategy(self, exchange, symbol, interval, data):
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
        # last_row = fast_data.iloc[-1]
        # buy_date = last_row['timestamp']
        # close1 = last_row['close']
        # # print(f"时间戳打印:{exchange}, {symbol}, {interval},{buy_date}")
        # # prev_row = slow_his_data.iloc[-2]
        # # close2 = prev_row['close']
        # # print(f"buy_date 的值是: {buy_date}, 类型是: {type(buy_date)}")

        # current_time = pd.to_datetime(buy_date)
        # current_minute = current_time.minute
        # current_hour = current_time.hour
        # total_minutes = current_hour * 60 + current_minute
        # five_now = ((total_minutes - 1) // timelevel) * timelevel 
        # smartstrategy_key = f"KCsmart_{exchange}_{symbol}_{timelevel}_{five_now}"

        # if smartstrategy_key not in cache:
        #     has_traded_in_block = False  # 重置交易标志
        #     account = MockAccount(initial_balance=balance)
        #     position_info = account.get_strategy_positions(strategy=plan, exchange=exchange, symbol=symbol)
        #     # print(position_info)
        #     position_data = position_info.get(exchange, {}).get(symbol)
        #     # print(position_data)
        #     # adx_value = 27
        #     if position_data:
        #         # entry_price = float(position_data.get("entry_price", 0))
        #         buy_side = position_data.get("position_side")
        #         # print(buy_side)
            
        #         if 25 < adx_value <= 30:
        #             if buy_side == 2:
        #                 result = 1
        #                 execute_sell_action(result, exchange, symbol, time, buy_date, close1, grid=kc_grid)
        #                 has_traded_in_block = True 
        #                 cache.set(smartstrategy_key, True, timeout=time)
        #             elif buy_side == 1:
        #                 result = 2
        #                 execute_sell_action(result, exchange, symbol, time, buy_date, close1, grid=kc_grid)
        #                 has_traded_in_block = True 
        #                 cache.set(smartstrategy_key, True, timeout=time)
            # result = 2
            # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
            # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        return f"KC_samtr_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"KC_samtrtask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg

@shared_task(bind=True)
def EMA5strategy(self, exchange, symbol, interval, data):
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
        side = None
        if interval == '1m' :
            period=10
        elif interval == '5m' :
            period=5
        ema5_values = calculate_ema(fast_data,period=period)
        last_row = fast_data.iloc[-1]
        last2_row = fast_data.iloc[-2]
        ema5_value1 = ema5_values.iloc[-1]
        ema5_value2 = ema5_values.iloc[-2]
        buy_date = last_row['timestamp']
        close1 = last_row['close']
        close2 = last2_row['close']
        current_date = pd.Timestamp(buy_date)
        dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S")
        formatted_time = dt.strftime("%H:%M")
        # print(ema5_value1,ema5_value2,close1,close2)

        if close2 > ema5_value2 and close1 > ema5_value1 :
            side = 1
        elif close2 < ema5_value2 and close1 < ema5_value1 :
            side = 2

        selltype = 'ALL'

        if side is not None:
            set_result = send_mode_signal(
                    coinPlatform = exchange,
                    coin=symbol,
                    plan=plan,
                    time=time,
                    side=side,
                    mode=1,
                    dpo=1,
                    dpo2=1,
                    tp=1,
                    sl=1,
                    multiple=1,
                    multiple2=1
                )
        
            # execute_sell_action(result, symbol, buy_date, close1, pv=kc_grid)
            # execute_buy_action(result, symbol, buy_date, close1, pv=kc_grid)
        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        return f"Ferry_{exchange}_{symbol}完成 "

    except Exception as e:
        # 返回简单的字符串而不是复杂的字典
        error_msg = f"Ferrytask_{exchange}_{symbol}报错: {str(e)}"
        # print(error_msg)  # 记录错误日志
        return error_msg


@shared_task(bind=True, time_limit=30, soft_time_limit=30)
def fetch_klines_task(self):
    async def fetch_and_distribute_redis_data():
        r = None
        try:
            r = Redis(
                host='47.84.194.2',
                port=6379,
                password='yyz135246',
                db=0,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            await r.ping()
            print("Redis连接成功！")

            target_exchanges = {'bitget', 'binance', 'okx'}
            target_symbols = {'btc', 'eth', 'sol', 'doge', 'xrp'}
            target_intervals = {'1m', '5m', '15m', '1h'}

            start_time = time.time()
            total_tasks = 0
            successful_tasks = 0

            # 异步 SCAN
            cursor = 0
            pattern = "*_data_*_*"
            keys = []

            while True:
                cursor, partial_keys = await r.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(partial_keys)
                if cursor == 0:
                    break

            print(f"找到 {len(keys)} 个符合格式的键")

            tasks_to_dispatch = []
            for key in keys:
                if key.endswith(('setMode', 'lastprice', 'spot')):
                    continue

                parts = key.split('_')
                if len(parts) != 4:
                    continue

                exchange, _, symbol, interval = parts
                exchange, symbol, interval = exchange.lower(), symbol.lower(), interval.lower()

                if (exchange in target_exchanges and
                    symbol in target_symbols and
                    interval in target_intervals):

                    value = await r.get(key)
                    if not value:
                        continue

                    try:
                        data = json.loads(value)
                        tasks_to_dispatch.append({
                            'exchange': exchange,
                            'symbol': symbol,
                            'interval': interval,
                            'data': data
                        })
                    except json.JSONDecodeError:
                        print(f"JSON解析失败: {key}")

            # 批量分发
            for task_info in tasks_to_dispatch:
                total_tasks += 1
                try:
                    # FB_strategy.delay(
                    #     task_info['exchange'],
                    #     task_info['symbol'],
                    #     task_info['interval'],
                    #     task_info['data']
                    # )
                    # KC_strategy.delay(
                    #     task_info['exchange'],
                    #     task_info['symbol'],
                    #     task_info['interval'],
                    #     task_info['data']
                    # )
                    # KC_smartstrategy.delay(
                    #     task_info['exchange'],
                    #     task_info['symbol'],
                    #     task_info['interval'],
                    #     task_info['data']
                    # )
                    # EMA5strategy.delay(
                    #     task_info['exchange'],
                    #     task_info['symbol'],
                    #     task_info['interval'],
                    #     task_info['data']
                    # )
                    KC_samtrstrategy.delay(
                        task_info['exchange'],
                        task_info['symbol'],
                        task_info['interval'],
                        task_info['data']
                    )
                    successful_tasks += 1
                except Exception as e:
                    print(f"分发任务失败: {task_info} - {e}")

            duration = time.time() - start_time
            print(f"总任务: {total_tasks}, 成功: {successful_tasks}, 耗时: {duration:.2f}s")

            return {
                'total_tasks': total_tasks,
                'successful_tasks': successful_tasks,
                'duration': round(duration, 2),
                'processed_keys': len(keys)
            }

        except Exception as e:
            print(f"Redis错误: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
        finally:
            if r is not None:
                await r.close()

    # 安全运行异步函数
    try:
        # 安全运行异步函数
        result = asyncio.run(fetch_and_distribute_redis_data())
        return {"status": "success", "data": result}
    except Exception as e:
        # 捕获所有异常（包括 Redis 连接失败、JSON 错误等）
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }