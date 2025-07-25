# config.py

BIGET_API_URL = 'https://api.bitget.com'
KLINE_INTERVALS = {
    '1m': '1m',
    '1h': '1h',
    '1d': '1d',
    '1w': '1w',
    '1M': '1M'
}
LOCAL_DATA_DIR = 'data'

def get_api_balance():
    initial_ba = 25
    return initial_ba

# REDIS_CONFIG = {
#     'host': '8.216.32.13',
#     'port': 6379,
#     'password': 'yyz135246',
#     'db': 0
# }