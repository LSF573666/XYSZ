import time
import pytz
import redis
import pandas as pd
import json
from datetime import datetime
from typing import Tuple, Dict

from xysz.main_biget import cof_main

def fetch_redis_data(
    host: str = '47.84.194.2',
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
    r.ping()
    print("连接成功！")
    
    data_5m = {}
    data_15m = {}
    last_prices = {}

    try:
        keys = r.keys('*')
        print(f"共找到 {len(keys)} 个键")
        filtered_keys = [key for key in keys if not key.endswith(('setMode', 'lastprice','spot'))]
        print(f"过滤后，剩余 {len(filtered_keys)} 个键")
        # print(filtered_keys)
        
        for i, key in enumerate(keys, 1):
            print(f"\n=== 键 {i}/{len(keys)}: {key} ===")
            
            # 获取键的类型
            key_type = r.type(key)
            print(f"类型: {key_type}")
            value = r.get(key)
            print(f"值: {value}")
            
            # 尝试解析JSON
            try:
                json_value = json.loads(value)
                print(f"JSON解析: {json.dumps(json_value, ensure_ascii=False, indent=2)}")
            except:
                pass

        target_exchanges = {'bitget', 'binance', 'okx'}
        target_symbols = {'btc', 'eth', 'sol', 'doge', 'xrp'}
        target_intervals = {'1m', '5m', '15m', '1h'}
        start_time = time.time()
        total_tasks = 0
        successful_tasks = 0
        # 异步 SCAN
        cursor = 0
        pattern = "*_data_*_*"
        keys = []
        while True:
            cursor, partial_keys = r.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(partial_keys)
            if cursor == 0:
                break
        print(f"找到 {len(keys)} 个符合格式的键")
        tasks_to_dispatch = []
        for key in keys:
            if key.endswith(('setMode', 'lastprice', 'spot')):
                continue
            parts = key.split('_')
            if len(parts) != 4:
                continue
            exchange, _, symbol, interval = parts
            exchange, symbol, interval = exchange.lower(), symbol.lower(), interval.lower()
            if (exchange in target_exchanges and
                symbol in target_symbols and
                interval in target_intervals):
                value = r.get(key)
                if not value:
                    continue
                try:
                    data = json.loads(value)
                    tasks_to_dispatch.append({
                        'exchange': exchange,
                        'symbol': symbol,
                        'interval': interval,
                        'data': data
                    })
                except json.JSONDecodeError:
                    print(f"JSON解析失败: {key}")
                
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





