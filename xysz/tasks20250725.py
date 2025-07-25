from multiprocessing.pool import AsyncResult
import time
from celery import shared_task
from django.http import HttpResponse
import pandas as pd
from django.core.cache import cache
import pytz
from datetime import datetime, timezone, timedelta
from xysz.config import get_api_balance
from xysz.core.fetcher_redisdata import fetch_redis_data
from xysz.env.BacktestEnv import calculate_adx, calculate_kc_channel, define_grid_strategy, execute_buy_action, execute_sell_action, identify_support_resistance
from xysz.env.MockAccount import MockAccount
from xysz.main_biget import data_delet_slow
# from xysz.main_biget import query_main

last_strategy_signal = None
last_processed_time = None
buy_close_price = None
result = None   # 用于记录上
has_traded_in_block = False
error_signal = 0
stop_five_transaction = False
time_keys = set()
strategy_result = None
balance = get_api_balance()


# all_middle_data, all_slow_data = cof_main()

@shared_task(bind=True, max_retries=3)
def FB_strategy(self):
    global has_traded_in_block, stop_five_transaction, error_signal, strategy_result
    
    try:
        slow_his_data, symbol = fetch_redis_data()

        slow_keys = list(slow_his_data.keys())
        slow_keys = list(map(str.upper, slow_keys))
        # print(slow_keys)
        
        cache_key = f"kline_{symbol}_{slow_his_data['timestamp']}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        cache.set(cache_key, True, timeout=10)
        # print(ws_type)

        # supports, resistances, median_line, (dense_low, dense_high), atr_slope = identify_support_resistance(slow_his_data)
        last_row = slow_his_data.iloc[-1]
        timestamp_ms = last_row['timestamp']  # 毫秒级时间戳
        print(timestamp_ms)
        timestamp_seconds = timestamp_ms / 1000  # 转换为秒级
        utc_time = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        beijing_time = utc_time.astimezone(timezone(timedelta(hours=8)))
        formatted_time = beijing_time.strftime("%Y-%m-%d %H:%M:%S%z")
        current_timestamp = formatted_time[:-2] + ":" + formatted_time[-2:]
        print(current_timestamp)
        close1 = float(last_row['close'])
        prev_row = slow_his_data.iloc[-2]
        close2 = float(prev_row['close'])
        print(close1)
        print(close2)
        # supports_1 = supports[0] if len(supports) > 0 else None
        # supports_2 = supports[1] if len(supports) > 1 else None
        # supports_3 = supports[2] if len(supports) > 1 else None
        # resistances_5 = resistances[0] if len(resistances) > 0 else None
        # resistances_4 = resistances[1] if len(resistances) > 1 else None
        # resistances_3 = resistances[2] if len(resistances) > 1 else None
        buy_date = current_timestamp
        # current_time = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S%z")
        account = MockAccount(initial_balance=20)
        btc_positions = account.positions.get(symbol, [])
        position_size = btc_positions.get('position_size', 0) if isinstance(btc_positions, dict) else 0
        position_side = btc_positions.get('position_side', None) if isinstance(btc_positions, dict) else None
        # buy_close_price = float(account.first_buyprice) if account.first_buyprice is not None else 0
        # position_size = float(position_size)
        # if buy_close_price is not None or buy_close_price != 0:
        #     longprice_gap = close1 - buy_close_price
        #     shortprice_gap = buy_close_price - close1
        # else :
        #     longprice_gap = 0
        #     shortprice_gap = 0
        # current_minute = current_time.minute
        # current_hour = current_time.hour
        # total_minutes = current_hour * 60 + current_minute
        # fifteen_now = ((total_minutes - 1) // 15) * 15
        # five_now = ((total_minutes - 1) // 5) * 5  
        # five_key = f"FB|{symbol}|{five_now}"
        # # fifteen_key = f"FB|{symbol}|{fifteen_now}"
        # fifteen_key = f"FB_{symbol}_{fifteen_now}"
        FB_key = 2 
        strategy_result,tide,mode = define_grid_strategy(symbol, slow_his_data, FB_key)
        print(strategy_result,tide,mode)
        # if ((tide == 1 and mode == 1) or (tide == 1 and mode == 2)) and ((position_size > 0 and position_side == 'short') or position_size <= 0):
        #     result = 1 
        #     if position_size > 0:
        #         execute_sell_action(result, symbol, buy_date, close1, grid=result)
        #     execute_buy_action(result, symbol, buy_date, close1, grid=result)
        # elif ((tide == 2 and mode == 1) or (tide == 2 and mode == 2)) and ((position_size > 0 and position_side == 'long') or position_size <= 0):
        #     result = 2
        #     if position_size > 0:
        #         execute_sell_action(result, symbol, buy_date, close1, grid=result)
        #     execute_buy_action(result, symbol, buy_date, close1, grid=result)

        #     if ((tide == 1 and mode == 1) or (tide == 1 and mode == 2)) and ((position_size > 0 and position_side == 'short') or position_size <= 0):
        #         result = 1 
        #         if position_size > 0:
        #             execute_sell_action(result, symbol, buy_date, close1, grid=result)
        #         execute_buy_action(result, symbol, buy_date, close1, grid=result)
        #     elif ((tide == 2 and mode == 1) or (tide == 2 and mode == 2)) and ((position_size > 0 and position_side == 'long') or position_size <= 0):
        #         result = 2
        #         if position_size > 0:
        #             execute_sell_action(result, symbol, buy_date, close1, grid=result)
        #         execute_buy_action(result, symbol, buy_date, close1, grid=result)
                    

        return 1
    
    except Exception as e:
        print(f"报错: {e}")
        return {  # 返回字典而不是 HttpResponse
            "status": "false",
            "symbol": symbol,
        }
        # return HttpResponse(f"报错: {e}")

@shared_task(bind=True)
def KC_strategy(self, ws_data):
    global has_traded_in_block,time_keys,error_signal, strategy_result
    five_minute = None
    try:
        time.sleep(0.2)
        ws_type = ws_data['symbol'].replace("USDT", "")
        symbol = ws_type
        all_middle_data, all_slow_data = fetch_redis_data()

        slow_keys = list(all_slow_data.keys())
        
        cache_key = f"kline_{ws_type}_{ws_data['timestamp']}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return
        cache.set(cache_key, True, timeout=10)

        if ws_type in slow_keys:
            # 初始化历史数据
            kline_data = pd.DataFrame(
                [ws_data],  # 注意：ws_data 是单条数据，需要用列表包裹
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'Denominated_Coin_Volume', 'whatever']
            )
            middle_his_data = all_middle_data.get(symbol, pd.DataFrame())
            slow_his_data = all_slow_data.get(symbol, pd.DataFrame())

            # print(kline_data)
            # print(slow_his_data.tail(2))
            # 确保列名匹配
            middle_his_data = slow_his_data.copy()  # 假设 middle_his_data 和 slow_his_data 结构类似
            middle_cols = kline_data[middle_his_data.columns.intersection(kline_data.columns)]
            slow_cols = kline_data[slow_his_data.columns.intersection(kline_data.columns)]
            middle_cols.index = [middle_his_data.index[-1] + 1]
            slow_cols.index = [slow_his_data.index[-1] + 1]
            middle_his_data = pd.concat([middle_his_data, middle_cols], ignore_index=False)
            slow_his_data = pd.concat([slow_his_data, slow_cols], ignore_index=False)

            kc_upper,kc_lower = calculate_kc_channel(middle_his_data)
            adx_value = calculate_adx(middle_his_data)
            adx_value = adx_value.iloc[-1]
            # print(adx_value)
            kc_upper = kc_upper.iloc[-1]
            kc_lower = kc_lower.iloc[-1]
            last_row = middle_his_data.iloc[-1]
            current_timestamp = last_row['timestamp']
            close1 = last_row['close']
            prev_row = middle_his_data.iloc[-2]
            close2 = prev_row['close']
            buy_date = current_timestamp
            # print(f"KC数据合并成功66")

            current_time = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S%z")
            account = MockAccount(initial_balance=balance)
            ETH_positions = account.positions.get(symbol, [])
            position_size = ETH_positions.get('position_size', 0) if isinstance(ETH_positions, dict) else 0
            position_side = ETH_positions.get('position_side', None) if isinstance(ETH_positions, dict) else None
            position_size = float(position_size)
            current_minute = current_time.minute
            current_hour = current_time.hour
            total_minutes = current_hour * 60 + current_minute
            # fifteen_minute = ((total_minutes - 1) // 15) * 15
            five_now = ((total_minutes - 1) // 5) * 5  
            kc_grid = 3

            five_key_KC = f"KC|{symbol}|{five_now}"
            if five_key_KC not in cache:

                strategy_result = define_grid_strategy(symbol, middle_his_data, slow_his_data,kc_grid)

                has_traded_in_block = False  # 重置交易标志
                if close2 < kc_lower and close1 > kc_lower and adx_value > 25:
                    error_signal -= 1
                    if error_signal <= 0:
                        result = 1 
                        if position_size <= 0:
                            execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                            cache.set(five_key_KC, True, timeout=300)
                        if position_size > 0 and position_side == 'short':
                            execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                            execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                            cache.set(five_key_KC, True, timeout=300)
                    else:
                        has_traded_in_block = True 
                        cache.set(five_key_KC, True, timeout=300)
                else:
                    if position_size > 0 and position_side == 'short':
                        execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                        has_traded_in_block = True 
                        cache.set(five_key_KC, True, timeout=300)

                if close2 > kc_upper and close1 < kc_upper and adx_value > 25:
                    error_signal -= 1
                    if error_signal <= 0:
                        result = 2 
                        if position_size <= 0:
                            execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                            cache.set(five_key_KC, True, timeout=300)
                        if position_size > 0 and position_side == 'long':
                            execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                            execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                            cache.set(five_key_KC, True, timeout=300)
                    else:
                        has_traded_in_block = True 
                        cache.set(five_key_KC, True, timeout=300)
                else:
                    if position_size > 0 and position_side == 'long':
                        execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                        has_traded_in_block = True 
                        cache.set(five_key_KC, True, timeout=300)

                # result = 1
                # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)

                print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},lower:{kc_lower:.3f},lower:{kc_upper:.3f},ADX:{adx_value:.3f}")
                # data_delet_middle(middle_his_data,all_middle_data,symbol)

                # cache.set(five_key_KC, True, timeout=·300)··

                return 1

    except Exception as e:
            print(f"报错: {e}")
            return {  # 返回字典而不是 HttpResponse
            "status": "false",
            "symbol": symbol,
        }