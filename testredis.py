import pytz
import redis
import pandas as pd
import json
from datetime import datetime
from typing import Tuple, Dict

from xysz.main_biget import cof_main

def fetch_redis_data(
    host: str = '8.216.32.13',
    port: int = 6379,
    password: str = 'yyz135246',
    db: int = 0
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], Dict[str, float]]:
    """
    从Redis获取5m/15m/lastprice数据并分别返回
    
    返回:
        Tuple[
            Dict[str, pd.DataFrame],  # 5m K线数据 {交易对: DataFrame}
            Dict[str, pd.DataFrame],  # 15m K线数据 {交易对: DataFrame}
            Dict[str, float]         # 最新价格 {交易对: 价格}
        ]
    """
    # 连接Redis
    r = redis.Redis(
        host=host,
        port=port,
        password=password,
        db=db,
        decode_responses=True  # 自动解码为字符串
    )
    
    data_5m = {}
    data_15m = {}
    last_prices = {}

    try:
        # 第一步：获取所有lastprice并转为float
        for key in r.keys('bitget_data_*_lastprice'):
            try:
                symbol = key.split('_')[2]
                last_prices[symbol] = float(r.get(key))
            except (ValueError, TypeError, AttributeError):
                print(f"忽略无效lastprice: {key}")
                continue

        # 第二步：处理5m和15m数据
        for key in r.keys('bitget_data_*_5m') + r.keys('bitget_data_*_15m'):
            symbol = key.split('_')[2]
            timeframe = key.split('_')[-1]
            
            # 解析K线数据
            raw_data = r.get(key)
            if not raw_data:
                continue
                
            try:
                # 转换为DataFrame
                df = pd.DataFrame(
                    json.loads(raw_data),
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
                )
                # 处理时间戳
                df['datetime'] = pd.to_datetime(pd.to_numeric(df['timestamp']),unit='ms')
                df.set_index('datetime', inplace=True)
                
                # 按周期存储
                if timeframe == '5m':
                    data_5m[symbol] = df
                elif timeframe == '15m':
                    data_15m[symbol] = df
                    
            except json.JSONDecodeError:
                print(f"无效JSON数据: {key}")
                continue
                
    finally:
        r.close()
        
    return data_5m, data_15m


# 使用示例
if __name__ == "__main__":
    # 获取数据
    kline_5m, kline_15m, last_prices = fetch_redis_data()
    # all_middle_data, all_slow_data = fetch_redis_data()
    symbol = 'btc'
    # # 打印BTC的5分钟K线
    
    # print("BTC 5分钟K线:")
    # print(kline_5m.get('btc', pd.DataFrame()).tail(2))
    
    # # 打印ETH的15分钟K线
    # print("\nETH 15分钟K线:")
    slow_keys = list(kline_5m.keys())
    print(len(kline_15m.get(symbol, pd.DataFrame())))
    print(kline_15m.get(symbol, pd.DataFrame()))
    # print(len(kline_5m.get(symbol, pd.DataFrame())))
    # print(kline_5m.get(symbol, pd.DataFrame()))

    # 打印最新价格
    print("\n最新价格:")
    for symbol, price in last_prices.items():
        print(f"{symbol.upper()}: {price}")





