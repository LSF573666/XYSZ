import requests
import pandas as pd
from datetime import datetime

def fetch_klines(exchange='binance', symbol='BTC', interval='1m', 
                 start_time=None, end_time=None, limit=2000, get_more=0):
    """
    从服务器API获取K线数据
    
    参数:
    exchange: 交易所名称 ('binance' 或 'okx')
    symbol: 交易对符号 (如 'BTC', 'ETH'等)
    interval: K线周期 ('1m', '5m', '15m', '30m')
    start_time: 开始时间戳(毫秒)
    end_time: 结束时间戳(毫秒)
    limit: 返回记录数(默认2000，仅在get_more=0时生效)
    get_more: 是否返回全部数据(1=是，0=否)
    
    返回:
    pandas DataFrame 包含K线数据
    """
    # API端点
    url = "http://47.236.144.131:8000/api/klines/fetch"
    
    # 查询参数
    params = {
        'exchange': exchange,
        'symbol': symbol,
        'interval': interval,
        'limit': limit,
        'get_more': get_more
    }
    
    # 添加可选的时间参数
    if start_time:
        params['start_time'] = start_time
    if end_time:
        params['end_time'] = end_time
    
    try:
        # 发送GET请求
        response = requests.get(url, params=params)
        response.raise_for_status()  # 检查请求是否成功
        
        # 解析JSON响应
        data = response.json()
        
        # 转换为DataFrame
        df = pd.DataFrame(data['data'])
        
        # 转换时间戳为可读格式
        if 'open_time' in df.columns:
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        if 'close_time' in df.columns:
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            
        return df
    
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

# 示例用法
if __name__ == "__main__":
    # 获取最近2000条BTC的1分钟K线数据
    df = fetch_klines(exchange='binance', symbol='BTC', interval='1m')
    
    if df is not None:
        print(f"获取到 {len(df)} 条记录")
        print(df.head())
        
        # 保存到CSV文件
        df.to_csv('klines_data.csv', index=False)
        print("数据已保存到 klines_data.csv")
    else:
        print("未能获取数据")   