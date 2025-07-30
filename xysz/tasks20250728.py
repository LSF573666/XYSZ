from multiprocessing.pool import AsyncResult
import time
from celery import shared_task
from django.http import HttpResponse
import pandas as pd
from datetime import datetime
from django.core.cache import cache

from xysz.config import get_api_balance
from xysz.env.BacktestEnv import calculate_adx, calculate_kc_channel, define_grid_strategy, execute_buy_action, execute_sell_action
from xysz.env.MockAccount import MockAccount
from xysz.main_biget import cof_main, data_delet_middle, data_delet_slow
from xysz.tests import send_mode_signal
# from xysz.main_biget import query_main

last_strategy_signal = None
last_processed_time = None
buy_close_price = None
result = None   # 用于记录上
has_traded_in_block = False
error_signal = 0
stop_five_transaction = False
strategy_result = None
balance = get_api_balance()


@shared_task(bind=True, max_retries=3)
def FB_strategy(self, ws_data):
    global has_traded_in_block, stop_five_transaction, error_signal, strategy_result
    
    try:
        # time.sleep(10)
        all_fast_data,all_slow_data = cof_main()

        ws_type = ws_data['symbol'].replace("USDT", "")
        # print(ws_type)
        symbol = ws_type
        slow_keys = list(all_fast_data.keys())
        # print(slow_keys)
        cache_key = f"kline_{ws_type}_{ws_data['timestamp'].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return

        if ws_type in slow_keys:
            # 初始化历史数据
            # middle_his_data = all_middle_data[symbol]
            fast_his_data = all_fast_data[symbol]
            # print("当前 fast_his_data 末尾数据：")
            # print(fast_his_data.tail(2))

            # 转换 WebSocket 数据为 DataFrame
            kline_data = pd.DataFrame(
                [ws_data],  # 注意：ws_data 是单条数据，需要用列表包裹
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'Denominated_Coin_Volume', 'whatever']
            )
            # print(kline_data)

            # 确保 fast_his_data 是 DataFrame
            fast_his_data = pd.DataFrame(
                fast_his_data,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'Denominated_Coin_Volume', 'whatever']
            )
            # print(kline_data)
            # print(fast_his_data.tail(2))
            # 确保列名匹配
            # fast_his_data = middle_his_data.copy()  # 假设 middle_his_data 和 fast_his_data 结构类似
            # 根据行数选择要合并的数据

            # 提取交集列
            # middle_cols = kline_data[middle_his_data.columns.intersection(kline_data.columns)]
            slow_cols = kline_data[fast_his_data.columns.intersection(kline_data.columns)]

            # 设置新索引（假设索引是时间戳）
            # middle_cols.index = [middle_his_data.index[-1] + 1]
            slow_cols.index = [fast_his_data.index[-1] + 1]

            # 合并数据
            # middle_his_data = pd.concat([middle_his_data, middle_cols], ignore_index=False)
            fast_his_data = pd.concat([fast_his_data, slow_cols], ignore_index=False)
            # print(fast_his_data.tail(3))
            # print(f"数据合并成功")
            # data_delet_slow(fast_his_data,all_fast_data,symbol)



            # supports, resistances, median_line, (dense_low, dense_high), atr_slope = identify_support_resistance(fast_his_data)
            # last_row = fast_his_data.iloc[-1]
            # current_timestamp = last_row['timestamp']
            # # print(current_timestamp)
            # close1 = float(last_row['close'])
            # prev_row = fast_his_data.iloc[-2]

            # buy_date = current_timestamp
            # # current_time = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S%z")
            # account = MockAccount(initial_balance=20)
            # btc_positions = account.positions.get(symbol, [])
            # position_size = btc_positions.get('position_size', 0) if isinstance(btc_positions, dict) else 0
            # position_side = btc_positions.get('position_side', None) if isinstance(btc_positions, dict) else None
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

            # fifteen_key = f"FB_{symbol}_{fifteen_now}"
            FB_key = 2 

            strategy_result,tide,mode,atr_slope = define_grid_strategy(symbol, fast_his_data, FB_key)
            # adx_value = calculate_adx(fast_his_data)
            # adx_value = adx_value.iloc[-1]

            # if ((tide == 1 and mode == 1) or (tide == 1 and mode == 2)) and ((position_size > 0 and position_side == 'short') or position_size <= 0) and atr_slope > 0.1 and adx_value > 20:
            #     result = 1 
            #     if position_size > 0:
            #         execute_sell_action(result, symbol, buy_date, close1, grid=result)
            #     execute_buy_action(result, symbol, buy_date, close1, grid=result)
            # elif ((tide == 2 and mode == 1) or (tide == 2 and mode == 2)) and ((position_size > 0 and position_side == 'long') or position_size <= 0) and atr_slope > 0.08 and adx_value > 20:
            #     result = 2
            #     if position_size > 0:
            #         execute_sell_action(result, symbol, buy_date, close1, grid=result)
            #     execute_buy_action(result, symbol, buy_date, close1, grid=result)
                        
                # result = 2
                # execute_sell_action(result, symbol, buy_date, close1, grid=result)
                # execute_buy_action(result, symbol, buy_date, close1, grid=result)

            # print(f"{symbol} 准备删除")
            # print("\nall_middle_data:")
            # print(middle_his_data.tail(3))
            # print("\nall_slow_data:")
            # print(middle_his_data.tail(3))

            # print(f"{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f}, 大区间:{dense_low:.3f} - {dense_high:.3f},小区间:{strategy_result['lower_bound']} - {strategy_result['upper_bound']}")
            # data_delet_middle(middle_his_data,all_middle_data,symbol)
            # data_delet_slow(slow_his_data,all_slow_data,symbol)

            # cache.set(cache_key,True, timeout=60)
            # cache.set(fifteen_key, True, timeout=900)
            # cache.set(five_key, True, timeout=300)

        # return all_slow_data
    
    except Exception as e:
        print(f"报错: {e}")
        return {  # 返回字典而不是 HttpResponse
            "status": "false",
            # "symbol": ws_type,
            # "processed_rows": len(all_slow_data)
        }
        # return HttpResponse(f"报错: {e}")

@shared_task(bind=True)
def KC_strategy(self, ws_data):
    global has_traded_in_block,error_signal, strategy_result
    five_minute = None
    try:
        # time.sleep(10)
        all_fast_data,all_slow_data = cof_main()

        ws_type = ws_data['symbol'].replace("USDT", "")
        # print(ws_type)
        symbol = ws_type
        slow_keys = list(all_slow_data.keys())
        # print(slow_keys)
        cache_key = f"kline_{ws_type}_{ws_data['timestamp'].replace(' ', '_').replace(':', '-')}"
        if cache.get(cache_key):
            # print(f"数据已处理过: {cache_key}")
            return

        if ws_type in slow_keys:
            # 初始化历史数据
            # middle_his_data = all_middle_data[symbol]
            slow_his_data = all_slow_data[symbol]
            # print("当前 slow_his_data 末尾数据：")
            # print(slow_his_data.tail(2))

            # 转换 WebSocket 数据为 DataFrame
            kline_data = pd.DataFrame(
                [ws_data],  # 注意：ws_data 是单条数据，需要用列表包裹
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'Denominated_Coin_Volume', 'whatever']
            )
            # print(kline_data)

            # 确保 slow_his_data 是 DataFrame
            slow_his_data = pd.DataFrame(
                slow_his_data,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'Denominated_Coin_Volume', 'whatever']
            )
            # print(kline_data)
            # print(slow_his_data.tail(2))
            # 确保列名匹配
            # slow_his_data = middle_his_data.copy()  # 假设 middle_his_data 和 slow_his_data 结构类似
            # 根据行数选择要合并的数据

            # 提取交集列
            # middle_cols = kline_data[middle_his_data.columns.intersection(kline_data.columns)]
            slow_cols = kline_data[slow_his_data.columns.intersection(kline_data.columns)]

            # 设置新索引（假设索引是时间戳）
            # middle_cols.index = [middle_his_data.index[-1] + 1]
            slow_cols.index = [slow_his_data.index[-1] + 1]

            # 合并数据
            # middle_his_data = pd.concat([middle_his_data, middle_cols], ignore_index=False)
            slow_his_data = pd.concat([slow_his_data, slow_cols], ignore_index=False)
            # print(slow_his_data.tail(3))
            # print(f"数据合并成功")
            data_delet_slow(slow_his_data,all_slow_data,symbol)
            # print(f"KC数据合并成功")

            kc_upper,kc_lower,Medium_track = calculate_kc_channel(slow_his_data)
            adx_value = calculate_adx(slow_his_data)
            adx_value = adx_value.iloc[-1]
            # print(adx_value)
            kc_upper = kc_upper.iloc[-1]
            kc_lower = kc_lower.iloc[-1]
            Medium_track = Medium_track.iloc[-1]
            last_row = slow_his_data.iloc[-1]
            current_timestamp = last_row['timestamp']
            close1 = last_row['close']
            prev_row = slow_his_data.iloc[-2]
            close2 = prev_row['close']
            buy_date = current_timestamp
            # print(f"KC数据合并成功66")

            # current_time = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S%z")
            account = MockAccount(initial_balance=balance)
            ETH_positions = account.positions.get(symbol, [])
            position_size = ETH_positions.get('position_size', 0) if isinstance(ETH_positions, dict) else 0
            position_side = ETH_positions.get('position_side', None) if isinstance(ETH_positions, dict) else None
            position_size = float(position_size)
            current_minute = current_timestamp.minute
            current_hour = current_timestamp.hour
            total_minutes = current_hour * 60 + current_minute
            # fifteen_minute = ((total_minutes - 1) // 15) * 15
            # five_now = ((total_minutes - 1) // 5) * 5  
            kc_grid = 3

            fifteen_now = ((total_minutes - 1) // 15) * 15
            # five_now = ((total_minutes - 1) // 5) * 5  
            # five_key = f"FB|{symbol}|{five_now}"

            # strategy_result,tide,mode,atr_slope = define_grid_strategy(symbol, slow_his_data, kc_grid)
            # print(strategy_result)

            fifteen_key = f"KC_{symbol}_{fifteen_now}"

            if fifteen_key not in cache:
                has_traded_in_block = False  # 重置交易标志
                # if close2 < kc_lower and close1 > kc_lower and adx_value > 20:
                #     error_signal -= 1
                #     if error_signal <= 0:
                #         result = 1 
                #         if position_size <= 0:
                #             execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             cache.set(fifteen_key, True, timeout=86400)
                #         if position_size > 0 and position_side == 'short':
                #             execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             cache.set(fifteen_key, True, timeout=86400)
                #     else:
                #         has_traded_in_block = True 
                #         cache.set(fifteen_key, True, timeout=86400)
                # else:
                #     if position_size > 0 and position_side == 'short':
                #         result = 1
                #         execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                #         has_traded_in_block = True 
                #         cache.set(fifteen_key, True, timeout=86400)

                # if close2 > kc_upper and close1 < kc_upper and adx_value > 20:
                #     error_signal -= 1
                #     if error_signal <= 0:
                #         result = 2 
                #         if position_size <= 0:
                #             execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             cache.set(fifteen_key, True, timeout=86400)
                #         if position_size > 0 and position_side == 'long':
                #             execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             cache.set(fifteen_key, True, timeout=86400)
                #     else:
                #         has_traded_in_block = True 
                #         cache.set(fifteen_key, True, timeout=86400)
                # else:
                #     if position_size > 0 and position_side == 'long':
                #         result = 2
                #         execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                #         has_traded_in_block = True 
                #         cache.set(fifteen_key, True, timeout=86400)
                        
                # if  close1 < kc_upper and close1 > kc_lower :
                #     if close2 > Medium_track and close1 < Medium_track :
                #         if position_size > 0 and position_side == 'long':
                #             result = 2
                #             execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             has_traded_in_block = True 
                #             cache.set(fifteen_key, True, timeout=86400)
                #     if close2 < Medium_track and close1 > Medium_track :
                #         if position_size > 0 and position_side == 'short':
                #             result = 1
                #             execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                #             has_traded_in_block = True 
                #             cache.set(fifteen_key, True, timeout=86400)


                # result = 2
                # execute_sell_action(result, symbol, buy_date, close1, grid=kc_grid)
                # execute_buy_action(result, symbol, buy_date, close1, grid=kc_grid)

            print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
            # data_delet_middle(middle_his_data,all_middle_data,symbol)
            # data_delet_slow(slow_his_data,all_slow_data,symbol)
            # cache.set(five_key_KC, True, timeout=300)
        # return all_slow_data

    except Exception as e:
            print(f"报错: {e}")
            return {  # 返回字典而不是 HttpResponse
            "status": "false",
            # "symbol": ws_type,
            # "processed_rows": len(all_slow_data)
        }
    