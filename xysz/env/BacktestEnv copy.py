# import threading
from django.http import HttpResponse
import pandas as pd
from datetime import datetime

import talib
from xysz.config import get_api_balance
import time
from xysz.env.MockAccount import MockAccount
import numpy as np
from xysz.tests import send_mode_signal, send_stock_alert, send_trading_signal, upload_coin_reminder


pd.set_option('mode.chained_assignment', None)

def calculate_atr(data, atr_period=None):
    """计算 ATR 和斜率"""
    data['atr'] = talib.ATR(data['high'], data['low'], data['close'], timeperiod=atr_period)
    data['atr_slope'] = data['atr'].diff() / data['atr'].shift(1)
    
    return data

class BacktestEnv:
    def __init__(self, middle_data, slow_data):
        self.slow_data = slow_data
        self.middle_data = middle_data 
        # self.fast_data = fast_data 
        self.last_strategy_signal = None
        self.last_processed_time = None
        self.buy_close_price = None
        self.middle_current_time = None
        self.result = None   # 用于记录上
        self.has_traded_in_block = False
        self.fifteen_minute = None
        self.five_minute = None
        self.error_signal = 0
        self.stop_five_transaction = False
        self.tide = None
        self.strategy_result = None
        self.balance = get_api_balance()
        self.algo_ids = []
        self.last_state = {
            'side': None,
            'mode': None,
            'dpo': None
        }


    def execute_buy_action(self, buy_date, fifteen_minute, grid=None):
        """执行买入操作并记录信号"""
        if self.result is None:
            return 
        
        if grid == 0:
            self.middle_current_time = None
            time_interval = 900
            timetype = "15分钟"
            reminder = "Fibonacci"
        elif grid in (1, 2):
            time_interval = 300
            timetype = "5分钟"
            reminder = "grid_fly"

        position_side = 'long' if self.result == 1 else 'short'
        current_date = pd.Timestamp(buy_date)
        if current_date.tzinfo is None:
            current_date = current_date.tz_localize('UTC').tz_convert('Asia/Shanghai')
        else:
            current_date = current_date.tz_convert('Asia/Shanghai')
        dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S%z")
        formatted_time = dt.strftime("%H:%M")
        self.slow_data['timestamp'] = pd.to_datetime(self.slow_data['timestamp'], utc=True).dt.tz_convert('UTC+08:00')
        small_level_data = self.slow_data[self.slow_data['timestamp'] == current_date]
        row = small_level_data.iloc[0] 
        current_price = row['close']
        position_percentage = 0.2
        self.account.buy('BTC', current_price, position_side=position_side,position_percentage=position_percentage)
        # 输出持仓信息和盈亏
        BTC_info = self.account.get_position_info('BTC', position_side=position_side)
        print(f"BTC 本地买入持仓信息: {row['timestamp']} ,当前仓位={self.position_size}, {BTC_info}")

        try:
            order_id = str(int(time.time()))

            if position_side == "long":
                side = "OPEN_LONG"
                open_side = '多'
            elif position_side == "short":
                side = "OPEN_SHORT"
                open_side = '空'

                
            # stop_loss_trigger_price = round(
                        # current_price * (1 + 0.01) if position_side == "short" else current_price * (1 - 0.01), 2)
            self.buy_close_price = current_price
            formatted_price = f"{current_price:.2f}" 
            ps = round(BTC_info['position_size'],3)
            # if ps < 0.01 or ps > 10:
            ps = 0.02

            # 执行买入操作
            upload_coin_reminder(
                    coin_platform="BITGET",
                    coin_name="BTC",
                    reminder_name=reminder,
                    side=side,
                    price=formatted_price,
                    timetype=timetype
                )
            order_request = send_trading_signal(
                    type_value="buysell",
                    coin="BTC",
                    time_frame=time_interval,
                    plan_name=reminder,
                    side=side,
                    price=formatted_price,
                    time2=formatted_time
                )

            send_stock_alert("BTC", time_interval, reminder, f"{open_side} {formatted_time},{formatted_price}")
            if order_request:
                print(ps,current_price)
                # print(f"已下单: {order_request}")
                self.has_traded_in_block = True  # 标记已交易
                self.fifteen_minute = fifteen_minute
                self.five_minute = fifteen_minute
                self.error_signal = 0

        except Exception as e:
            print(f"okx下单失败: {e}")

        # print(f"当前账户总余额: {self.account.get_account_summary()}")


    def execute_sell_action(self, buy_date, fifteen_minute, grid=None):
        """处理卖出操作卖出"""
        if self.result is None:
            return
        
        if grid == 0:
            time_interval = 900
            timetype = "15分钟"
            reminder = "Fibonacci"
        elif grid in (1, 2):
            time_interval = 300
            timetype = "5分钟"
            reminder = "grid_fly"

    
        filtered_data = self.slow_data[self.slow_data['timestamp'] == buy_date]
        if not filtered_data.empty:
            closest_row = filtered_data.iloc[-1]
            previous_date = closest_row['timestamp']
            previous_price = closest_row['close']
        else:
            previous_date = None
            previous_price = None
        print(f"本地卖出信号触发：日期={previous_date}, 卖出价格={previous_price}") 

        dt = datetime.strptime(previous_date, "%Y-%m-%d %H:%M:%S%z")
        formatted_time = dt.strftime("%H:%M")
        formatted_price = f"{previous_price:.2f}"
        sell_side = 'CLOSE_SHORT' if self.result == 1 else 'CLOSE_LONG'
        sell_side1 = '平空' if self.result == 1 else '平多'
        try:
            request = upload_coin_reminder(
                    coin_platform="BITGET",
                    coin_name="BTC",
                    reminder_name=reminder,
                    side=sell_side,
                    price=formatted_price,
                    timetype=timetype
                )
            order_request = send_trading_signal(
                    type_value="buysell",
                    coin="BTC",
                    time_frame=time_interval,
                    plan_name=reminder,
                    side=sell_side,
                    price=formatted_price,
                    time2=formatted_time
                )
            send_stock_alert("BTC", time_interval, reminder, f"{sell_side1} {formatted_time},{formatted_price}")
            if order_request:
                self.has_traded_in_block = True  # 标记已交易
                self.fifteen_minute = fifteen_minute
                self.five_minute = fifteen_minute

        except Exception as e:
            print(f"okx平仓失败: {e}")

    """斐波那契回撤+正态分布"""
    def identify_support_resistance(self, data, n=480, variance_threshold=0.85):
        try:
            if len(data) < n:
                n = len(data)

            recent_data = data.tail(n).copy()

            price_cols = ['open', 'high', 'low', 'close']
            for col in price_cols:
                recent_data[col] = recent_data[col].astype(float)

            start_price = float(recent_data.iloc[0]['close'])
            end_price = float(recent_data.iloc[-1]['close'])
            is_uptrend = (end_price > start_price)

            highest_high = float(recent_data['high'].max())
            lowest_low = float(recent_data['low'].min())
            price_range = highest_high - lowest_low

            fib_levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]

            if is_uptrend:
                self.tide = 1
                fib_prices = [lowest_low + level * price_range for level in fib_levels]
            else:
                self.tide = 2
                fib_prices = [highest_high - level * price_range for level in fib_levels]

            level_prices = [float(price) for price in fib_prices]

            top_supports = sorted(level_prices)[:3]
            top_resistances = sorted(level_prices, reverse=True)[:3]
            median_line = sorted(level_prices, reverse=True)[-4]

            all_prices = np.concatenate([
                recent_data['open'].values,
                recent_data['high'].values,
                recent_data['low'].values,
                recent_data['close'].values
            ]).astype(float)

            lower_bound = np.percentile(all_prices, (1 - variance_threshold)/2 * 100)
            upper_bound = np.percentile(all_prices, (1 - (1 - variance_threshold)/2) * 100)

            lower_bound = max(lower_bound, lowest_low)
            upper_bound = min(upper_bound, highest_high)

            atr_period = 8
            recent_data = calculate_atr(recent_data, atr_period=atr_period)
            atr_slope = recent_data['atr_slope'].iloc[-1] if not recent_data['atr_slope'].isna().all() else 0

            return top_supports, top_resistances, median_line, (float(lower_bound), float(upper_bound)), atr_slope
        
        except Exception as e:
            print(f"报错: {e}")
    

    """正态分布"""
    def normal_distribution(self, data, variance_threshold=0.85):

        def ensure_shanghai_time(ts):
            ts = pd.to_datetime(ts)
            if ts.tzinfo is None:
                return ts.tz_localize('Asia/Shanghai')
            else: 
                return ts.tz_convert('Asia/Shanghai')

        last_timestamp = ensure_shanghai_time(data.iloc[-1]['timestamp'])
        compare_time = ensure_shanghai_time(self.middle_current_time)
        data['timestamp'] = data['timestamp'].apply(ensure_shanghai_time)

        if last_timestamp > compare_time:
            normal_data = data[data['timestamp'] > compare_time].copy()

        highest_high = float(normal_data['high'].max())
        lowest_low = float(normal_data['low'].min())

        all_prices = np.concatenate([
            normal_data['open'].values,
            normal_data['high'].values,
            normal_data['low'].values,
            normal_data['close'].values
        ]).astype(float)

        lower_bound = np.percentile(all_prices, (1 - variance_threshold)/2 * 100)
        upper_bound = np.percentile(all_prices, (1 - (1 - variance_threshold)/2) * 100)

        lower_bound = max(lower_bound, lowest_low)
        upper_bound = min(upper_bound, highest_high)

        return (float(lower_bound), float(upper_bound))

    """5分钟网格"""
    def define_grid_strategy(self, middle_his_data, slow_his_data, grid_pct=1):
        try:
            if len(slow_his_data) < 30:
                return {
                    'is_consolidation': False,
                    'signal': 'hold',
                    'reason': '数据不足4条'
                }

            for i in range(33, 10-1, -1):
                if len(slow_his_data) < i:
                    continue

                closes = slow_his_data['close'].iloc[-i:].values
                min_close = np.min(closes)
                max_close = np.max(closes)
                fluctuation_pct = (max_close - min_close) / min_close * 100

                is_consolidation = fluctuation_pct < grid_pct

                if fluctuation_pct > 1.5 :
                    self.stop_five_transaction = True

                # 初始化结果
                result = {
                    'is_consolidation': is_consolidation,
                    'current_price': slow_his_data.iloc[-1]['close'],
                    'fluctuation_pct': fluctuation_pct,
                    'signal': 'hold',
                    'lower_bound': None,
                    'upper_bound': None
                }
            
                if is_consolidation:
                    if self.middle_current_time is None:
                        self.middle_current_time = middle_his_data.iloc[-i*3]['timestamp']
                    lower_bound, upper_bound = self.normal_distribution(middle_his_data)
                    middle_close1 = middle_his_data.iloc[-1]['close']
                    middle_close2 = middle_his_data.iloc[-2]['close']

                    result.update({
                        'lower_bound': lower_bound,
                        'upper_bound': upper_bound
                    })

                    if middle_close1 > lower_bound and middle_close2 <= lower_bound:
                        self.tide = 2
                        result['signal'] = '1'

                    elif middle_close1 < upper_bound and middle_close2 >= upper_bound:
                        self.tide = 2
                        result['signal'] = '2'
                    if lower_bound is not None:
                        mode = 1
                else:
                    mode = 2

                atr_period = 5
                middle_his_data = calculate_atr(middle_his_data, atr_period=atr_period)
                five_atr = middle_his_data['atr'].iloc[-1]
                if five_atr > 100 :
                    dpo = 0.5
                else:
                    dpo = 0.2
                
                current_state = {
                    'side': self.tide,
                    'mode': mode,
                    'dpo': dpo
                }
                if current_state != self.last_state:
                    send_mode_signal(
                        coin="BTC",
                        side=self.tide,
                        mode=mode,
                        dpo=dpo
                    )
                    self.last_state = current_state

                return result
            
        except Exception as e:
            print(f"报错: {e}")

    """
    买入主逻辑
    """
    def set_signals(self, middle_his_data, slow_his_data):
        try:
            slow_prices = pd.DataFrame(slow_his_data)  # 包含high, low, close列
            supports, resistances, median_line, (dense_low, dense_high), atr_slope = self.identify_support_resistance(slow_prices)

            self.slow_data = slow_his_data
            self.middle_data = middle_his_data
            last_row = self.slow_data.iloc[-1]
            current_timestamp = last_row['timestamp']
            close1 = last_row['close']
            prev_row = self.slow_data.iloc[-2]
            close2 = prev_row['close']

            supports_1 = supports[0] if len(supports) > 0 else None
            supports_2 = supports[1] if len(supports) > 1 else None
            supports_3 = supports[2] if len(supports) > 1 else None
            resistances_5 = resistances[0] if len(resistances) > 0 else None
            resistances_4 = resistances[1] if len(resistances) > 1 else None
            resistances_3 = resistances[2] if len(resistances) > 1 else None

            buy_date = current_timestamp
            current_time = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S%z")
            self.account = MockAccount(initial_balance=self.balance)
            btc_positions = self.account.positions.get('BTC', [])
            self.position_size = btc_positions.get('position_size', 0) if isinstance(btc_positions, dict) else 0
            self.position_side = btc_positions.get('position_side', None) if isinstance(btc_positions, dict) else None
            self.buy_close_price = float(self.account.first_buyprice) if self.account.first_buyprice is not None else 0
            self.position_size = float(self.position_size)

            if self.buy_close_price is not None or self.buy_close_price != 0:
                longprice_gap = close1 - self.buy_close_price
                shortprice_gap = self.buy_close_price - close1
            else :
                longprice_gap = 0
                shortprice_gap = 0

            current_minute = current_time.minute
            current_hour = current_time.hour
            total_minutes = current_hour * 60 + current_minute
            fifteen_minute = ((total_minutes - 1) // 15) * 15
            five_minute = ((total_minutes - 1) // 5) * 5  
            if self.fifteen_minute is None:
                self.fifteen_minute = fifteen_minute - 20
            if fifteen_minute != self.fifteen_minute:
                self.has_traded_in_block = False  # 重置交易标志
                long_line_price = supports_2 if supports_2 > dense_low else dense_low
                if close2 < long_line_price and close1 > long_line_price and atr_slope > 0.005:
                    self.error_signal -= 1
                    if self.error_signal <= 0:
                        self.result = 1 
                        if self.position_size <= 0:
                            self.execute_buy_action(buy_date, fifteen_minute, grid=0)
                        if self.position_size > 0 and self.position_side == 'short':
                            self.execute_sell_action(buy_date, fifteen_minute, grid=0)
                            if shortprice_gap > 500:
                                self.error_signal = 2
                                print(f"当前价格与买入价格价差: {shortprice_gap}，此次标记错误信号，不交易")
                            else: 
                                self.execute_buy_action(buy_date, fifteen_minute, grid=0)
                    else:
                        self.has_traded_in_block = True 
                        self.fifteen_minute = fifteen_minute
                short_line_price = resistances_4 if resistances_4 < dense_high else dense_high
                if close2 > short_line_price and close1 < short_line_price and atr_slope > 0.01:
                    self.error_signal -= 1
                    if self.error_signal <= 0:
                        self.result = 2 
                        if self.position_size <= 0:
                            self.execute_buy_action(buy_date, fifteen_minute, grid=0)
                        if self.position_size > 0 and self.position_side == 'long':
                            self.execute_sell_action(buy_date, fifteen_minute, grid=0)
                            if longprice_gap > 500:
                                self.error_signal = 2
                                print(f"当前价格与买入价格价差: {longprice_gap}，此次标记错误信号，不交易")
                            else:
                                self.execute_buy_action(buy_date, fifteen_minute, grid=0)
                    else:
                        self.has_traded_in_block = True 
                        self.fifteen_minute = fifteen_minute

                short_supports = supports_2 if supports_2 < dense_low else dense_low
                long_resistances = resistances_4 if resistances_4 > dense_high else dense_high
                short_supports_price = short_supports * 0.985 if short_supports * 0.985 > supports_1 else supports_1 * 0.9995
                long_resistances_price = long_resistances * 1.015 if long_resistances * 1.015 < resistances_5 else resistances_5 * 1.0005
                print(f"大级别支撑位: {supports_1:.3f},{supports_2:.3f}  中位值: {median_line:.3f},  压力位: {resistances_4:.3f},{resistances_5:.3f},空头: {short_supports_price:.3f}, 多头: {long_resistances_price:.3f},artr_slope: {atr_slope:.3f}")

                if ((self.position_size > 0 and self.position_side == 'long') or self.position_size <= 0) :
                    if close2 > short_supports_price and close1 < short_supports_price and atr_slope > 0.005:
                        self.result = 2 
                        self.execute_sell_action(buy_date, fifteen_minute, grid=0)
                        self.error_signal -= 1
                        if self.error_signal <= 0:
                            if shortprice_gap > 500:
                                    self.error_signal = 2
                                    print(f"当前价格与买入价格价差: {shortprice_gap}，此次标记错误信号，不交易")
                            else: 
                                self.execute_buy_action(buy_date, fifteen_minute, grid=0)
                                print(f"压力位: {short_supports_price:.3f}")
                        else:
                            self.has_traded_in_block = True
                            self.fifteen_minute = fifteen_minute

                if ((self.position_size > 0 and self.position_side == 'short') or self.position_size <= 0) :
                    if close2 < long_resistances_price and close1 > long_resistances_price and atr_slope > 0.005:
                        self.result = 1
                        self.execute_sell_action(buy_date, fifteen_minute, grid=0)
                        if self.error_signal <= 0:
                            if shortprice_gap > 500:
                                    self.error_signal = 2
                                    print(f"当前价格与买入价格价差: {shortprice_gap}，此次标记错误信号，不交易")
                            else: 
                                self.execute_buy_action(buy_date, fifteen_minute, grid=0)
                                print(f"支撑位: {long_resistances_price:.3f}")
                        else:
                            self.has_traded_in_block = True
                            self.fifteen_minute = fifteen_minute

            if self.five_minute is None:
                self.five_minute = five_minute - 10
            if five_minute != self.five_minute:
                self.has_traded_in_block = False 
                self.strategy_result = self.define_grid_strategy(middle_his_data, slow_his_data)
                if self.strategy_result['signal'] == '1' and ((self.position_size > 0 and self.position_side == 'short') or self.position_size <= 0):
                    self.result = 1 
                    if self.position_size > 0:
                        self.execute_sell_action(buy_date, five_minute, grid=self.result)
                    self.execute_buy_action(buy_date, five_minute, grid=self.result)
                elif self.strategy_result['signal'] == '2' and ((self.position_size > 0 and self.position_side == 'long') or self.position_size <= 0):
                    self.result = 2
                    if self.position_size > 0:
                        self.execute_sell_action(buy_date, five_minute, grid=self.result)
                    self.execute_buy_action(buy_date, five_minute, grid=self.result)

                self.result = 1
                # self.execute_sell_action(buy_date, fifteen_minute, grid=self.result)
                # self.execute_buy_action(buy_date, fifteen_minute, grid=self.result)

                if self.strategy_result['lower_bound'] and self.strategy_result['upper_bound'] is not None :
                    if (close1 < self.strategy_result['lower_bound'] * 0.9982) or (close1 > self.strategy_result['upper_bound'] *1.0022):
                        self.result = 1 if self.strategy_result['signal'] == '1'else 2
                        if self.position_size > 0:
                            self.execute_sell_action(buy_date, five_minute, grid=self.result)
                        self.execute_buy_action(buy_date, five_minute, grid=self.result)
                        self.stop_five_transaction = False

            print(f"{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f}, 大区间:{dense_low:.3f} - {dense_high:.3f},小区间:{self.strategy_result['lower_bound']} - {self.strategy_result['upper_bound']}")

            return 1
        
        except Exception as e:
            print(f"报错: {e}")
            return HttpResponse(f"报错: {e}")
