# ws_client.py
import json
import os
import shutil
import ssl
import threading
import time
import queue
import pandas as pd
import websocket
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from xysz.config import LOCAL_DATA_DIR
from xysz.main_biget import cof_main


class BigetWebSocket:
    def __init__(self, subscriptions, max_retries=10):
        self.subscriptions = subscriptions
        self.max_retries = max_retries
        self.retry_count = 0
        self.processed_keys = set()
        self.ws = None
        self.running = False
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.reconnect_delay = 5
        self.redata_fetcher = True

    def on_open(self, ws):
        params = {
            "op": "subscribe",
            "args": [{
                "instType": sub["instType"],
                "channel": f"candle{sub['granularity']}",
                "instId": sub["instId"]
            } for sub in self.subscriptions]
        }
        
        try:
            ws.send(json.dumps(params))
            self.retry_count = 0
            print(f"成功订阅: {[sub['instId'] for sub in self.subscriptions]}")
        except Exception as e:
            print(f"Error sending subscribe message: {e}")
            self.schedule_reconnect()

    def on_message(self, ws, message):
        current_time = int(datetime.now(timezone.utc).timestamp())
        minute_timestamp = (current_time // 60) * 60

        if current_time % 900 <= 30 and self.redata_fetcher: 
            shutil.rmtree(LOCAL_DATA_DIR)
            os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
            cof_main()
            self.redata_fetcher = False
        elif current_time % 850 <= 30 :
            self.redata_fetcher = True

        if current_time % 60 <= 30:
            try:
                msg = json.loads(message)
                if 'arg' in msg and 'data' in msg:
                    inst_id = msg['arg']['instId']
                    kline = msg['data'][-1]
                    timestamp_ms = int(kline[0])
                    beijing_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone(timedelta(hours=8)))
                    minute_level_time = beijing_time.replace(second=0, microsecond=0)
                    formatted_timestamp = minute_level_time.strftime('%Y-%m-%d %H:%M:00%z')[:-2] + ":" + minute_level_time.strftime('%z')[-2:]

                    kline_data = {
                        'symbol': inst_id,
                        'timestamp': formatted_timestamp,
                        'open': float(kline[1]),
                        'high': float(kline[2]),
                        'low': float(kline[3]),
                        'close': float(kline[1]),  # 修正为正确的close价格
                        'volume': float(kline[5]),
                    }

                    composite_key = f"{inst_id}|{minute_timestamp}"
                    # print(kline_data)
                    if composite_key not in self.processed_keys:
                        from xysz.tasks import FB_strategy, KC_strategy
                        FB_strategy.delay(kline_data)
                        KC_strategy.delay(kline_data)
                        self.processed_keys.add(composite_key)
                        if len(self.processed_keys) > 100:
                            self.processed_keys.clear()

            except Exception as e:
                print(f"Error processing message: {e}")

    def on_error(self, ws, error):
        print(f"WebSocket error: {error}")
        self.schedule_reconnect()

    def on_close(self, ws, close_status_code, close_msg):
        print(f"WebSocket connection closed: {close_status_code}, {close_msg}")
        self.schedule_reconnect()

    def schedule_reconnect(self):
        with self.lock:
            if not self.running:
                return
                
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                print(f"Attempting reconnect... {self.retry_count}/{self.max_retries}")
                self.executor.submit(self.delayed_reconnect)
            else:
                print(f"超过最大重试次数，等待 60 秒后重置计数器并重试")
                self.retry_count = 0
                time.sleep(60)
                self.delayed_reconnect()

    def delayed_reconnect(self):
        time.sleep(self.reconnect_delay)
        self.run()

    def on_ping(self, ws, message):
        try:
            ws.send("pong")
        except Exception as e:
            print(f"Error sending pong: {e}")
            self.schedule_reconnect()

    def run(self):
        with self.lock:
            if not self.running:
                self.running = True
                
        self.retry_count = 0
        url = "wss://ws.bitget.com/v2/ws/public"
        
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
            
        try:
            self.ws = websocket.WebSocketApp(
                url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_ping=self.on_ping
            )
            
            self.ws.run_forever(
                ping_interval=20,
                ping_timeout=10,
                sslopt={"cert_reqs": ssl.CERT_NONE},
                reconnect=5
            )
        except Exception as e:
            print(f"Unexpected error in run_forever: {e}")
            self.schedule_reconnect()

    def stop(self):
        with self.lock:
            self.running = False
            
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
            
        self.executor.shutdown(wait=False)


def start_websocket_client():
    subscriptions = [
        {"instId": "BTCUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
        {"instId": "ETHUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
        {"instId": "SOLUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
        {"instId": "DOGEUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
        {"instId": "XRPUSDT", "instType": "USDT-FUTURES", "granularity": "1m"},
        # {"instId": "BTCUSDT", "instType": "USDT-FUTURES", "granularity": "5m"},
        # {"instId": "ETHUSDT", "instType": "USDT-FUTURES", "granularity": "5m"},
        # {"instId": "SOLUSDT", "instType": "USDT-FUTURES", "granularity": "5m"},
        # {"instId": "DOGEUSDT", "instType": "USDT-FUTURES", "granularity": "5m"},
        # {"instId": "XRPUSDT", "instType": "USDT-FUTURES", "granularity": "5m"},
    ]
    
    ws = BigetWebSocket(subscriptions)
    ws_thread = threading.Thread(target=ws.run, daemon=True)
    ws_thread.start()
    return ws