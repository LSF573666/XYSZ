from datetime import datetime, timezone
import json
import queue
import threading
import asyncio
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from concurrent.futures import ThreadPoolExecutor
# from xysz.core.wsbiget_1m import BitgetWebSocket
from xysz.core.wsbiget_1m import BigetWebSocket
from xysz.tasks import FB_strategy

class KlineConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 核心组件初始化
        self.ws_client = None
        self.data_queue = queue.Queue(maxsize=1000)
        self._queue_lock = threading.Lock()
        self._heartbeat_interval = 5  # 心跳检测间隔(秒)
        self.symbols_keys = set()
        self._clear_queue()  # 新增的初始化清理

        # 线程控制
        self.running = False
        self.processing_thread = None
        self.thread_pool = ThreadPoolExecutor(max_workers=1)
        
        # 状态监控
        self.last_processed = None
        self._monitor_task = None

    def _clear_queue(self):
        """清空数据队列"""
        with self._queue_lock:
            while not self.data_queue.empty():
                try:
                    self.data_queue.get_nowait()
                except queue.Empty:
                    break
            print("🔄 数据队列已清空")

    async def connect(self):
        """安全连接流程"""
        await self.accept()
        
        # WebSocket客户端初始化
        self.ws_client = self.create_ws_client()
        self.ws_client.start()
        
        # 启动处理线程
        self.running = True
        self._start_processing_thread()
        
        # 启动监控任务
        self._monitor_task = asyncio.create_task(self._monitor_services())
        
        await self.send_status("Connection established")

    async def disconnect(self, close_code):
        """安全关闭流程"""
        self.running = False
        
        # 停止监控
        if self._monitor_task:
            self._monitor_task.cancel()
            
        # 关闭WebSocket
        if self.ws_client:
            self.ws_client.stop()
            
        # 停止线程
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2)
            
        # 关闭线程池
        self.thread_pool.shutdown(wait=True)

    def _start_processing_thread(self):
        """安全线程启动方法"""
        if hasattr(self, 'processing_thread') and self.processing_thread.is_alive():
            return

        self.processing_thread = threading.Thread(
            target=self._thread_wrapper,
            args=(self.process_queue_messages,),
            daemon=True,
            name=f"Processor-{time.time()}"
        )
        self.processing_thread.start()
        print(f"🔄 线程已重启 (ID: {self.processing_thread.ident})")

    def _thread_wrapper(self, func):
        """线程安全包装器"""
        try:
            while self.running:
                try:
                    func()
                except Exception as e:
                    print(f"💥 线程异常: {str(e)}")
                    time.sleep(5)  # 错误冷却
        finally:
            print("🛑 处理线程退出")

    def create_ws_client(self):
        """WebSocket客户端工厂"""
        subscriptions = [
            {"instId": "BTCUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
            {"instId": "ETHUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
            {"instId": "SOLUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
            {"instId": "DOGEUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
            {"instId": "XRPUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
            ]
        return BigetWebSocket(
            subscriptions=subscriptions,
            data_queue=self.data_queue,
            message_handler=self._handle_raw_message,
            loop=asyncio.get_event_loop()
        )

    def _handle_raw_message(self, ws, message):
        """线程安全的消息处理器"""
        with self._queue_lock:
            try:
                # 新增：检查队列大小，超过10条则清理
                if self.data_queue.qsize() > 10:
                    self._clear_queue()
                    print(f"队列已超过最大限制，已清理")
                msg = json.loads(message)
                if not self._validate_message(msg):
                    return
                    
                print(f"📩 消息入队: {msg['arg']['instId']}")
                self._process_single_message(msg) 

                self.data_queue.put_nowait(msg)
                
            except queue.Full:
                print("⚠️ 队列已满，丢弃消息")
            except Exception as e:
                print(f"🚨 消息处理失败: {str(e)}")

    def _validate_message(self, msg):
        """消息有效性验证"""
        required_keys = ['arg', 'data']
        # print(msg)
        if not all(k in msg for k in required_keys):
            # print(f"❌ 无效消息格式: {msg.keys()}")
            return False
        return True

    def process_queue_messages(self):
        print(f"🟢 处理线程启动 (ID: {threading.get_ident()})")
        while self.running:
            try:
                # 使用带超时的阻塞获取
                kline_data = self.data_queue.get(timeout=5)  # 5秒超时

                # 消息处理逻辑
                symbol = kline_data['arg']['instId']
                # print(f"✅ 开始处理: {symbol}")

                # 同步执行测试（绕过Celery）
                try:
                    from xysz.tasks import FB_strategy
                    FB_strategy(kline_data)
                    # print(f"🎉 处理完成: {symbol}")
                except ImportError as e:
                    print(f"❌ 导入任务失败: {str(e)}")
                except Exception as e:
                    print(f"❌ 任务执行错误: {str(e)}")

            except queue.Empty:
                print("⏳ 队列空闲中...")
                continue
            except Exception as e:
                print(f"💥 处理循环异常: {str(e)}")
                time.sleep(5)  # 错误冷却

    def _process_single_message(self, data):
        """处理单个消息"""
        # print(f"✅ 处理中: {data}")
    
        symbol = data['arg']['instId']
        print(f"✅ 处理中: {symbol}")
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        minute_timestamp = int(now.timestamp())
        composite_key = f"{symbol}|{minute_timestamp}"
        # print(composite_key)
        # print(self.symbols_keys)
        if composite_key not in self.symbols_keys:
            try:
                FB_strategy(data)
                # print(f"🎉 处理完成: {symbol}")
                self.last_processed = time.time()

            except ImportError:
                print("❌ 任务模块导入失败")
            except Exception as e:
                print(f"❌ 任务执行失败: {str(e)}")
        self.symbols_keys.add(composite_key)

        # 自动清理旧键
        if len(self.symbols_keys) > 10:
            self.symbols_keys.clear()

    async def _monitor_services(self):
        """服务健康监控"""
        while self.running:
            await asyncio.sleep(self._heartbeat_interval)
            
            # 检查线程状态
            if not self.processing_thread.is_alive():
                print("⚠️ 处理线程死亡，尝试重启...")
                self._start_processing_thread()
                
            # 检查处理延迟
            if self.last_processed and (time.time() - self.last_processed) > 30:
                print("⚠️ 处理延迟超过30秒")
                await self.send_status("High processing latency")

    async def send_status(self, message):
        """安全状态发送"""
        try:
            await self.send(text_data=json.dumps({
                "type": "status",
                "message": message,
                "timestamp": int(time.time()),
                "queue_size": self.data_queue.qsize()
            }))
        except Exception as e:
            print(f"📤 状态发送失败: {str(e)}")

    async def receive(self, text_data):
        """指令处理"""
        try:
            data = json.loads(text_data)
            if data.get("action") == "ping":
                await self.send_status("pong")
            elif data.get("action") == "stats":
                await self._send_system_stats()
        except Exception as e:
            await self.send_status(f"Command error: {str(e)}")

    async def _send_system_stats(self):
        """发送系统状态"""
        stats = {
            "running": self.running,
            "queue_size": self.data_queue.qsize(),
            "thread_alive": self.processing_thread.is_alive() if self.processing_thread else False,
            "last_processed": self.last_processed
        }
        await self.send_status(json.dumps(stats))