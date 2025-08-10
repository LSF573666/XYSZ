import asyncio
import aiohttp
from channels.generic.websocket import AsyncWebsocketConsumer
from .tasks import process_kline_data_task  # 导入Celery任务

class KlineDataConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.is_running = False

    async def connect(self):
        await self.accept()
        self.is_running = True
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self.data_fetching_loop())

    async def disconnect(self, close_code):
        self.is_running = False
        if self.session:
            await self.session.close()

    async def data_fetching_loop(self):
        while self.is_running:
            try:
                # 异步获取数据
                data = await self.fetch_kline_data()
                
                if data:
                    # 触发Celery任务处理数据
                    process_kline_data_task.delay(data)
                
                await asyncio.sleep(10)  # 每10秒获取一次
                
            except Exception as e:
                print(f"数据获取出错: {e}")
                await asyncio.sleep(30)

    async def fetch_kline_data(self):
        """异步获取K线数据"""
        url = "http://47.236.144.131:8000/api/klines/fetch"
        params = {
            'exchange': 'binance',
            'symbol': 'BTC',
            'interval': '1m',
            'limit': 2000
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            print(f"获取K线数据失败: {e}")
            return None