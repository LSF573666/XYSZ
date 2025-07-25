# data_fetcher.py

import requests, os
import pandas as pd
import time, datetime
import pytz
from xysz.utils.Utils import Utils
from xysz.config import BIGET_API_URL, LOCAL_DATA_DIR

timezone_s = 'Asia/Shanghai'

def get_historical_klines(symbol, granularity, start_str, end_str=None, limit=500):
    base_url = f"{BIGET_API_URL}/api/v2/mix/market/candles"
    all_data = []
    end_time = end_str
    retry_attempts = 3

    while True:
        try:
            params = {
                'symbol': symbol,
                'granularity': granularity,
                'limit': limit
            }
            if end_str:
                params['endTime'] = end_str
                
            url = f"{base_url}?symbol={params['symbol']}&granularity={params['granularity']}&endTime={end_time}&limit={params['limit']}&productType=USDT-FUTURES"
            response = requests.get(url)
            data = response.json()
            
            if not data:
                print(f"No data fetched: {data}")
                break
                        
            start_timestamp = int(data['data'][0][0])  # 先转成 int
            end_timestamp = int(data['data'][-1][0])
            start_dt = Utils.timestamp_to_date_string(start_timestamp / 1000, tz=pytz.timezone(timezone_s))
            end_dt = Utils.timestamp_to_date_string(end_timestamp / 1000, tz=pytz.timezone(timezone_s))
            print(f"当前获取到{symbol}{granularity}数据：{start_dt} - {end_dt}...")
            
            all_data.extend(data['data'])
            
            # Update start_time for next batch
            end_time = Utils.adjust_timestamp(end_timestamp, granularity,limit)

            # Check if we have reached the end_time
            if start_str and int(data['data'][0][0]) <= start_str:
                break
            
            # Sleep to avoid hitting API rate limits
            time.sleep(Utils.generate_random_number(1) + 1)
            retry_attempts = 3
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if retry_attempts > 0:
                print(f"Error fetching data: {e}. Retrying... ({retry_attempts} attempts left)")
                retry_attempts -= 1
                time.sleep(Utils.generate_random_number(1))
                continue
            else:
                print(f"Error fetching data: {e}. Maximum retry attempts reached.")
                break
        except Exception as e:
            print(f"Unexpected error fetching data: {e}")
            break
        
    _columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'Denominated_Coin_Volume']

    if all_data:
        df = pd.DataFrame(all_data, columns=_columns)
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype('int64'), unit='ms').dt.tz_localize('UTC').dt.tz_convert(timezone_s)
        # 按时间戳降序排序（最新的时间在前）
        df = df.sort_values('timestamp', ascending=True).reset_index(drop=True)
        return df
    else:
        return pd.DataFrame(columns=_columns)

def query_klines(symbol, granularity, start_date, end_date=None, sort=True):
    current_time = datetime.datetime.now()
    start_timestamp = int(pd.Timestamp(start_date).timestamp() * 1000)
    end_timestamp = int(pd.Timestamp(end_date).timestamp() * 1000) if end_date else int(current_time.timestamp() * 1000)

    if end_date and pd.Timestamp(end_date) > current_time:
        end_date = current_time
        end_timestamp = int(current_time.timestamp() * 1000)

    current_year = pd.Timestamp(start_date).year
    end_year = pd.Timestamp(end_date).year if end_date else current_time.year

    all_data = []
    years_to_fetch = []

    for year in range(current_year, end_year + 1):
        filename = f"{symbol}_{granularity}_{year}.csv"
        df = load_from_csv(filename)
        if df is not None:
            all_data.append(df)
        else:
            years_to_fetch.append(year)

    if all_data:
        combined_df = pd.concat(all_data).drop_duplicates().reset_index(drop=True)
        # combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp'])
        # 确保时间戳转换为UTC格式
        combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp'], utc=True)

        # 如果需要本地时区，可以转换
        combined_df['timestamp'] = combined_df['timestamp'].dt.tz_convert('Asia/Shanghai')

    else:
        combined_df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    if not combined_df.empty:
        min_local_timestamp = combined_df['timestamp'].min()
        max_local_timestamp = combined_df['timestamp'].max()

        if min_local_timestamp > pd.to_datetime(start_date).tz_localize(timezone_s):
            missing_start = pd.to_datetime(start_date)
        else:
            missing_start = max_local_timestamp + pd.Timedelta(milliseconds=1)

        if max_local_timestamp < pd.to_datetime(end_date).tz_localize(timezone_s):
            missing_end = pd.to_datetime(end_date) if end_date else current_time
        else:
            missing_end = min_local_timestamp - pd.Timedelta(milliseconds=1)
    else:
        missing_start = pd.to_datetime(start_date)
        missing_end = pd.to_datetime(end_date) if end_date else current_time

    if years_to_fetch:
        for year in years_to_fetch:
            fetch_start = pd.Timestamp(f'{year}-01-01')
            fetch_end = pd.Timestamp(f'{year}-12-31')
            
            if year == current_year:
                fetch_start = max(fetch_start, pd.to_datetime(start_date))
            if year == end_year:
                fetch_end = min(fetch_end, pd.to_datetime(end_date) if end_date else current_time)
            
            # # 处理时间戳列（修复第一个警告）
            # df['timestamp'] = pd.to_datetime(df['timestamp'].astype('int64'), unit='ms') \
            #                    .dt.tz_localize('UTC') \
            #                    .dt.tz_convert(timezone_s)
            
            # 合并数据（修复第二个警告）
            missing_data = get_historical_klines(symbol, granularity,int(fetch_start.timestamp() * 1000), int(fetch_end.timestamp() * 1000))
            
            if not missing_data.empty:
                if combined_df.empty:
                    combined_df = missing_data.copy()
                else:
                    combined_df = pd.concat([combined_df, missing_data], ignore_index=True).drop_duplicates().reset_index(drop=True) 
                
                save_to_csv(missing_data, f"{symbol}_{granularity}_{year}.csv")

    if sort:
        combined_df = combined_df.sort_values(by='timestamp').reset_index(drop=True)

    # 过滤结果，使其符合start_date和end_date
    combined_df = combined_df[(combined_df['timestamp'] >= pd.to_datetime(start_date).tz_localize(timezone_s)) & 
                              (combined_df['timestamp'] <= pd.to_datetime(end_date).tz_localize(timezone_s) if end_date else current_time)]

    return combined_df

def save_to_csv(df, filename):
    if not os.path.exists(LOCAL_DATA_DIR):
        os.makedirs(LOCAL_DATA_DIR)
    filepath = os.path.join(LOCAL_DATA_DIR, filename)
    df.to_csv(filepath, index=False)

def load_from_csv(filename):
    filepath = os.path.join(LOCAL_DATA_DIR, filename)
    if os.path.exists(filepath):
        return pd.read_csv(filepath, parse_dates=['timestamp'])
    return None
