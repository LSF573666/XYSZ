# import threading
from django.http import HttpResponse
import pandas as pd
from datetime import datetime
import ta
import talib
from xysz.config import get_api_balance
import time
from xysz.env.MockAccount import MockAccount
from django.core.cache import cache

import numpy as np
from xysz.tests import send_mode_signal, send_stock_alert, send_trading_signal, upload_coin_reminder


pd.set_option('mode.chained_assignment', None)

last_strategy_signal = None
last_processed_time = None
buy_close_price = None
middle_current_time = None
result = None   # 用于记录上
has_traded_in_block = False
error_signal = 0
stop_five_transaction = False
tide = None
FBside = {}
KCside = {}
strategy_result = None
balance = get_api_balance()
algo_ids = []
last_state = {
    'side': None,
    'mode': None,
    'dpo': None
}

account = MockAccount(initial_balance=20)
btc_positions = account.positions.get('BTC', [])
position_size = btc_positions.get('position_size', 0) if isinstance(btc_positions, dict) else 0
position_side = btc_positions.get('position_side', None) if isinstance(btc_positions, dict) else None
buy_close_price = float(account.first_buyprice) if account.first_buyprice is not None else 0
position_size = float(position_size)


def calculate_atr(data, atr_period=None):
    """计算 ATR 和斜率"""
    data['atr'] = talib.ATR(data['high'], data['low'], data['close'], timeperiod=atr_period)
    data['atr_slope'] = data['atr'].diff() / data['atr'].shift(1)
    
    return data

def execute_buy_action(result, symbol, buy_date, close, grid=None):
    global middle_current_time,has_traded_in_block,error_signal
    """执行买入操作并记录信号"""
    if result is None:
        return 
    
    if grid == 0:
        middle_current_time = None
        time_interval = 900
        timetype = "15分钟"
        reminder = "grid_fly"
    elif grid in (1, 2):
        time_interval = 900
        timetype = "15分钟"
        reminder = "grid_fly"
    elif grid == 3 :
        time_interval = 900
        timetype = "15分钟"
        reminder = "KC"

    position_side = 'long' if result == 1 else 'short'
    current_date = pd.Timestamp(buy_date)
    if current_date.tzinfo is None:
        current_date = current_date.tz_localize('UTC').tz_convert('Asia/Shanghai')
    else:
        current_date = current_date.tz_convert('Asia/Shanghai')
    dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S%z")
    formatted_time = dt.strftime("%H:%M")
    current_price = close
    position_percentage = 0.2
    account.buy(symbol, current_price, position_side=position_side,position_percentage=position_percentage)
    # 输出持仓信息和盈亏
    BTC_info = account.get_position_info(symbol, position_side=position_side)
    # print(f"{symbol} 本地买入持仓信息: {buy_date} ,当前仓位={position_size}, {BTC_info}")
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
        # buy_close_price = current_price
        formatted_price = f"{current_price:.2f}" 
        ps = round(BTC_info['position_size'],3)
        # if ps < 0.01 or ps > 10:
        ps = 0.02
        # 执行买入操作
        upload_coin_reminder(
                coin_platform="BITGET",
                coin_name=symbol,
                reminder_name=reminder,
                side=side,
                price=formatted_price,
                timetype=timetype
            )
        order_request = send_trading_signal(
                type_value="buysell",
                coin=symbol,
                time_frame=time_interval,
                plan_name=reminder,
                side=side,
                price=formatted_price,
                time2=formatted_time
            )
        send_stock_alert(symbol, time_interval, reminder, f"{open_side} {formatted_time},{formatted_price}")
        if order_request:
            print(reminder,symbol,side,formatted_price)
            # print(f"已下单: {order_request}")
            has_traded_in_block = True  # 标记已交易
            error_signal = 0
    except Exception as e:
        print(f"okx下单失败: {e}")
    # print(f"当前账户总余额: {account.get_account_summary()}")

def execute_sell_action(result, symbol,buy_date, close, grid=None):
    """处理卖出操作卖出"""
    if result is None:
        return
    
    if grid == 0:
        time_interval = 900
        timetype = "15分钟"
        reminder = "grid_fly"
    elif grid in (1, 2):
        time_interval = 900
        timetype = "15分钟"
        reminder = "grid_fly"
    elif grid == 3 :
        time_interval = 900
        timetype = "15分钟"
        reminder = "KC"
        selltype = "TP"

    # print(f"本地卖出信号触发：日期={buy_date}, 卖出价格={close}") 
    dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S%z")
    formatted_time = dt.strftime("%H:%M")
    formatted_price = f"{close:.2f}"
    sell_side = 'CLOSE_SHORT' if result == 1 else 'CLOSE_LONG'
    sell_side1 = '平空' if result == 1 else '平多'
    try:
        request = upload_coin_reminder(
                coin_platform="BITGET",
                coin_name=symbol,
                reminder_name=reminder,
                side=sell_side,
                price=formatted_price,
                timetype=timetype
            )
        order_request = send_trading_signal(
                type_value="buysell",
                coin=symbol,
                time_frame=time_interval,
                plan_name=reminder,
                side=sell_side,
                selltype=selltype,
                price=formatted_price,
                time2=formatted_time
            )
        # send_stock_alert(symbol, time_interval, reminder, f"{sell_side1} {formatted_time},{formatted_price}")
        if order_request:
            has_traded_in_block = True  # 标记已交易
    except Exception as e:
        print(f"okx平仓失败: {e}")


def calculate_kc_channel(df, ema_period=16, atr_period=16, multiplier=2):
    df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()
    df['atr'] = talib.ATR(
        high=df['high'], 
        low=df['low'], 
        close=df['close'], 
        timeperiod=atr_period
    )
    
    df['kc_upper'] = df['ema'] + multiplier * df['atr']
    df['kc_lower'] = df['ema'] - multiplier * df['atr']
    return df['kc_upper'], df['kc_lower'], df['ema']


def calculate_adx(df, period=12):
    df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=period)
    return df['adx']

def calculate_rsi_with_talib(prices, period=10):

    # 使用TA-Lib计算RSI
    rsi = talib.RSI(prices['close'].values, timeperiod=period)
    
    return rsi


"""斐波那契回撤+正态分布"""
def identify_support_resistance(data, n=450, variance_threshold=0.85):
    global tide
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
            fib_prices = [lowest_low + level * price_range for level in fib_levels]
        else:
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
def normal_distribution( data, variance_threshold=0.85):
    global middle_current_time
    # print(f"5分钟正态分布计算")
    def ensure_shanghai_time(ts):
        ts = pd.to_datetime(ts)
        if ts.tzinfo is None:
            return ts.tz_localize('Asia/Shanghai')
        else: 
            return ts.tz_convert('Asia/Shanghai')
    last_timestamp = ensure_shanghai_time(data.iloc[-1]['timestamp'])
    compare_time = ensure_shanghai_time(middle_current_time)
    data['timestamp'] = data['timestamp'].apply(ensure_shanghai_time)
    if last_timestamp > compare_time:
        normal_data = data[data['timestamp'] > compare_time].copy()
    # print(len(normal_data))
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


"""FB设置信号判断"""
def define_grid_strategy(symbol, slow_his_data, grid_value, grid_pct=1.3):
    global FBside,last_state,middle_current_time,stop_five_transaction
    try:
        if len(slow_his_data) < 130:
            return {
                'is_consolidation': False,
                'signal': 'hold',
                'reason': '数据不足4条'
            }

        n = len(slow_his_data)
        safe_index = -120 if n >= 120 else -(n - 1)  # 确保不越界

        if grid_value == 3:
            strategy = 'KC'
            plan = 'KC'
        else :
            strategy = 'grid_fly'
            plan = 'grid_fly'
            atr_period = 8

            for i in range(33, 9-1, -1):
                if len(slow_his_data) < i:
                    continue

                slow_his_data = slow_his_data.dropna(subset=['close'])  # 删除 NaN
                slow_his_data['close'] = slow_his_data['close'].astype(float)  # 强制转换
                closes = slow_his_data['close'].iloc[-i:].values

                min_close = np.min(closes)
                max_close = np.max(closes)
                fluctuation_pct = (max_close - min_close) / min_close * 100
                is_consolidation = fluctuation_pct < grid_pct
                if fluctuation_pct > 1.5 :
                    stop_five_transaction = True
                # 初始化结果

                result = {
                    'is_consolidation': is_consolidation,
                    'current_price': slow_his_data.iloc[-1]['close'],
                    'fluctuation_pct': fluctuation_pct,
                    'signal': 'hold',
                    'lower_bound': None,
                    'upper_bound': None
                }
                # print(result)

                if is_consolidation:
                    print(f"{strategy}_{symbol}现在为震荡区")
                    if middle_current_time is None:
                        middle_current_time = slow_his_data.iloc[safe_index]['timestamp']
                    lower_bound, upper_bound = normal_distribution(slow_his_data)
                    middle_close1 = slow_his_data.iloc[-1]['close']
                    middle_close2 = slow_his_data.iloc[-2]['close']
                    print(middle_close1,middle_close2,lower_bound,upper_bound)
                    result.update({
                        'lower_bound': lower_bound,
                        'upper_bound': upper_bound
                    })
                    print(f"打印grid_{middle_close1},{middle_close2},{lower_bound},{upper_bound}")
                    # print(type(middle_close2),type(lower_bound))

                    if middle_close1 > lower_bound and middle_close2 <= lower_bound:
                        FBside[symbol] = 1
                        result['signal'] = '1'
                    elif middle_close1 < upper_bound and middle_close2 >= upper_bound:
                        FBside[symbol] = 1
                        result['signal'] = '2'
                    if lower_bound is not None:
                        mode = 1
                    break
                else:
                    mode = 2

        if FBside.get(symbol, 0) == 0: 
            if grid_value == 3 :
                # print(safe_index)
                start_price = float(slow_his_data.iloc[safe_index]['close'])
                end_price = float(slow_his_data.iloc[-1]['close'])
                # print(2)
            else:
                start_price = float(slow_his_data.iloc[safe_index]['close'])
                end_price = float(slow_his_data.iloc[-1]['close'])
            is_uptrend = (end_price > start_price)
            # print(is_uptrend)
            if is_uptrend:
                FBside[symbol] = 1
            else:
                FBside[symbol] = 2

        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        slow_his_data = calculate_atr(slow_his_data, atr_period=atr_period)
        atr_value = slow_his_data['atr'].iloc[-1]
        # print(atr_value)
        # atr_slope = slow_his_data['atr_slope'].iloc[-1]

        if symbol == 'BTC':
            if atr_value > 340:
                dpo, tp = 1.3, 1.02
            elif atr_value > 270:
                dpo, tp = 1.1, 0.78
            elif atr_value > 220:
                dpo, tp = 0.9, 0.54
            elif atr_value > 170:
                dpo, tp = 0.7, 0.37
            elif atr_value <= 170:
                dpo, tp = 0.5, 0.25
        elif symbol == 'ETH':
            if atr_value > 18:
                dpo, tp = 1.3, 1.02
            elif atr_value > 16:
                dpo, tp = 1.1, 0.78
            elif atr_value > 13:
                dpo, tp = 0.9, 0.54
            elif atr_value > 10:
                dpo, tp = 0.7, 0.37
            elif atr_value <= 10:
                dpo, tp = 0.5, 0.25
        elif symbol == 'SOL':
            if atr_value > 1.1:
                dpo, tp = 1.3, 1.02
            elif atr_value > 1:
                dpo, tp = 1.1, 0.78
            elif atr_value > 0.9:
                dpo, tp = 0.9, 0.54
            elif atr_value > 0.7:
                dpo, tp = 0.7, 0.37
            elif atr_value <= 0.7:
                dpo, tp = 0.5, 0.25
        elif symbol == 'DOGE':
            if atr_value > 0.002:
                dpo, tp = 1.3, 1.02
            elif atr_value > 0.0018:
                dpo, tp = 1.1, 0.78
            elif atr_value > 0.0015:
                dpo, tp = 0.9, 0.54
            elif atr_value > 0.0012:
                dpo, tp = 0.7, 0.37
            elif atr_value <= 0.0012:
                dpo, tp = 0.5, 0.25
        elif symbol == 'XRP':
            if atr_value > 0.0189:
                dpo, tp = 1.3, 1.02
            elif atr_value > 0.0176:
                dpo, tp = 1.1, 0.78
            elif atr_value > 0.0151:
                dpo, tp = 0.9, 0.54
            elif atr_value > 0.0137:
                dpo, tp = 0.7, 0.37
            elif atr_value <= 0.0137:
                dpo, tp = 0.5, 0.25
        if dpo is None:
            dpo, tp = 0.5, 0.25


        side = FBside.get(symbol, None)

        base_key = f"{strategy}_{symbol}"
        full_key = f"{base_key}_{plan}_{side}_{mode}_{dpo}_{tp}"
        current_params = f"{plan}_{side}_{mode}_{dpo}_{tp}"

        # 获取缓存中的历史记录（只存储最新的一条）
        last_params = cache.get(base_key)

        if last_params is None:
            # 首次发送信号，并存储参数组合
            set_result = send_mode_signal(
                coin=symbol,
                plan=plan,
                side=side,
                mode=mode,
                dpo=dpo,
                tp=tp
            )
            if set_result:
                # 存储新记录
                cache.set(base_key, current_params, timeout=86400)
                print(f"震荡趋势信号:{full_key}")
                return result
        else:
            if last_params != current_params:
                # 参数变化，发送信号并更新缓存
                set_result = send_mode_signal(
                    coin=symbol,
                    plan=plan,
                    side=side,
                    mode=mode,
                    dpo=dpo,
                    tp=tp
                )
                if set_result:
                    # 更新记录
                    cache.set(base_key, current_params, timeout=86400)
                    print(f"震荡趋势已更新:{full_key}")
                    return result
            else:
                # 参数未变化，不发送信号
                print(f"震荡趋势未变化:{full_key}")
                return result
            
    except Exception as e:
        print(f"FB报错: {e}")


"""KC设置信号判断"""
def define_KC_strategy(symbol, slow_his_data, grid_value):
    global KCside,last_state,middle_current_time
    try:
        if len(slow_his_data) < 139:
            return {
                'is_consolidation': False,
                'signal': 'hold',
                'reason': '数据不足4条'
            }

        n = len(slow_his_data)
        safe_index = -120 if n >= 120 else -(n - 1)  # 确保不越界
        adx_value = 1
        
        if grid_value == 3:
            strategy = 'KC'
            plan = 'KC'
            atr_period = 14
            kc_upper,kc_lower,Medium_track = calculate_kc_channel(slow_his_data)
            # fast_kc_upper,fast_kc_lower,fast_Medium_track = calculate_kc_channel(fast_his_data)
            adx_value = calculate_adx(slow_his_data)
            # rsi_value = calculate_rsi_with_talib(slow_his_data)
            adx_value = adx_value.iloc[-1]
            # rsi_value = rsi_value[-1]
            # print(adx_value)
            # print(rsi_value)
            kc_upper = kc_upper.iloc[-1]
            kc_lower = kc_lower.iloc[-1]
            Medium_track = Medium_track.iloc[-1]
            # print(Medium_track)
            # print(slow_his_data.columns.tolist())
            # print(fast_his_data.columns.tolist())
            last_row = slow_his_data.iloc[-1]
            close1 = last_row['close']
            prev_row = slow_his_data.iloc[-2]
            thiry_row = slow_his_data.iloc[-3]
            close2 = prev_row['close']
            close3 = thiry_row['close']
            Medium_2 = prev_row['ema']
            Medium_3 = thiry_row['ema']
            # print(Medium_2)


            if adx_value >= 20:
                mode = 1
            else:
                mode = 2
            # print(mode)

            if close2 > Medium_2 and close1 > Medium_track :
                KCside[symbol] = 1
            elif close2 < Medium_2 and close1 < Medium_track:
                KCside[symbol] = 2


        # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_value:.3f}")
        
        slow_his_data = calculate_atr(slow_his_data, atr_period=atr_period)
        atr_value = slow_his_data['atr'].iloc[-1]
        # print(atr_value)

        # atr_slope = slow_his_data['atr_slope'].iloc[-1]
        dpo, tp = None, None

        if symbol == 'BTC':
            if atr_value > 340:
                dpo, tp = 1.2, 0.9
            elif atr_value > 270:
                dpo, tp = 1, 0.7
            elif atr_value > 220:
                dpo, tp = 0.8, 0.5
            elif atr_value > 170:
                dpo, tp = 0.6, 0.35
            elif atr_value <= 170:
                dpo, tp = 0.4, 0.2
        elif symbol == 'ETH':
            if atr_value > 18:
                dpo, tp = 1.2, 0.9
            elif atr_value > 16:
                dpo, tp = 1, 0.7
            elif atr_value > 13:
                dpo, tp = 0.8, 0.5
            elif atr_value > 10:
                dpo, tp = 0.6, 0.35
            elif atr_value <= 10:
                dpo, tp = 0.4, 0.2
        elif symbol == 'SOL':
            if atr_value > 1.1:
                dpo, tp = 1.2, 0.9
            elif atr_value > 1:
                dpo, tp = 1, 0.7
            elif atr_value > 0.9:
                dpo, tp = 0.8, 0.5
            elif atr_value > 0.7:
                dpo, tp = 0.6, 0.35
            elif atr_value <= 0.7:
                dpo, tp = 0.4, 0.2
        elif symbol == 'DOGE':
            if atr_value > 0.002:
                dpo, tp = 1.2, 0.9
            elif atr_value > 0.0018:
                dpo, tp = 1, 0.7
            elif atr_value > 0.0015:
                dpo, tp = 0.8, 0.5
            elif atr_value > 0.0012:
                dpo, tp = 0.6, 0.35
            elif atr_value <= 0.0012:
                dpo, tp = 0.4, 0.2
        elif symbol == 'XRP':
            if atr_value > 0.0189:
                dpo, tp = 1.2, 0.9
            elif atr_value > 0.0176:
                dpo, tp = 1, 0.7
            elif atr_value > 0.0151:
                dpo, tp = 0.8, 0.5
            elif atr_value > 0.0137:
                dpo, tp = 0.6, 0.35
            elif atr_value <= 0.0137:
                dpo, tp = 0.4, 0.2
        if dpo is None:
            dpo, tp = 0.4, 0.2

        side = KCside.get(symbol, None)
        # print(side)
        base_key = f"{strategy}_{symbol}"
        full_key = f"{base_key}_{plan}_{side}_{mode}_{dpo}_{tp}"
        current_params = f"{plan}_{side}_{mode}_{dpo}_{tp}"

        # 获取缓存中的历史记录（只存储最新的一条）
        last_params = cache.get(base_key)
        print(f"中轨2:{Medium_2},中轨1:{Medium_track},close3:{close3},close2:{close2},close1:{close1},adx:{adx_value},mode:{mode},atr:{atr_value},dpo:{dpo},tp:{tp}")
        if last_params is None:
            # 首次发送信号，并存储参数组合
            set_result = send_mode_signal(
                coin=symbol,
                plan=plan,
                side=side,
                mode=mode,
                dpo=dpo,
                tp=tp
            )
            if set_result:
                # 存储新记录
                cache.set(base_key, current_params, timeout=86400)
                print(f"震荡趋势信号:{full_key}")
                return adx_value
        else:
            if last_params != current_params:
                # 参数变化，发送信号并更新缓存
                set_result = send_mode_signal(
                    coin=symbol,
                    plan=plan,
                    side=side,
                    mode=mode,
                    dpo=dpo,
                    tp=tp
                )
                if set_result:
                    # 更新记录
                    cache.set(base_key, current_params, timeout=86400)
                    print(f"震荡趋势已更新:{full_key}")
                    return adx_value
            else:
                # 参数未变化，不发送信号
                print(f"震荡趋势未变化:{full_key}")
                return 0

    except Exception as e:
        print(f"KC报错: {e}")