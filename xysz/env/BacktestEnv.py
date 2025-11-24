# import threading
import pandas as pd
from datetime import datetime
import talib
from xysz.config import get_api_balance
import time
from xysz.env.MockAccount import MockAccount
from django.core.cache import cache
from typing import Dict
import numpy as np
from xysz.tests import send_mode_signal
import csv
import os

pd.set_option('mode.chained_assignment', None)

middle_current_time = None
result = None
FBside = {}
KCside = {}
KCsmartside = {}
KCsamtrside = {}
balance = get_api_balance()
account = MockAccount(initial_balance=balance)


def calculate_ema(df, period=None):
    # 确保价格数据是数值类型
    prices = pd.to_numeric(df['close'], errors='coerce')
    # 计算EMA
    ema_values = talib.EMA(prices, timeperiod=period)
    return ema_values
    
def append_to_csv(file_path, data):
    """追加数据到CSV文件"""
    with open(file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 检查文件是否为空（需要先判断文件是否存在）
        if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
            writer.writerow(data)
        else:
            writer.writerow(data)

def calculate_trading_params(fast_his_data, symbol, plan, exchange, time, mode, period=None, atr_period=None):
    global account
    # 计算斐波那契和ATR水平
    fib_0, fib_1, fib_2, fib_3, fib_4, fib_5, fib_6, fast_his_data = calculate_atr_fibonacci_levels(
        fast_his_data, period=period, atr_period=atr_period
    )
    fast_atr = fast_his_data['atr'].iloc[-1]
    fast_atr2 = fast_his_data['atr'].iloc[-2]
    fast_atr3 = fast_his_data['atr'].iloc[-3]
    atr_slope = fast_his_data['atr_slope'].iloc[-1]
    # 止盈
    TP_VALUES = {
        'BTC': [0.18, 0.193, 0.205],
        'ETH': [0.23, 0.244, 0.258],
        'SOL': [0.31, 0.324, 0.338],
        'XRP': [0.385, 0.415, 0.445],
        'DOGE': [0.460, 0.496, 0.532]
        }
    # 止损
    SL_VALUES = {
        'BTC': [0.27, 0.2895, 0.3075],
        'ETH': [0.345, 0.366, 0.387],
        'SOL': [0.465, 0.486, 0.507],
        'XRP': [0.5775, 0.6225, 0.6675],
        'DOGE': [0.69, 0.744, 0.798]
        }
    # 网格大小
    DPO_VALUES_1 = {
        'BTC': [0.2, 0.3, 1],
        'ETH': [0.262, 0.389, 1.292],
        'SOL': [0.31, 0.458, 1.51],
        'XRP': [0.375, 0.569, 1.926],
        'DOGE': [0.44, 0.668, 2.265]
        }
    DPO_VALUES_2 = [0.2, 0.2, 0.2]

    # 初始化默认值
    dpo, tp, sl = None, None, None
    dpo2 = None
    atr_sl, avgrange_sl = None, None
    multiple2 = 1.3
    # 根据ATR值确定交易参数
    if symbol in TP_VALUES:
        if mode == 2:
            dpo_values = DPO_VALUES_1[symbol]
        else:
            dpo_values = DPO_VALUES_2
        tp_values = TP_VALUES[symbol]
        sl_values = SL_VALUES[symbol]
        
        if fast_atr > fib_4:
            dpo, tp, atr_sl = dpo_values[2], tp_values[2], sl_values[2]  # 等级4
            dpo2 = 0.5
        elif fast_atr > fib_3:
            dpo, tp, atr_sl = dpo_values[1], tp_values[1], sl_values[1]  # 等级3
            dpo2 = 0.1
        elif fast_atr > fib_2:
            dpo, tp, atr_sl = dpo_values[0], tp_values[0], sl_values[0]  # 等级2
            dpo2 = 0.15
        elif fast_atr < fib_2:
            dpo, tp, atr_sl = dpo_values[0], tp_values[0], sl_values[0]  # 等级2
            dpo2 = 0.15

    # # 设置默认值
    # if dpo is None:
    #     dpo, tp, atr_sl = 0.25, 0.25, 0.25
    if mode == 2:
        dpo2 = dpo2
        # if dpo2 is None:
        #     dpo2 = dpo
    else:
        dpo2 = 0
    
    # 特殊条件处理
    if fast_atr > fib_5 or fast_atr < fib_1 or (fast_atr < fast_atr2 < fast_atr3 and fast_atr > fib_4):
        dpo = 10
        tp = 0.5
        dpo2 = 10
    if fib_2 * 0.7 > fast_atr or fast_atr > fib_4 * 1.3:
        multiple2 = 0.8

    tp = round((fast_atr / close_price) * 100, 3)
    
    # 计算平均价差SL
    avg_range = calculate_avg_price_range(fast_his_data, period=10)
    # print(f"{plan}_{exchange}_{symbol}平均价差{avg_range}")
    # print(f"{exchange}, {symbol}, {time}, {fib_0}, {fib_1}, {fib_2}, {fib_3}, {fib_4}, {fib_5}, {fib_6}")
    
    # 获取持仓信息计算SL
    position_info = account.get_strategy_positions(strategy=plan, exchange=exchange, symbol=symbol)
    position_data = position_info.get(exchange, {}).get(symbol)
    
    if position_data:
        entry_price = float(position_data.get("entry_price", 0))
        entry_price = float(entry_price)
        # print(f"{exchange}买入价格{entry_price}")
        avgrange_sl = avg_range / entry_price 
    
    # 确定最终的SL值
    if avgrange_sl is not None:
        sl = atr_sl if atr_sl > avgrange_sl else avgrange_sl
    else:
        sl = atr_sl
    
    return {
        'dpo': dpo,
        'dpo2':dpo2,
        'tp': tp,
        'sl': sl,
        'fast_atr': fast_atr,
        'atr_slope': atr_slope,
        'multiple2' : multiple2
    }

def calculate_avg_price_range(df, period=None):
    """计算最后period根K线的平均价差"""
    return (df['high'].tail(period) - df['low'].tail(period)).sum() / period

def calculate_atr(data, atr_period=None):
    """ATR值计算"""
    data['atr'] = talib.ATR(data['high'], data['low'], data['close'], timeperiod=atr_period)
    data['atr_slope'] = data['atr'].diff() / data['atr'].shift(1)
    
    return data

def calculate_kc_channel(df, ema_period=None, atr_period=None, multiplier=1):
    """KC通道计算"""
    df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()
    df['atr'] = talib.ATR(
        high=df['high'], 
        low=df['low'], 
        close=df['close'], 
        timeperiod=atr_period)
    df['kc_upper'] = df['ema'] + multiplier * df['atr']
    df['kc_lower'] = df['ema'] - multiplier * df['atr']
    return df['kc_upper'], df['kc_lower'], df['ema'], df['atr'] 

def calculate_volume_ratio(df, period=5, column_name='volume_ratio'):
    """成交量计算"""
    avg_volume = df['volume'].rolling(window=period, min_periods=1).mean()
    # 计算量比并添加到DataFrame
    df[column_name] = df['volume'] / avg_volume
    return df

def calculate_adx(df, period=14):
    """ADX计算"""
    df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=period)
    return df['adx']

def calculate_rsi_with_talib(prices, period=None):
    """RSI计算"""
    rsi = talib.RSI(prices['close'].values, timeperiod=period)
    return rsi

def calculate_vi_manual(prices, period=None):
    """VI计算"""
    high = prices['high'].values
    low = prices['low'].values
    close = prices['close'].values
    
    tr = np.zeros(len(prices))
    vm_plus = np.zeros(len(prices))
    vm_minus = np.zeros(len(prices))

    for i in range(1, len(prices)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        vm_plus[i] = abs(high[i] - low[i-1])
        vm_minus[i] = abs(low[i] - high[i-1])

    sum_tr = np.zeros(len(prices))
    sum_vm_plus = np.zeros(len(prices))
    sum_vm_minus = np.zeros(len(prices))

    for i in range(period, len(prices)):
        sum_tr[i] = np.sum(tr[i-period+1:i+1])
        sum_vm_plus[i] = np.sum(vm_plus[i-period+1:i+1])
        sum_vm_minus[i] = np.sum(vm_minus[i-period+1:i+1])

    # 安全计算 VI，避免除以 0
    plus_vi = np.divide(sum_vm_plus, sum_tr, out=np.zeros_like(sum_vm_plus), where=(sum_tr != 0))
    minus_vi = np.divide(sum_vm_minus, sum_tr, out=np.zeros_like(sum_vm_minus), where=(sum_tr != 0))
    
    # 计算 VI_ratio
    vi_ratio = np.ones(len(prices))
    for i in range(len(prices)):
        if minus_vi[i] > 0:
            vi_ratio[i] = plus_vi[i] / minus_vi[i]
        else:
            vi_ratio[i] = 1.0

    return plus_vi, minus_vi, vi_ratio
    # return vi_ratio

def calculate_atr_fibonacci_levels(ohlc_data: pd.DataFrame, 
                                  period: int = None, 
                                  atr_period: int = None) -> Dict[str, float]:
    """使用斐波那契回撤值移动计算atr等级"""
    # 确保数据足够计算
    if len(ohlc_data) < period + atr_period:
        raise ValueError(f"数据不足，需要至少 {period + atr_period} 根K线，当前只有 {len(ohlc_data)} 根")
    # 获取最近的period根K线
    recent_data = ohlc_data.tail(period).copy()
    # 计算ATR
    recent_data['atr'] = talib.ATR(recent_data['high'], recent_data['low'], recent_data['close'], 
                                  timeperiod=atr_period)
    recent_data['atr_slope'] = recent_data['atr'].diff() / recent_data['atr'].shift(1)
    
    # 找到ATR的最低点和最高点
    atr_min = recent_data['atr'].min()
    atr_max = recent_data['atr'].max()
    
    atr_range = atr_max - atr_min

    fib_0 = atr_min                     # 0%
    fib_1 = atr_min + atr_range * 0.236   # 23.6%
    fib_2 = atr_min + atr_range * 0.382   # 38.2%
    fib_3 = atr_min + atr_range * 0.5       # 50%
    fib_4 = atr_min + atr_range * 0.618   # 61.8%
    fib_5 = atr_min + atr_range * 0.786   # 78.6%
    fib_6 = atr_max               # 100%
    
    return fib_0,fib_1,fib_2,fib_3,fib_4,fib_5,fib_6,recent_data


def execute_buy_action(result, exchange, symbol, buy_date, close, grid=None):
    global middle_current_time
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
    dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S")
    formatted_time = dt.strftime("%H:%M")
    current_price = close
    position_percentage = 0.2
    # account.buy(symbol, current_price, position_side=position_side,position_percentage=position_percentage)
    # 输出持仓信息和盈亏
    # BTC_info = account.get_position_info(symbol, position_side=position_side)
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
        # ps = round(BTC_info['position_size'],3)
        # if ps < 0.01 or ps > 10:
        ps = 0.02
        # 执行买入操作
        # order_request = upload_coin_reminder(
        #         coin_platform=exchange,
        #         coin_name=symbol,
        #         reminder_name=reminder,
        #         side=side,
        #         price=formatted_price,
        #         timetype=timetype
        #     )
        # order_request = send_trading_signal(
        #         type_value="buysell",
        #         coin=symbol,
        #         coinPlatform=exchange,
        #         time_frame=time_interval,
        #         plan_name=reminder,
        #         side=side,
        #         price=formatted_price,
        #         time2=formatted_time
        #     )
        # send_stock_alert(symbol, time_interval, reminder, f"{open_side} {formatted_time},{formatted_price}")
        # if order_request:
        #     print(reminder,symbol,side,formatted_price)
            # print(f"已下单: {order_request}")
            # has_traded_in_block = True  # 标记已交易
    except Exception as e:
        print(f"okx下单失败: {e}")
    # print(f"当前账户总余额: {account.get_account_summary()}")

def execute_sell_action(result, exchange, symbol, time, buy_date, close, grid=None):
    """处理卖出操作卖出"""
    if result is None:
        return
    
    if grid == 0:
        timetype = "15分钟"
        reminder = "grid_fly"
    elif grid in (1, 2):
        timetype = "15分钟"
        reminder = "grid_fly"
    elif grid == 3 :
        timetype = "1分钟"
        reminder = "KC"
        selltype = "TP"
    elif grid == 4 :
        timetype = "1分钟"
        reminder = "kc_smart"
        selltype = "TP"
    # print(f"本地卖出信号触发：日期={buy_date}, 卖出价格={close}") 
    dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S")
    formatted_time = dt.strftime("%H:%M")
    formatted_price = f"{close:.2f}"
    sell_side = 'CLOSE_SHORT' if result == 1 else 'CLOSE_LONG'
    sell_side1 = '平空' if result == 1 else '平多'
    # try:
        # request = upload_coin_reminder(
        #         coin_platform=exchange,
        #         coin_name=symbol,
        #         reminder_name=reminder,
        #         side=sell_side,
        #         price=formatted_price,
        #         timetype=timetype
        #     )
        # order_request = send_trading_signal(
        #         type_value="buysell",
        #         coin=symbol,
        #         coinPlatform=exchange,
        #         time_frame=time,
        #         plan_name=reminder,
        #         side=sell_side,
        #         selltype=selltype,
        #         price=formatted_price,
        #         time2=formatted_time
        #     )
        # send_stock_alert(symbol, time_interval, reminder, f"{sell_side1} {formatted_time},{formatted_price}")
        # if order_request:
        #     has_traded_in_block = True  # 标记已交易
    # except Exception as e:
    #     print(f"okx平仓失败: {e}")
"""斐波那契回撤"""
def support_resistance(data, n=480):
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
        # top_supports = sorted(level_prices)[:3]
        # top_resistances = sorted(level_prices, reverse=True)[:3]
        # median_line = sorted(level_prices, reverse=True)[-4]
        return level_prices
    
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
def define_grid_strategy(exchange, symbol, fast_his_data, middle_his_data, grid_value, grid_pct=1.3):
    global FBside,middle_current_time,account
    try:
        if len(middle_his_data) < 130:
            return {
                'is_consolidation': False,
                'signal': 'hold',
                'reason': '数据不足4条'
            }

        n = len(middle_his_data)
        safe_index = -120 if n >= 120 else -(n - 1)  # 确保不越界
        time = 900
        if grid_value == 3:
            plan = 'KC'
        else :
            plan = 'grid_fly'
            atr_period = 8
            last_row = fast_his_data.iloc[-1]
            close1 = last_row['close']
            signal_time = last_row['timestamp']

            for i in range(33, 9-1, -1):
                if len(middle_his_data) < i:
                    continue

                middle_his_data = middle_his_data.dropna(subset=['close'])  # 删除 NaN
                middle_his_data['close'] = middle_his_data['close'].astype(float)  # 强制转换
                closes = middle_his_data['close'].iloc[-i:].values
                close1 = middle_his_data.iloc[-1]['close']

                min_close = np.min(closes)
                max_close = np.max(closes)
                fluctuation_pct = (max_close - min_close) / min_close * 100
                is_consolidation = fluctuation_pct < grid_pct
                # if fluctuation_pct > 1.5 :
                #     stop_five_transaction = True
                # 初始化结果

                result = {
                    'is_consolidation': is_consolidation,
                    'current_price': middle_his_data.iloc[-1]['close'],
                    'fluctuation_pct': fluctuation_pct,
                    'signal': 'hold',
                    'lower_bound': None,
                    'upper_bound': None
                }
                # print(result)
                multiple = 1
                if is_consolidation:
                    # print(f"{plan}_{symbol}现在为震荡区")
                    multiple = 1
                    if middle_current_time is None:
                        middle_current_time = middle_his_data.iloc[safe_index]['timestamp']
                    lower_bound, upper_bound = normal_distribution(middle_his_data)
                    middle_close1 = middle_his_data.iloc[-1]['close']
                    middle_close2 = middle_his_data.iloc[-2]['close']
                    # print(middle_close1,middle_close2,lower_bound,upper_bound)
                    result.update({
                        'lower_bound': lower_bound,
                        'upper_bound': upper_bound
                    })
                    # print(f"打印grid_{middle_close1},{middle_close2},{lower_bound},{upper_bound}")
                    # print(type(middle_close2),type(lower_bound))

                    if middle_close1 > lower_bound and middle_close2 <= lower_bound:
                        FBside[symbol] = 1
                        result['signal'] = '1'
                    elif middle_close1 < upper_bound and middle_close2 >= upper_bound:
                        FBside[symbol] = 2
                        result['signal'] = '2'
                    if lower_bound is not None:
                        mode = 1
                    break
                else:
                    multiple = 2
                    mode = 2

            if FBside.get(symbol, 0) == 0: 
                if grid_value == 3 :
                    # print(safe_index)
                    start_price = float(middle_his_data.iloc[safe_index]['close'])
                    end_price = float(middle_his_data.iloc[-1]['close'])
                    # print(2)
                else:
                    start_price = float(middle_his_data.iloc[safe_index]['close'])
                    end_price = float(middle_his_data.iloc[-1]['close'])
                is_uptrend = (end_price > start_price)
                # print(is_uptrend)
                if is_uptrend:
                    FBside[symbol] = 1
                else:
                    FBside[symbol] = 2
            multiple2 = 1
            params = calculate_trading_params(
                fast_his_data=fast_his_data,
                symbol=symbol,
                plan=plan,
                exchange=exchange,
                time=time,
                mode=mode,
                period=480,
                atr_period=8
            )
            multiple2 = params['multiple2']
            dpo = params['dpo']
            dpo2 = params['dpo2']
            tp = params['tp']
            sl = params['sl']
            side = FBside.get(symbol, None)
            base_key = f"{exchange}_{plan}_{symbol}_{time}"
            full_key = f"{base_key}_{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}_{close1}"
            current_params = f"{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}_{close1}"
    
            # 获取缓存中的历史记录（只存储最新的一条）
            last_params = cache.get(base_key)
            today = datetime.now().date()
            csv_file = f"./gf_signal{today}_{time}.csv"
            if last_params is None:
                # 首次发送信号，并存储参数组合
                set_result = send_mode_signal(
                    coinPlatform = exchange,
                    marketType = "FUTURES",
                    coin=symbol,
                    plan=plan,
                    time=time,
                    side=side,
                    mode=mode,
                    dpo=dpo,
                    dpo2=dpo2,
                    tp=tp,
                    sl=sl,
                    slPrice=1,
                    multiple=multiple,
                    multiple2=multiple2
                )
                if set_result:
                    # 存储新记录
                    cache.set(base_key, current_params, timeout=3600)
                    # print(f"震荡趋势信号:{full_key}")
                    append_to_csv(csv_file, [signal_time, full_key])
                    account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                    return 1
            else:
                if last_params != current_params:
                    # 参数变化，发送信号并更新缓存
                    set_result = send_mode_signal(
                            coinPlatform = exchange,
                            marketType = "FUTURES",
                            coin=symbol,
                            plan=plan,
                            time=time,
                            side=side,
                            mode=mode,
                            dpo=dpo,
                            dpo2=dpo2,
                            tp=tp,
                            sl=sl,
                            slPrice=1,
                            multiple=multiple,
                            multiple2=multiple2
                        )
                    if set_result:
                        # 更新记录
                        cache.set(base_key, current_params, timeout=3600)
                        # print(f"震荡趋势已更新:{full_key}")
                        append_to_csv(csv_file, [signal_time, full_key])
                        account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                        return 1
                else:
                    # 参数未变化，不发送信号
                    # print(f"震荡趋势未变化:{full_key}")
                    return 2
            
    except Exception as e:
        print(f"FB_{exchange}报错: {e}")
        return 3


"""KC设置信号判断"""
def define_KC_strategy(exchange, symbol, time, fast_his_data, grid_value):
    global KCside,account
    try:
        # print(exchange, symbol, len(fast_his_data), grid_value)

        if len(fast_his_data) < 139:
            return {
                'is_consolidation': False,
                'signal': 'hold',
                'reason': '数据不足4条'
            }

        n = len(fast_his_data)

        safe_index = -120 if n >= 120 else -(n - 1)  # 确保不越界
        adx_last = 1
        mode = None
        dpo, tp = None, None
        multiple = 1
        multiple2 = 1
        
        if grid_value == 3:
            plan = 'KC'
            kc_upper,kc_lower,Medium_track = calculate_kc_channel(fast_his_data, ema_period=100, atr_period=14)
            # fast_kc_upper,fast_kc_lower,fast_Medium_track = calculate_kc_channel(fast_his_data)
            adx_value = calculate_adx(fast_his_data)
            # rsi_value = calculate_rsi_with_talib(fast_his_data)
            # last_three_adx = adx_value.iloc[-3:]
            adx_last = float(adx_value.iloc[-1])
            if adx_last < 25 :
                mode = 1
                multiple = 1
            elif 25 < adx_last < 30 :
                multiple = 3
                mode = 1
            else:
                multiple = 2
                mode = 2

            if mode is None:
                if adx_last > 27 :
                    mode = 1
                else:
                    mode = 2

            # print(adx_value)
            # print(rsi_value)
            kc_upper = kc_upper.iloc[-1]
            kc_lower = kc_lower.iloc[-1]
            Medium_track = Medium_track.iloc[-1]
            # print(Medium_track)
            # print(fast_his_data.columns.tolist())
            # print(fast_his_data.columns.tolist())
            last_row = fast_his_data.iloc[-1]
            close1 = last_row['close']
            signal_time = last_row['timestamp']
            prev_row = fast_his_data.iloc[-2]
            thiry_row = fast_his_data.iloc[-3]
            four_row = fast_his_data.iloc[-4]
            close2 = prev_row['close']
            close3 = thiry_row['close']
            close4 = four_row['close']
            Medium_2 = prev_row['ema']
            Medium_3 = thiry_row['ema']
            Medium_4 = four_row['ema']
            # print(f"{plan}时间戳打印:{exchange}, {symbol}, {time},{signal_time}")

            # print(Medium_2)

            if close2 > Medium_2 and close1 > Medium_track :
                KCside[symbol] = 1
            elif close2 < Medium_2 and close1 < Medium_track:
                KCside[symbol] = 2

            # print(f"{symbol}肯特:{current_timestamp},close2:{close2:.3f}, close1:{close1:.3f},下轨:{kc_lower:.3f},中轨:{Medium_track:.3f},上轨:{kc_upper:.3f},ADX:{adx_last:.3f}")

            fast_his_data = calculate_volume_ratio(fast_his_data, period=480)
            volume_ratio = fast_his_data['volume_ratio'].iloc[-1]
            volume = fast_his_data['volume'].iloc[-1]

            params = calculate_trading_params(
                fast_his_data=fast_his_data,
                symbol=symbol,
                plan=plan,
                exchange=exchange,
                time=time,
                mode=mode,
                period=480,
                atr_period=14
            )

            dpo = params['dpo']
            dpo2 =params['dpo2']
            tp = params['tp']
            sl = params['sl']
            fast_atr = params['fast_atr']
            multiple2 = params['multiple2']

            # if adx_last > 35 :
            #     dpo, tp = 0.3, 0.35
            side = KCside.get(symbol, None)
            # print(close1,Medium_track)
            if side is None:
                if close1 > Medium_track :
                    side = 1
                elif close1 < Medium_track:
                    side = 2
            # print(side)
            base_key = f"{exchange}_{plan}_{symbol}_{time}_{close1}"
            full_key = f"{base_key}_{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}"
            current_params = f"{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}"

            # 获取缓存中的历史记录（只存储最新的一条）
            last_params = cache.get(base_key)

            # print(fast_atr)
            log_message = f"KC_{exchange}_{symbol}_{time}_{signal_time},中轨2:{Medium_2},中轨1:{Medium_track},close3:{close3},close2:{close2},close1:{close1},adx:{adx_last},atr:{fast_atr},量比:{volume_ratio},成交量{volume}"
            print(log_message)

            # CSV文件路径
            today = datetime.now().date()
            csv_file = f"./KCsignal{today}_{time}.csv"
            set_result = send_mode_signal(
                    coinPlatform = exchange,
                    marketType = "FUTURES",
                    coin=symbol,
                    plan=plan,
                    time=time,
                    side=side,
                    mode=mode,
                    dpo=dpo,
                    dpo2=dpo2,
                    tp=tp,
                    sl=sl,
                    slPrice=1,
                    multiple=multiple,
                    multiple2=multiple2
                )
            if last_params is None:
                
                if set_result:
                    # 存储新记录
                    cache.set(base_key, current_params, timeout=3600)
                    # print(f"震荡趋势信号:{full_key}")
                    append_to_csv(csv_file, [full_key, signal_time, Medium_4, Medium_3, Medium_2, Medium_track, close4, close3, close2, close1, adx_last, fast_atr, volume_ratio, volume])
                    account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                    return exchange, adx_last
            else:
                if last_params != current_params:
                    # print(f"震荡趋势有变化")
                    if (side == 1 and ((mode == 1 and volume_ratio < 0.8) or (mode == 2 and volume_ratio < 1.2))):
                        set_result = send_mode_signal(
                                coinPlatform = exchange,
                                marketType = "FUTURES",
                                coin=symbol,
                                plan=plan,
                                time=time,
                                side=side,
                                mode=mode,
                                dpo=dpo,
                                dpo2=dpo2,
                                tp=tp,
                                sl=sl,
                                slPrice=1,
                                multiple=multiple,
                                multiple2=multiple2
                            )
                        if set_result:
                            # 更新记录
                            cache.set(base_key, current_params, timeout=3600)
                            # print(f"震荡趋势已更新:{full_key}")
                            append_to_csv(csv_file, [full_key, signal_time, Medium_4, Medium_3, Medium_2, Medium_track, close4, close3, close2, close1, adx_last, fast_atr, volume_ratio, volume])
                            account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                            return exchange, adx_last

                    elif (side == 2 and ((mode == 1 and volume_ratio < 0.8) or (mode == 2 and volume_ratio < 1.2))):
                        set_result = send_mode_signal(
                                coinPlatform = exchange,
                                marketType = "FUTURES",
                                coin=symbol,
                                plan=plan,
                                time=time,
                                side=side,
                                mode=mode,
                                dpo=dpo,
                                dpo2=dpo2,
                                tp=tp,
                                sl=sl,
                                slPrice=1,
                                multiple=multiple,
                                multiple2=multiple2
                            )
                        if set_result:
                            # 更新记录
                            cache.set(base_key, current_params, timeout=3600)
                            # print(f"震荡趋势已更新:{full_key}")
                            append_to_csv(csv_file, [full_key, signal_time, Medium_4, Medium_3, Medium_2, Medium_track, close4, close3, close2, close1, adx_last, fast_atr, volume_ratio, volume])
                            account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                            return exchange, adx_last
                else:
                    # 参数未变化，不发送信号
                    # print(f"震荡趋势未变化:{full_key}")
                    return exchange, adx_last
    except Exception as e:
        print(f"KC{symbol}_{time}报错: {e}")
        return exchange, adx_last



"""KC_smart设置信号判断"""
def define_KC_smartstrategy(exchange, symbol, time, fast_his_data, grid_value):
    global KCsmartside,account
    try:
        # print(symbol,len(fast_his_data), len(fast_his_data), grid_value)

        if len(fast_his_data) < 139:
            return {
                'is_consolidation': False,
                'signal': 'hold',
                'reason': '数据不足4条'
            }

        n = len(fast_his_data)

        safe_index = -120 if n >= 120 else -(n - 1)  # 确保不越界
        adx_last = 1
        mode = None
        dpo, tp = None, None
        multiple = 1
        multiple2 = 1
        
        if grid_value == 4:
            plan = 'kc_smart'
            atr_period = 10
            kc_upper,kc_lower,Medium_track = calculate_kc_channel(fast_his_data, ema_period=100, atr_period=14, multiplier=1)
            # fast_kc_upper,fast_kc_lower,fast_Medium_track = calculate_kc_channel(fast_his_data)
            adx_value = calculate_adx(fast_his_data)
            # rsi_value = calculate_rsi_with_talib(fast_his_data)
            # last_three_adx = adx_value.iloc[-2:]
            adx_last = float(adx_value.iloc[-1])
            # all_greater_than_27 = all(last_three_adx > 20)
            # all_less_than_22 = all(last_three_adx < 20)
            # if all_less_than_22:
            #     mode = 2
            # elif all_greater_than_27:
            #     mode = 1

            if adx_last < 25 :
                mode = 1
                multiple = 1
            elif 25 < adx_last < 30 :
                multiple = 3
                mode = 1
            else:
                multiple = 2
                mode = 2

            # print(adx_value)
            # print(rsi_value)
            kc_upper = kc_upper.iloc[-1]
            kc_lower = kc_lower.iloc[-1]
            Medium_track = Medium_track.iloc[-1]
            # print(Medium_track)
            # print(fast_his_data.columns.tolist())
            # print(fast_his_data.columns.tolist())
            last_row = fast_his_data.iloc[-1]
            close1 = last_row['close']
            signal_time = last_row['timestamp']
            prev_row = fast_his_data.iloc[-2]
            thiry_row = fast_his_data.iloc[-3]
            four_row = fast_his_data.iloc[-4]
            close2 = prev_row['close']
            close3 = thiry_row['close']
            close4 = four_row['close']
            Medium_2 = prev_row['ema']
            Medium_3 = thiry_row['ema']
            Medium_4 = four_row['ema']
            # print(Medium_2)
            if mode == 2:
                if close2 > Medium_2 and close1 > Medium_track :
                    KCsmartside[symbol] = 1
                elif close2 < Medium_2 and close1 < Medium_track:
                    KCsmartside[symbol] = 2
            elif mode == 1:
                if close1 > kc_upper :
                    KCsmartside[symbol] = 1
                elif close1 < kc_lower :
                    KCsmartside[symbol] = 2

            params = calculate_trading_params(
                fast_his_data=fast_his_data,
                symbol=symbol,
                plan=plan,
                exchange=exchange,
                time=time,
                mode=mode,
                period=480,
                atr_period=14
            )

            dpo = params['dpo']
            dpo2 =params['dpo2']
            tp = params['tp']
            sl = params['sl']
            fast_atr = params['fast_atr']
            multiple2 = params['multiple2']

            side = KCsmartside.get(symbol, None)
            if side is None:
                if close1 > Medium_track :
                    side = 1
                elif close1 < Medium_track:
                    side = 2
            # print(side)

            base_key = f"{exchange}_{plan}_{symbol}_{time}"
            full_key = f"{base_key}_{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}"
            current_params = f"{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}"

            # 获取缓存中的历史记录（只存储最新的一条）
            last_params = cache.get(base_key)

            # print(fast_atr)
            log_message = f"KCsmart_{exchange}_{symbol}_{time}_{signal_time},中轨2:{Medium_2},中轨1:{Medium_track},close3:{close3},close2:{close2},close1:{close1},adx:{adx_last},atr:{fast_atr}"
            print(log_message)

            # CSV文件路径
            today = datetime.now().date()
            csv_file = f"./kcsmartsignal{today}_{time}.csv"

            if last_params is None:
                # 首次发送信号，并存储参数组合
                set_result = send_mode_signal(
                    coinPlatform = exchange,
                    marketType = "FUTURES",
                    coin=symbol,
                    plan=plan,
                    time=time,
                    side=side,
                    mode=mode,
                    dpo=dpo,
                    dpo2=dpo2,
                    tp=tp,
                    sl=sl,
                    slPrice=1,
                    multiple=multiple,
                    multiple2=multiple2
                )
                if set_result:
                    # 存储新记录
                    cache.set(base_key, current_params, timeout=3600)
                    # print(f"震荡趋势信号:{full_key}")
                    append_to_csv(csv_file, [full_key, signal_time, Medium_4, Medium_3, Medium_2, Medium_track, close4, close3, close2, close1, adx_last, fast_atr])
                    account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                    return exchange, adx_last
            else:
                if last_params != current_params:
                    # print(f"震荡趋势有变化")
                    set_result = send_mode_signal(
                        coinPlatform = exchange,
                        marketType = "FUTURES",
                        coin=symbol,
                        plan=plan,
                        time=time,
                        side=side,
                        mode=mode,
                        dpo=dpo,
                        dpo2=dpo2,
                        tp=tp,
                        sl=sl,
                        slPrice=1,
                        multiple=multiple,
                        multiple2=multiple2
                    )
                    if set_result:
                        # 更新记录
                        cache.set(base_key, current_params, timeout=3600)
                        # print(f"震荡趋势已更新:{full_key}")
                        append_to_csv(csv_file, [full_key, signal_time, Medium_4, Medium_3, Medium_2, Medium_track, close4, close3, close2, close1, adx_last, fast_atr])
                        account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                        return exchange, adx_last
                else:
                    # 参数未变化，不发送信号
                    # print(f"震荡趋势未变化:{full_key}")
                    return exchange, adx_last

    except Exception as e:
        print(f"KCsmart_{exchange}_{symbol}_{time}报错: {e}")
        return exchange, 1



"""KC_samtr设置信号判断"""
def define_KC_samtrstrategy(exchange, symbol, time, fast_data, grid_value):
    global KCsamtrside,account
    try:
        # print(symbol,len(fast_data), len(fast_data), grid_value)

        if len(fast_data) < 139:
            return {
                'is_consolidation': False,
                'signal': 'hold',
                'reason': '数据不足139条'
            }

        adx_last = 1
        mode, side = None, None
        dpo, tp, sl, dpo2 = None, None, None, None
        rsi_period, kc_period, atr_period = None, None, None
        multiple = 1
        multiple2 = 1
        
        if grid_value == 6:
            
            period_config = {
                60: {'rsi_period': 6, 'kc_period': 30, 'atr_period': 5},
                300: {'rsi_period': 8, 'kc_period': 8, 'atr_period': 7},
                900: {'rsi_period': 9, 'kc_period': 4, 'atr_period': 8},
                3600: {'rsi_period': 10, 'kc_period': 2, 'atr_period': 10}
            }

            if time in period_config:
                config = period_config[time]
                rsi_period = config['rsi_period']
                kc_period = config['kc_period']
                atr_period = config['atr_period']
            plan = 'KC_samtr'

            # 7个支撑压力位
            level_prices = support_resistance(fast_data)
            kc_upper, kc_lower, Medium_track, atr_values = calculate_kc_channel(fast_data, ema_period=kc_period, atr_period=atr_period, multiplier=1)
            kc_upper = kc_upper.iloc[-1]
            kc_lower = kc_lower.iloc[-1]
            Medium_track = Medium_track.iloc[-1]
            adx_value = calculate_adx(fast_data, period=10)
            rsi_values = calculate_rsi_with_talib(fast_data, period=rsi_period)
            plus_vi, minus_vi,vi_ratios = calculate_vi_manual(fast_data,period=14)
            minus_vi1 = minus_vi[-1]
            minus_vi2 = minus_vi[-2]
            minus_vi3 = minus_vi[-3]
            plus_vi1 = plus_vi[-1]
            plus_vi2 = plus_vi[-2]
            plus_vi3 = plus_vi[-3]
            vi_ratio1 = vi_ratios[-1]
            vi_ratio2 = vi_ratios[-2]
            vi_ratio3 = vi_ratios[-3]
            adx_last = float(adx_value.iloc[-1])
            adx_last2 = float(adx_value.iloc[-2])
            adx_last3 = float(adx_value.iloc[-3])
            rsi_value = rsi_values[-1]
            rsi_value2 = rsi_values[-2]
            rsi_value3 = rsi_values[-3]
            current_atr = atr_values.iloc[-1]    # 当前值
            prev_atr = atr_values.iloc[-2]       # 前一天值
            three_atr = atr_values.iloc[-3]  # 倒数第三天值
            atr_recent = atr_values.tail(480)
            # 计算ATR的极值
            max_atr = atr_recent.max()    # 最近480个周期的ATR最大值
            min_atr = atr_recent.min()    # 最近480个周期的ATR最小值
            # print(Medium_track)
            # print(fast_data.columns.tolist())
            # print(fast_data.columns.tolist())
            last_row = fast_data.iloc[-1]
            close1 = last_row['close']
            signal_time = last_row['timestamp']
            prev_row = fast_data.iloc[-2]
            thiry_row = fast_data.iloc[-3]
            close2 = prev_row['close']
            Medium_2 = prev_row['ema']

            if current_atr < min_atr + 0.3 * (max_atr - min_atr):
                dpo = 10
                tp = 0.5
            elif current_atr > min_atr + 0.85 * (max_atr - min_atr):
                dpo = 10
                tp = 0.5

            # 震荡趋势判断
            vi_decreasing = (vi_ratio1 < vi_ratio2) and (vi_ratio2 < vi_ratio3)
            adx_decreasing = (adx_last < adx_last2) and (adx_last2 < adx_last3)
            rsi_decreasing = (rsi_value < rsi_value2) and (rsi_value2 < rsi_value3)
            atr_decreasing = (current_atr < prev_atr) and (prev_atr < three_atr)
            # 判断所有指标是否都递减
            all_decreasing = vi_decreasing and adx_decreasing and rsi_decreasing and atr_decreasing
            if (0.85 <= vi_ratio1 <= 1.15) and all_decreasing:
                mode = 1
            else:
                mode = 2

            # 原趋势震荡判断逻辑
            # if adx_last > 25 and plus_vi1 > minus_vi1:
            #     mode = 2
            # elif 25 < adx_last < 30 :
            #     mode = 1
            # else:
            #     mode = 1
            
            # 小许的多空判断逻辑
            # if rsi_value < 50 and plus_vi1 < minus_vi1 :
            #     KCsmartside[symbol] = 2
            # elif rsi_value > 50 and plus_vi1 > minus_vi1 :
            #     KCsmartside[symbol] = 1

            if symbol == 'BTC' :
                if (atr_decreasing and 
                        current_atr > three_atr * 1.09) and rsi_value >= 58 and adx_last > 26:
                    dpo2 = 0.5
                    dpo = 0.1
                    tp = 0.5
                    multiple = 3
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else:
                        KCsmartside[symbol] = 1
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.06) and rsi_value >= 63 and adx_last > 30:
                    dpo2 = 0.2
                    dpo = 0.15
                    tp = 0.3
                    multiple = 2
                    if close1 > kc_upper :
                        KCsmartside[symbol] = 1
                    elif close1 < kc_lower:
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.02) and rsi_value >= 67 and adx_last > 32:
                    dpo2 = 0.1
                    dpo2 = 0.2
                    tp = 0.2
                    multiple = 1
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else:
                        KCsmartside[symbol] = 2
                elif (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.96) and rsi_value >= 64 and adx_last > 28:
                    dpo2 = 0.1
                    dpo2 = 0.2
                    multiple = 1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr < three_atr * 0.93) and rsi_value >= 52 and adx_last > 17:
                    dpo2 = 0.1
                    dpo2 = 0.2
                    multiple = 1
                    tp = 0.2
                    if close1 < Medium_track :
                        KCsmartside[symbol] = 2
                    else :
                        KCsmartside[symbol] = 1

            elif symbol == 'ETH' :
                if (atr_decreasing and 
                        current_atr > three_atr * 1.09) and rsi_value >= 60 and adx_last > 27:
                    dpo2 = 0.5
                    dpo = 0.1
                    tp = 0.5
                    multiple = 3
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.06) and rsi_value >= 66 and adx_last > 33:
                    dpo2 = 0.2
                    dpo = 0.15
                    multiple = 2
                    tp = 0.3
                    if close1 > kc_upper :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.06) and rsi_value >= 69 and adx_last > 35:
                    dpo2 = 0.1
                    dpo = 0.1
                    multiple = 1
                    tp = 0.2
                    if close1 > kc_upper :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr < three_atr * 1.02) and rsi_value >= 70 and adx_last > 34:
                    multiple = 1
                    dpo2 = 0.1
                    dpo = 0.1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr < three_atr * 1.02) and rsi_value >= 68 and adx_last > 32:
                    multiple = 1
                    dpo = 0.1
                    dpo2 = 0.1
                    tp = 0.2
                    if close1 < Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.96) and rsi_value >= 65 and adx_last > 30:
                    dpo = 0.1
                    dpo2 = 0.1
                    multiple = 1
                    tp = 0.2
                    if close1 < Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
            elif symbol == 'SOL' :
                if (atr_decreasing and 
                        current_atr > three_atr * 1.09) and rsi_value >= 40 and adx_last > 29:
                    dpo2 = 0.5
                    dpo = 0.1
                    tp = 0.5
                    multiple = 3
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.06) and rsi_value >= 35 and adx_last > 31:
                    dpo2 = 0.2
                    dpo = 0.15
                    multiple = 2
                    tp = 0.3
                    if close1 > kc_upper :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.02) and rsi_value >= 32 and adx_last > 27:
                    dpo2 = 0.1
                    dpo = 0.2
                    multiple = 1
                    tp = 0.2
                    if close1 > kc_upper :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.96) and rsi_value >= 36 and adx_last > 27:
                    dpo2 = 0.1
                    dpo = 0.5
                    multiple = 1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.93) and rsi_value >= 42 and adx_last > 21:
                    dpo2 = 0.1
                    dpo = 0.5
                    multiple = 1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr < three_atr * 0.91) and rsi_value >= 48 and adx_last > 16:
                    dpo2 = 0.1
                    multiple = 1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 2
                    else :
                        KCsmartside[symbol] = 1
            elif symbol == 'XRP' :
                if (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.93) and rsi_value >= 38 and adx_last > 18:
                    dpo2 = 0.5
                    dpo = 0.1
                    tp = 0.5
                    multiple = 3
                    if close1 < kc_lower :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.02) and rsi_value >= 45 and adx_last > 17:
                    multiple = 2
                    dpo2 = 0.2
                    dpo = 0.15
                    tp = 0.3
                    if close1 < Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.05) and rsi_value >= 50 and adx_last > 20:
                    dpo2 = 0.1
                    dpo = 0.2
                    multiple = 1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr < three_atr * 1.09) and rsi_value >= 56 and adx_last > 26:
                    dpo2 = 0.1
                    dpo = 0.5
                    multiple = 1
                    tp = 0.2
                    if close1 > kc_upper :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.96) and rsi_value >= 53 and adx_last > 23:
                    dpo2 = 0.1
                    dpo = 0.5
                    multiple = 1
                    tp = 0.2
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2

            elif symbol == 'DOGE' :
                if (current_atr < prev_atr and 
                        prev_atr < three_atr and 
                        current_atr < three_atr * 0.93) and rsi_value >= 38 and adx_last > 15:
                    dpo2 = 0.5
                    dpo = 0.1
                    tp = 0.3
                    multiple = 3
                    if  close1 < kc_lower :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                elif (atr_decreasing and 
                        current_atr > three_atr * 1.02) and rsi_value >= 50 and adx_last > 20:
                    dpo2 = 0.2
                    dpo = 0.15
                    multiple = 2
                    tp = 0.5
                    if close1 > Medium_track :
                        KCsmartside[symbol] = 1
                    else :
                        KCsmartside[symbol] = 2
                # elif (current_atr > prev_atr and 
                #         prev_atr > three_atr and 
                #         current_atr > three_atr * 1.05) and rsi_value >= 50 and close1 > Medium_track and adx_last > 20:
                #     dpo2 = 0.1
                #     tp = 0.2
            sl = 1
            if dpo is None:
                dpo = 0.2
                dpo = 0.1
                sl = 1
                # sl传价格过去 到新的接口.
                tp = 0.2
            side = KCsmartside.get(symbol, None)
            if side is None:
                if close1 > Medium_track :
                    side = 1
                elif close1 < Medium_track:
                    side = 2
            # print(side)

            base_key = f"{exchange}_{plan}_{symbol}_{time}"
            full_key = f"{base_key}_{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}"
            current_params = f"{plan}_{mode}_{side}_{dpo}_{dpo2}_{tp}_{sl}_{multiple}"

            # 获取缓存中的历史记录（只存储最新的一条）
            last_params = cache.get(base_key)

            # print(fast_atr)
            log_message = f"KCsamtr{exchange}_{symbol}_{time}_{signal_time},中轨2:{Medium_2},中轨1:{Medium_track},close2:{close2},close1:{close1},adx:{adx_last},atr:{current_atr}"
            print(log_message)

            # CSV文件路径
            today = datetime.now().date()
            csv_file = f"./kcsamtrsignal{today}_{time}.csv"

            if last_params is None:
                # 首次发送信号，并存储参数组合
                set_result = send_mode_signal(
                    coinPlatform = exchange,
                    marketType = "FUTURES",
                    coin=symbol,
                    plan=plan,
                    time=time,
                    side=side,
                    mode=mode,
                    dpo=dpo,
                    dpo2=dpo2,
                    tp=tp,
                    sl=sl,
                    slPrice=1,
                    multiple=multiple,
                    multiple2=multiple2
                )
                if set_result:
                    # 存储新记录
                    cache.set(base_key, current_params, timeout=3600)
                    # print(f"震荡趋势信号:{full_key}")
                    append_to_csv(csv_file, [full_key, signal_time, Medium_2, Medium_track, close2, close1, adx_last, current_atr])
                    account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                    return exchange, adx_last
            else:
                if last_params != current_params:
                    # print(f"震荡趋势有变化")
                    set_result = send_mode_signal(
                            coinPlatform = exchange,
                            marketType = "FUTURES",
                            coin=symbol,
                            plan=plan,
                            time=time,
                            side=side,
                            mode=mode,
                            dpo=dpo,
                            dpo2=dpo2,
                            tp=tp,
                            sl=sl,
                            slPrice=1,
                            multiple=multiple,
                            multiple2=multiple2
                        )
                    if set_result:
                        # 更新记录
                        cache.set(base_key, current_params, timeout=3600)
                        # print(f"震荡趋势已更新:{full_key}")
                        append_to_csv(csv_file, [full_key, signal_time, Medium_2, Medium_track, close2, close1, adx_last, current_atr])
                        account.buy(plan, exchange, symbol, close1, side, 0.01, 2)
                        return exchange, adx_last
                else:
                    # 参数未变化，不发送信号
                    # print(f"震荡趋势未变化:{full_key}")
                    return exchange, adx_last

    except Exception as e:
        print(f"KCsamtr{exchange}_{symbol}_{time}报错: {e}")
        return exchange, 1