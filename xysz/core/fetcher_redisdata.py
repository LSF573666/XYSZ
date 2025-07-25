# import pandas as pd
# import json
# from typing import Tuple, Dict

# # 假设你有一个utils/redis_utils.py文件
# from biget.celery import redis_client

# def fetch_redis_data() -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], Dict[str, float]]:
#     """
#     从Redis获取5m/15m/lastprice数据并分别返回
    
#     返回:
#         Tuple[
#             Dict[str, pd.DataFrame],  # 5m K线数据 {交易对: DataFrame}
#             Dict[str, pd.DataFrame],  # 15m K线数据 {交易对: DataFrame}
#             Dict[str, float]         # 最新价格 {交易对: 价格}
#         ]
#     """
#     # 使用项目统一的Redis连接
#     print(f"尝试连接外部redis")
#     r = redis_client()
#     print(f"连接外部redis成功")

    
#     data_5m = {}
#     data_15m = {}

#     try:

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
#                 df['datetime'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
#                 df.set_index('datetime', inplace=True)
                
#                 # 按周期存储
#                 if timeframe == '5m':
#                     data_5m[symbol] = df
#                 elif timeframe == '15m':
#                     from xysz.tasks import FB_strategy, KC_strategy
#                     data_15m[symbol] = df
#                     FB_strategy.delay(data_15m[symbol])

                    
#             except json.JSONDecodeError:
#                 print(f"无效JSON数据: {key}")
#                 continue
                
#     finally:
#         # 如果你的get_redis_connection返回的是连接池，不需要关闭
#         # 如果是单个连接，可能需要关闭
#         pass
        
#     return data_5m, data_15m 