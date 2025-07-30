from django.http import HttpResponse
import pandas as pd
from datetime import datetime, timedelta
from xysz.core import data_fetcher_BG
from xysz.utils.Utils import Utils

pairs = {'BTC', 'ETH', 'SOL', 'DOGE', 'XRP'}
granularity_fast = '1m'
granularity_middle = '5m'
granularity_slow = '15m'
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
    middle_start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    middle_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    slow_start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    slow_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    slow_1_start_date = (datetime.now() - timedelta(days=83)).strftime('%Y-%m-%d')
    slow_1_end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    all_fast_data = {}
    all_middle_data = {}
    # all_slow_data = {}
    
    for pair in pairs:
        symbol = f"{pair}USDT"
        # 获取历史数据
        fast_his_data = data_fetcher_BG.query_klines(symbol, granularity_fast, fast_start_date, fast_end_date)
    
        middle_his_data = data_fetcher_BG.query_klines(symbol, granularity_middle, middle_start_date, middle_end_date)
    
        # slow_his_data = data_fetcher_BG.query_klines(symbol, granularity_slow, slow_start_date, slow_end_date)
        # granularity_slow_1 = data_fetcher_BG.query_klines(symbol, granularity_slow_1, slow_1_start_date, slow_1_end_date)
        
        # 转换数据类型
        fast_his_data = Utils.str_to_numeric(fast_his_data)
        middle_his_data = Utils.str_to_numeric(middle_his_data)
        # slow_his_data = Utils.str_to_numeric(slow_his_data)
        # granularity_slow_1 = Utils.str_to_numeric(granularity_slow_1)
        
        # 添加日期列
        fast_his_data['date'] = pd.to_datetime(fast_his_data['timestamp'])
        middle_his_data['date'] = pd.to_datetime(middle_his_data['timestamp'])
        # slow_his_data['date'] = pd.to_datetime(slow_his_data['timestamp'])
        # granularity_slow_1['date'] = pd.to_datetime(granularity_slow_1['timestamp'])
        # 保存到字典中
        all_fast_data[pair] = fast_his_data
        all_middle_data[pair] = middle_his_data
        # all_slow_data[pair] = slow_his_data
    
    return all_fast_data,all_middle_data


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
    # print("\nall_slow_data:")
    # print(all_slow_data[symbol].tail(2))
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
    slow_interval_to_remove = slow_last_three[slow_last_three['timestamp_ms'] % 900000 != 0]
    
    # 删除不符合时间间隔的行（如果有）
    all_slow_data[symbol] = slow_data.drop(slow_interval_to_remove.index)

    print(f"{symbol} 数据删除成功")
    # print("\nall_middle_data:")
    # print(all_middle_data[symbol].tail(2))
    print("\nall_slow_data:")
    print(all_slow_data[symbol].tail(3).to_string())

    return all_slow_data


# def fetch_redis_data(
#     host: str = '8.216.32.13',
#     port: int = 6379,
#     password: str = 'yyz135246',
#     db: int = 0
# ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], Dict[str, float]]:
#     """
#     从Redis获取5m/15m/lastprice数据并分别返回
    
#     返回:
#         Tuple[
#             Dict[str, pd.DataFrame],  # 5m K线数据 {交易对: DataFrame}
#             Dict[str, pd.DataFrame],  # 15m K线数据 {交易对: DataFrame}
#             Dict[str, float]         # 最新价格 {交易对: 价格}
#         ]
#     """
#     # 连接Redis
#     r = redis.Redis(
#         host=host,
#         port=port,
#         password=password,
#         db=db,
#         decode_responses=True  # 自动解码为字符串
#     )
    
#     data_5m = {}
#     data_15m = {}
#     last_prices = {}

#     try:
#         # 第一步：获取所有lastprice并转为float
#         for key in r.keys('bitget_data_*_lastprice'):
#             try:
#                 symbol = key.split('_')[2]
#                 last_prices[symbol] = float(r.get(key))
#             except (ValueError, TypeError, AttributeError):
#                 print(f"忽略无效lastprice: {key}")
#                 continue

#         # 第二步：处理5m和15m数据
#         for key in r.keys('bitget_data_*_5m') + r.keys('bitget_data_*_15m'):
#             symbol = key.split('_')[2]
#             timeframe = key.split('_')[-1]
            
#             # 解析K线数据
#             raw_data = r.get(key)
#             if not raw_data:
#                 continue
                
#             try:
#                 # 转换为DataFrame
#                 df = pd.DataFrame(
#                     json.loads(raw_data),
#                     columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
#                 )
#                 # 处理时间戳
#                 df['datetime'] = pd.to_datetime(pd.to_numeric(df['timestamp']),unit='ms')
#                 df.set_index('datetime', inplace=True)
                
#                 # 按周期存储
#                 if timeframe == '5m':
#                     data_5m[symbol] = df
#                 elif timeframe == '15m':
#                     data_15m[symbol] = df
                    
#             except json.JSONDecodeError:
#                 print(f"无效JSON数据: {key}")
#                 continue
                
#     finally:
#         r.close()
        
#     return data_5m, data_15m


# def query_main():
#     try:
#         middle_his_data, slow_his_data = cof_main()
#         # env = BacktestEnv(middle_his_data, slow_his_data)

#         strategy_flag = True  # 初始状态为 True，允许策略执行
#         ws, data_queue = start_multiple_subscriptions()
#         last_data_time = time.monotonic()  # 记录开始时间
#         while strategy_flag:
#             if not data_queue.empty():
#                 # 有数据进来，更新时间戳
#                 last_data_time = time.monotonic()
#                 strategy_flag = False
#                 kline_data = data_queue.get_nowait()
#                 # kline_data = data_queue.get()
#                 kline_data_df = pd.DataFrame([kline_data])
#                 ws_type = kline_data_df['symbol'][0]
#                 ws_type = ws_type.replace("USDT", "")
#                 slow_keys  = list(slow_his_data.keys())

#                 # 检查三个类型是否一致且在允许列表中
#                 if ws_type in slow_keys:
#                     # 动态访问对应交易对的数据列
#                     middle_cols = kline_data_df[middle_his_data[ws_type].columns.intersection(kline_data_df.columns)]
#                     slow_cols = kline_data_df[slow_his_data[ws_type].columns.intersection(kline_data_df.columns)]
#                     # 索引处理
#                     middle_cols.index = [middle_his_data[ws_type].index[-1] + 1]
#                     slow_cols.index = [slow_his_data[ws_type].index[-1] + 1]
#                     return ws_type, middle_his_data[ws_type], slow_his_data[ws_type]

#                     # slow_his_data = calculate_atr(slow_his_data[ws_type], atr_period=8)

#                 # sign1 = env.set_signals(middle_his_data=middle_his_data, slow_his_data=slow_his_data)

#                 # if sign1 == 1:

#                 #     # print(slow_his_data.tail(3))
#                 #     # print(middle_his_data.tail(3))
#                 #     middle_his_data['timestamp'] = pd.to_datetime(middle_his_data['timestamp'], errors='coerce', utc=True)
#                 #     middle_his_data['timestamp'] = middle_his_data['timestamp'].dt.tz_convert('Asia/Shanghai')
#                 #     middlelast_three_rows = middle_his_data.tail(3)
#                 #     middlelast_three_rows['timestamp_ms'] = middlelast_three_rows['timestamp'].astype(int) // 10**6
#                 #     middle_to_remove = middlelast_three_rows[middlelast_three_rows['timestamp_ms'] % 300000 != 0]
#                 #     middle_his_data = middle_his_data.drop(middle_to_remove.index)

#                 #     slow_his_data['timestamp'] = pd.to_datetime(slow_his_data['timestamp'], errors='coerce', utc=True)
#                 #     slow_his_data['timestamp'] = slow_his_data['timestamp'].dt.tz_convert('Asia/Shanghai')
#                 #     last_three_rows = slow_his_data.tail(3)
#                 #     last_three_rows['timestamp_ms'] = last_three_rows['timestamp'].astype(int) // 10**6
#                 #     slow_to_remove = last_three_rows[last_three_rows['timestamp_ms'] % 900000 != 0]
#                 #     slow_his_data = slow_his_data.drop(slow_to_remove.index)

#                 #     strategy_flag = True
#                 #     # current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 去掉最后3位微秒，只保留毫秒
#                 #     # print(f"当前时间（毫秒）：{current_time}")

#             else:
#                 # 检查是否超过15分钟无数据（15分钟 = 900秒）
#                 if time.monotonic() - last_data_time > 900:
#                     strategy_flag = False
#                     try:
#                         ws.on_close(ws.ws, 1000, "25分钟内未接收到数据，停止执行策略。")
#                     except Exception as e:
#                         print(f"关闭 WebSocket 失败：{e}")

#     except Exception as e:
#         return HttpResponse(f"报错: {e}")
    
#     return HttpResponse(f"已完成")
