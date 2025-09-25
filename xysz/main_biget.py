from django.http import HttpResponse
import pandas as pd
from datetime import datetime, timedelta
from xysz.core import data_fetcher_BG
from xysz.utils.Utils import Utils

pairs = {'BTC', 'ETH', 'SOL', 'DOGE', 'XRP'}
granularity_fast = '1m'
granularity_middle = '15m'
granularity_slow = '5m'
granularity_slow_1 = '1H'
instType = "USDT-FUTURES"

# def calculate_atr(data, atr_period=None):
#     """计算 ATR 和斜率"""
#     data['atr'] = talib.ATR(data['high'], data['low'], data['close'], timeperiod=atr_period)
#     data['atr_slope'] = data['atr'].diff() / data['atr'].shift(1)
    
#     return data

def safe_convert_to_datetime(ts):
    """安全转换混合类型的时间戳"""
    try:
        # 尝试解析带时区的字符串
        if isinstance(ts, str) and "+" in ts:
            return pd.to_datetime(ts, format='%Y-%m-%d %H:%M:%S%z')
        # 处理不带时区的字符串
        elif isinstance(ts, str):
            dt = pd.to_datetime(ts, errors='coerce')
            return dt.tz_localize('Asia/Shanghai') if not pd.isna(dt) else pd.NaT
        # 处理已为Timestamp类型的情况
        elif isinstance(ts, pd.Timestamp):
            return ts.tz_convert('Asia/Shanghai') if ts.tz is not None else ts.tz_localize('Asia/Shanghai')
        else:
            return pd.NaT
    except:
        return pd.NaT

def cof_main():

    fast_start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    fast_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    middle_start_date = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d')
    middle_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    slow_start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    slow_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    slow_1_start_date = (datetime.now() - timedelta(days=83)).strftime('%Y-%m-%d')
    slow_1_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    all_fast_data = {}
    all_middle_data = {}
    all_slow_data = {}
    
    for pair in pairs:
        symbol = f"{pair}USDT"
        # 获取历史数据
        fast_his_data = data_fetcher_BG.query_klines(symbol, granularity_fast, fast_start_date, fast_end_date)
    
        middle_his_data = data_fetcher_BG.query_klines(symbol, granularity_middle, middle_start_date, middle_end_date)
    
        slow_his_data = data_fetcher_BG.query_klines(symbol, granularity_slow, slow_start_date, slow_end_date)
        # granularity_slow_1 = data_fetcher_BG.query_klines(symbol, granularity_slow_1, slow_1_start_date, slow_1_end_date)
        
        # 转换数据类型
        fast_his_data = Utils.str_to_numeric(fast_his_data)
        middle_his_data = Utils.str_to_numeric(middle_his_data)
        slow_his_data = Utils.str_to_numeric(slow_his_data)
        # granularity_slow_1 = Utils.str_to_numeric(granularity_slow_1)
        
        # 添加日期列
        fast_his_data['date'] = pd.to_datetime(fast_his_data['timestamp'])
        middle_his_data['date'] = pd.to_datetime(middle_his_data['timestamp'])
        slow_his_data['date'] = pd.to_datetime(slow_his_data['timestamp'])
        # granularity_slow_1['date'] = pd.to_datetime(granularity_slow_1['timestamp'])
        # 保存到字典中
        all_fast_data[pair] = fast_his_data
        all_middle_data[pair] = middle_his_data
        all_slow_data[pair] = slow_his_data
    
    return all_fast_data, all_middle_data, all_slow_data

def data_delet_middle(middle_his_data,all_middle_data,symbol):

    middle_his_data['timestamp'] = middle_his_data['timestamp'].apply(safe_convert_to_datetime)

    # 打印最后一个时间戳的dtype
    # print("\n最后一个时间戳的dtype:")
    # print(type(middle_his_data['timestamp'].iloc[-1]))
    # print(all_middle_data[symbol].tail(2))
    middle_data = middle_his_data

    # 处理 middle 数据
    middle_data['timestamp'] = pd.to_datetime(middle_data['timestamp'], errors='coerce', utc=True)
    middle_data['timestamp'] = middle_data['timestamp'].dt.tz_convert('Asia/Shanghai')

    # 检查后三行是否有重复时间戳，并保留每组重复时间戳的最后一行
    middle_data = middle_data.drop_duplicates(subset=['timestamp'], keep='last')
    
    # 原有时间间隔检查（保持不变）
    middle_last_three = middle_data.tail(3)
    middle_last_three['timestamp_ms'] = middle_last_three['timestamp'].astype(int) // 10**6
    slow_interval_to_remove = middle_last_three[middle_last_three['timestamp_ms'] % 900000 != 0]
    
    # 删除不符合时间间隔的行（如果有）
    all_middle_data[symbol] = middle_data.drop(slow_interval_to_remove.index)
    
    # print("\nall_middle_data:")
    # print(all_middle_data[symbol].tail(2))
    return all_middle_data

def data_delet_slow(slow_his_data,all_slow_data,symbol):

    # 打印最后一个时间戳的dtype
    # print("\n最后一个时间戳的dtype:")
    # print("\n准备删除:")
    # print(type(middle_his_data['timestamp'].iloc[-1]))
    # print(slow_his_data.tail(3))
    slow_data = slow_his_data

    # 处理 slow 数据
    slow_data['timestamp'] = pd.to_datetime(slow_data['timestamp'], errors='coerce', utc=True)
    slow_data['timestamp'] = slow_data['timestamp'].dt.tz_convert('Asia/Shanghai')
    
    # 检查后三行是否有重复时间戳，并保留每组重复时间戳的最后一行
    slow_data = slow_data.drop_duplicates(subset=['timestamp'], keep='last')
    
    # 原有时间间隔检查（保持不变）
    slow_last_three = slow_data.tail(3)
    slow_last_three['timestamp_ms'] = slow_last_three['timestamp'].astype(int) // 10**6
    slow_interval_to_remove = slow_last_three[slow_last_three['timestamp_ms'] % 300000 != 0]
    
    # 删除不符合时间间隔的行（如果有）
    all_slow_data[symbol] = slow_data.drop(slow_interval_to_remove.index)

    # print(f"{symbol} 数据删除成功")
    # print("\nall_slow_data:")
    # print(all_slow_data[symbol].tail(3).to_string())

    return all_slow_data
