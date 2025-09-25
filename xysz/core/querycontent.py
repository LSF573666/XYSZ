import aiohttp
import asyncio
import time


async def fetch_klines(session, exchange, symbol, interval):
    base_url = "http://47.236.144.131:8000/api/klines/fetch"
    params = {
        'exchange': exchange,
        'symbol': symbol,
        'interval': interval,
        'limit': 500,  # 注意到你已将limit改为500
        'get_more': 0
    }
    try:
        async with session.get(base_url, params=params, timeout=10) as response:
            if response.status == 200:
                # 读取并解析JSON响应
                data = await response.json()
                print(f"成功: {exchange}, {symbol}, {interval}")
                print(f"响应数据: {data}")
                return True
            else:
                print(f"失败: {exchange}, {symbol}, {interval} - 状态码: {response.status}")
                return False
    except Exception as e:
        print(f"错误: {exchange}, {symbol}, {interval} - {str(e)}")
        return False


async def main():
    # 参数列表
    exchanges = ['bitget', 'binance', 'okx']
    symbols = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
    intervals = ['1m', '5m', '15m', '30m']

    # 统计
    total_calls = 0
    successful_calls = 0
    failed_calls = 0

    # 记录开始时间
    start_time = time.time()

    # 创建单一会话
    async with aiohttp.ClientSession() as session:
        # 创建任务列表
        tasks = [
            fetch_klines(session, exchange, symbol, interval)
            for exchange in exchanges
            for symbol in symbols
            for interval in intervals
        ]

        # 并发运行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计成功和失败
        total_calls = len(tasks)
        successful_calls = sum(1 for result in results if result is True)
        failed_calls = total_calls - successful_calls

    # 记录结束时间并计算耗时
    end_time = time.time()
    duration = end_time - start_time

    # 输出总结
    print("\n--- 总结 ---")
    print(f"总请求数: {total_calls}")
    print(f"成功请求: {successful_calls}")
    print(f"失败请求: {failed_calls}")
    print(f"总耗时: {duration:.2f} 秒")
    print(f"平均每请求耗时: {duration / total_calls:.2f} 秒")


if __name__ == "__main__":
    asyncio.run(main())