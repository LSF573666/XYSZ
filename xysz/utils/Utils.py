from datetime import datetime, timezone
import pandas as pd
import numpy as np
import random

import pytz

class Utils:
    
    @staticmethod
    def timestamp_to_date_string(timestamp, format='%Y-%m-%d %H:%M:%S', tz=timezone.utc):
        """
        时间戳转日期字符串
        :param timestamp: 时间戳，可以是 int、float 或 str
        :param format: 日期格式
        :param tz: 时区，默认是 UTC
        :return: 日期字符串
        """
        try:
            # 确保 timestamp 是浮点数或整数
            if isinstance(timestamp, str):
                timestamp = float(timestamp)  # 如果是字符串，尝试转换为浮点数
            elif not isinstance(timestamp, (int, float)):
                raise ValueError(f"Unsupported timestamp type: {type(timestamp)}")
            
            # 时间戳转换为 datetime
            dt = datetime.fromtimestamp(timestamp, tz=tz)
            return dt.strftime(format)
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {timestamp}. Error: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")
    
    @staticmethod
    def date_string_to_timestamp(date_string, format='%Y-%m-%d %H:%M:%S'):
        """
        日期字符串转时间戳
        """
        dt = datetime.strptime(date_string, format)
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    @staticmethod
    def date_string_to_date(date_string, format='%Y-%m-%d %H:%M:%S', tzinfo=timezone.utc):
        """
        日期字符串转日期对象
        """
        dt = datetime.strptime(date_string, format)
        return dt.replace(tzinfo=tzinfo)

    @staticmethod
    def date_to_date_string(date_obj, format='%Y-%m-%d %H:%M:%S'):
        """
        日期对象转日期字符串
        """
        return date_obj.strftime(format)

    @staticmethod
    def date_to_timestamp(date_obj):
        """
        日期对象转时间戳
        """
        return int(date_obj.timestamp())

    @staticmethod
    def timestamp_to_date(timestamp):
        """
        时间戳转日期对象
        """
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    @staticmethod
    def generate_random_number(level):
        """
        Generate a random float number based on the level.
        The higher the level, the higher the probability of generating a larger number.

        Args:
            level (int): The level determining the range of the random number.

        Returns:
            float: A random number greater than 0.
        """
        exponent = 1 + level / 10  # Adjust the exponent based on the level

        random_number = random.expovariate(1 / exponent)
        
        return random_number
    
    @staticmethod
    def str_to_numeric(combined_df):
        # 在读取数据后，确保数值列的类型正确
        combined_df['open'] = pd.to_numeric(combined_df['open'], errors='coerce')
        combined_df['high'] = pd.to_numeric(combined_df['high'], errors='coerce')
        combined_df['low'] = pd.to_numeric(combined_df['low'], errors='coerce')
        combined_df['close'] = pd.to_numeric(combined_df['close'], errors='coerce')
        # combined_df['confirm'] = pd.to_numeric(combined_df['confirm'], errors='coerce')
        return combined_df
    
    @staticmethod
    def calculate_percentile(df):
        """
        计算给定指标变化率的当前值在历史上的百分位数，并绘制其历史分布图。
        
        参数:
        df (DataFrame): 包含时间序列数据的DataFrame。
        column_name (str): 指标的列名。
        title (str): 图表的标题。
        
        返回:
        percentile (float): 当前指标变化率的历史百分位数。
        """
        # 计算指标的变化率
        df['Change'] = df.diff().abs()
        
        # 当前变化率
        current_change = df['Change'].iloc[-1]

        # 历史分布分析
        historical_changes = df['Change'].iloc[:-1].dropna()  # 去除NA值

        # 计算当前变化率在历史上的百分位数
        percentile = np.searchsorted(np.sort(historical_changes), current_change) / len(historical_changes) * 100

        return percentile
    
    def adjust_timestamp(original_timestamp, granularity,limit):
        """
        根据时间间隔调整时间戳，支持中国时区的毫秒级时间戳。
        """
        # 将时间间隔转换为小写，统一处理
        granularity = granularity.lower().strip()

        # 将原始时间戳转换为 Pandas 时间戳
        timestamp = pd.to_datetime(original_timestamp, unit='ms', utc=True)

        # 根据 granularity 确定减去的时间跨度
        if granularity.endswith('m'):  # 分钟级
            minutes = int(granularity[:-1])  # 提取数字部分
            adjusted_timestamp = timestamp - pd.Timedelta(minutes=minutes * limit)
        elif granularity.endswith('h'):  # 小时级
            hours = int(granularity[:-1])  # 提取数字部分
            adjusted_timestamp = timestamp - pd.Timedelta(hours=hours * limit)
        elif granularity == '1d':
            adjusted_timestamp = timestamp - pd.Timedelta(days=limit)
        else:
            raise ValueError("不支持的时间间隔，请提供合法的格式如 '15m', '2h'")

        # 转换为中国时区
        china_timezone = pytz.timezone('Asia/Shanghai')
        adjusted_timestamp = adjusted_timestamp.tz_convert(china_timezone)

        # 转换为毫秒级时间戳并返回
        adjusted_timestamp_ms = int(adjusted_timestamp.timestamp() * 1000)
        
        return adjusted_timestamp_ms