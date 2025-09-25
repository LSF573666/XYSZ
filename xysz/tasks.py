from multiprocessing.pool import AsyncResult
import time
import os, csv
from celery import shared_task
from django.http import HttpResponse
import pandas as pd
from datetime import datetime
from django.core.cache import cache
import numpy as np
from xysz.config import get_api_balance
from xysz.env.BacktestEnv import calculate_adx, calculate_kc_channel, calculate_volume_ratio, calculate_vi_manual, define_KC_strategy, define_KC_smartstrategy, define_grid_strategy, execute_buy_action, execute_sell_action
from xysz.env.MockAccount import MockAccount
import aiohttp
import asyncio
from asgiref.sync import sync_to_async

from xysz.tests import send_KRmode_signal
# from xysz.main_biget import query_main

last_strategy_signal = None
last_processed_time = None
buy_close_price = None
result = None   # 用于记录上
has_traded_in_block = False
error_signal = 0
KLRT_side = {}
stop_five_transaction = False
strategy_result = None
balance = get_api_balance()


@shared_task(bind=True, max_retries=3)
def FB_strategy(self, exchange, symbol, interval, data):
    try:
        # 转换数据为DataFrame
        df = pd.DataFrame(
            data['data']['data'],
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        ).sort_values(by='timestamp')
        
        last_timestamp = df['timestamp'].iloc[-1]
        # print(f"FB策略收到 {symbol} {interval} 数据，时间: {last_timestamp}")

        # 为不同时间框架创建缓存键
        cache_key_1m = f"fb_{exchange}_{symbol}_1m_data"
        cache_key_15m = f"fb_{exchange}_{symbol}_15m_data"
        cache_key_lock = f"fb_{exchange}_{symbol}_lock"
        cache_key_processed = f"fb_{exchange}_{symbol}_processed_{last_timestamp}"

        # 检查是否已处理过
        if cache.get(cache_key_processed):
            # print(f"数据已处理过: {symbol} {last_timestamp}")
            return

        # 存储数据到缓存
        if interval == '1m':
            cache.set(cache_key_1m, {'data': df, 'timestamp': last_timestamp}, timeout=20)
        elif interval == '15m':
            cache.set(cache_key_15m, {'data': df, 'timestamp': last_timestamp}, timeout=20)

        # 检查两个时间框架的数据是否都可用
        data_1m = cache.get(cache_key_1m)
        data_15m = cache.get(cache_key_15m)

        if data_1m and data_15m:
            # 获取分布式锁，防止并发处理
            if cache.add(cache_key_lock, True, timeout=20):
                try:
                    # 检查时间戳是否匹配（可选）
                    # if data_1m['timestamp'] == data_15m['timestamp']:
                    
                    fast_data = data_1m['data']
                    middle_data = data_15m['data']
                    
                    # print(f"开始执行FB策略: {symbol}, 1m数据: {len(fast_data)}, 15m数据: {len(middle_data)}")
                    
                    FB_key = 2 
                    strategy_result = define_grid_strategy(exchange, symbol, fast_data, middle_data, FB_key)
                    
                    # 标记为已处理
                    cache.set(cache_key_processed, True, timeout=20)
                    # print(f"FB策略完成: {symbol}, 结果: {strategy_result}")
                    
                finally:
                    cache.delete(cache_key_lock)
            else:
                print(f"等待锁释放: {symbol}")
                self.retry(countdown=2, max_retries=3)
        # else:
        #     print(f"等待另一个时间框架数据: {symbol}, 已有: {interval}")
            
    except Exception as e:
        print(f"FB_task报错_{exchange}_{symbol},{e}")
        if '锁' in str(e):
            self.retry(countdown=3)
        return {"status": "false"}

@shared_task(bind=True)
def KC_strategy(self, exchange, symbol, interval, data):
    global has_traded_in_block,error_signal,account
    try:
        if interval == '1m':
            # print(f"KC接受到数据{exchange}, {symbol}")
            fast_data = pd.DataFrame(
                    data['data']['data'],
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                ).sort_values(by='timestamp')
            # print(type(fast_data))
            # print(fast_data)
            exchange = exchange.upper()
            plan = "KC"
            cache_key = f"kcline_{exchange}_{symbol}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
            if cache.get(cache_key):
                # print(f"数据已处理过: {cache_key}")
                return
            kc_grid = 3
            
            exchange, adx_value = define_KC_strategy(exchange, symbol, fast_data, kc_grid)

            last_row = fast_data.iloc[-1]
            buy_date = last_row['timestamp']
            close1 = last_row['close']
            # prev_row = slow_his_data.iloc[-2]
            # close2 = prev_row['close']

            current_time = pd.to_datetime(buy_date)
            current_minute = current_time.minute
            current_hour = current_time.hour
            total_minutes = current_hour * 60 + current_minute
            # fifteen_minute = ((total_minutes - 1) // 15) * 15

            # fifteen_now = ((total_minutes - 1) // 15) * 15
            five_now = ((total_minutes - 1) // 1) * 1 

            # print(strategy_result)
            # five_key = f"KC_{symbol}_{five_now}"
            fifteen_key = f"KC_{exchange}_{symbol}_{five_now}"

            if fifteen_key not in cache:
                has_traded_in_block = False  # 重置交易标志
                # adx_value = 27
                if 25 < adx_value <= 30:
                    account = MockAccount(initial_balance=balance)
                    position_info = account.get_strategy_positions(strategy=plan, exchange=exchange, symbol=symbol)
                    position_data = position_info.get(exchange, {}).get(symbol)

                    if position_data:
                        # entry_price = float(position_data.get("entry_price", 0))
                        buy_side = position_data.get("position_side")

                        if 25 < adx_value <= 30:
                            if buy_side == 2:
                                result = 1
                                execute_sell_action(result, exchange, symbol, buy_date, close1, grid=kc_grid)
                                has_traded_in_block = True 
                                cache.set(fifteen_key, True, timeout=60)
                            elif buy_side == 1:
                                result = 2
                                execute_sell_action(result, exchange, symbol, buy_date, close1, grid=kc_grid)
                                has_traded_in_block = True 
                                cache.set(fifteen_key, True, timeout=60)

                # result = 2
                # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)

            # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        # return all_slow_data

    except Exception as e:
            print(f"KC_task_{exchange}_{symbol}报错: {e}")
            return {"status": "false"}
    
@shared_task(bind=True)
def KC_smartstrategy(self, exchange, symbol, interval, data):
    global has_traded_in_block,error_signal,account
    try:
        if interval == '1m':
            # print(f"KC接受到数据{exchange}, {symbol}")
            fast_data = pd.DataFrame(
                    data['data']['data'],
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                ).sort_values(by='timestamp')
            # print(type(fast_data))
            # print(fast_data)
            exchange = exchange.upper()
            plan = "kc_smart"

            cache_key = f"kcsmartline_{exchange}_{symbol}_{fast_data['timestamp'].iloc[-1].replace(' ', '_').replace(':', '-')}"
            if cache.get(cache_key):
                # print(f"数据已处理过: {cache_key}")
                return
            kc_grid = 4
            
            exchange, adx_value = define_KC_smartstrategy(exchange, symbol, fast_data, kc_grid)

            last_row = fast_data.iloc[-1]
            buy_date = last_row['timestamp']
            close1 = last_row['close']
            # prev_row = slow_his_data.iloc[-2]
            # close2 = prev_row['close']
            # print(f"buy_date 的值是: {buy_date}, 类型是: {type(buy_date)}")
            current_time = pd.to_datetime(buy_date)
            current_minute = current_time.minute
            current_hour = current_time.hour
            total_minutes = current_hour * 60 + current_minute
            # fifteen_minute = ((total_minutes - 1) // 15) * 15

            # fifteen_now = ((total_minutes - 1) // 15) * 15
            five_now = ((total_minutes - 1) // 1) * 1 

            # print(strategy_result)

            # five_key = f"KCsmart_{symbol}_{five_now}"
            fifteen_key = f"KCsmart_{exchange}_{symbol}_{five_now}"
            if fifteen_key not in cache:
                has_traded_in_block = False  # 重置交易标志
                account = MockAccount(initial_balance=balance)
                position_info = account.get_strategy_positions(strategy=plan, exchange=exchange, symbol=symbol)
                # print(position_info)
                position_data = position_info.get(exchange, {}).get(symbol)
                # print(position_data)
                # adx_value = 27
                if position_data:
                    # entry_price = float(position_data.get("entry_price", 0))
                    buy_side = position_data.get("position_side")
                    # print(buy_side)
                
                    if 25 < adx_value <= 30:
                        if buy_side == 2:
                            result = 1
                            execute_sell_action(result, exchange, symbol, buy_date, close1, grid=kc_grid)
                            has_traded_in_block = True 
                            cache.set(fifteen_key, True, timeout=60)
                        elif buy_side == 1:
                            result = 2
                            execute_sell_action(result, exchange, symbol, buy_date, close1, grid=kc_grid)
                            has_traded_in_block = True 
                            cache.set(fifteen_key, True, timeout=60)

                # result = 2
                # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)

            # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        # return all_slow_data

    except Exception as e:
            print(f"KC_smarttask_{exchange}_{symbol}报错: {e}")
            return {"status": "false"}


@shared_task(bind=True)
def fetch_klines_task(self):
    async def fetch_klines(session, exchange, symbol, interval, task_name):
        base_url = "http://47.236.144.131:8000/api/klines/fetch"
        params = {
            'exchange': exchange,
            'symbol': symbol,
            'interval': interval,
            'limit': 600,
            'get_more': 0
        }
        try:
            async with session.get(base_url, params=params, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    # print(f"成功: {exchange}, {symbol}, {interval} for {task_name}")
                    
                    # 根据任务类型分发
                    if task_name == 'FB':
                        FB_strategy.delay(exchange, symbol, interval, data)
                    elif task_name == 'KC':
                        KC_strategy.delay(exchange, symbol, interval, data)
                    elif task_name == 'KC_smart':
                        KC_smartstrategy.delay(exchange, symbol, interval, data)

                    return True
                else:
                    print(f"失败: {exchange}, {symbol}, {interval} for {task_name}")
                    return False
        except Exception as e:
            print(f"错误: {exchange}, {symbol}, {interval} for {task_name} - {str(e)}")
            return False

    async def main():
        exchanges = ['bitget', 'binance', 'okx', 'gate']
        # exchanges = ['bitget', 'binance', 'okx']
        # exchanges = ['bitget']
        symbols = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
        
        total_calls = 0
        successful_calls = 0
        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            # FB策略需要1m和15m数据
            fb_tasks = []
            for exchange in exchanges:
                for symbol in symbols:
                    # FB需要两个时间间隔的数据
                    fb_tasks.append(fetch_klines(session, exchange, symbol, '1m', 'FB'))
                    fb_tasks.append(fetch_klines(session, exchange, symbol, '15m', 'FB'))
            
            # KC策略只需要1m数据
            kc_tasks = []
            for exchange in exchanges:
                for symbol in symbols:
                    kc_tasks.append(fetch_klines(session, exchange, symbol, '1m', 'KC'))

            kc_smarttasks = []
            for exchange in exchanges:
                for symbol in symbols:
                    kc_smarttasks.append(fetch_klines(session, exchange, symbol, '1m', 'KC_smart'))
            
            # 并行执行所有任务
            all_tasks = fb_tasks + kc_tasks + kc_smarttasks
            # all_tasks = kc_smarttasks
            results = await asyncio.gather(*all_tasks, return_exceptions=True)

            total_calls = len(all_tasks)
            successful_calls = sum(1 for result in results if result is True)

        end_time = time.time()
        duration = end_time - start_time

        # print(f"\n总请求数: {total_calls}, 成功: {successful_calls}, 失败: {total_calls - successful_calls}")
        # print(f"耗时: {duration:.2f}秒")

        return {'total_calls': total_calls, 'successful_calls': successful_calls}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # 返回任务对象，让调用方处理
        task = loop.create_task(main())
        return task
    else:
        try:
            result = loop.run_until_complete(main())
            # 确保返回的是简单可序列化的字典
            return {
                'total_calls': result.get('total_calls', 0),
                'successful_calls': result.get('successful_calls', 0)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
        finally:
            if not loop.is_closed():
                loop.close()