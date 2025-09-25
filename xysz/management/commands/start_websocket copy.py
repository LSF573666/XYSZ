# your_app/management/commands/start_websocket.py
from django.core.management.base import BaseCommand
# from your_app.ws_client import start_websocket_client
import time
import signal
import sys

from xysz.core.wsbiget_1m import start_websocket_client

class Command(BaseCommand):
    help = 'Start WebSocket client for market data'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws = None
        
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting WebSocket client...'))
        
        # 注册信号处理，以便优雅退出
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.ws = start_websocket_client()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_websocket()
    
    def signal_handler(self, signum, frame):
        self.stdout.write(self.style.WARNING(f'Received signal {signum}, stopping WebSocket client...'))
        self.stop_websocket()
        sys.exit(0)
        
    def stop_websocket(self):
        if self.ws:
            self.stdout.write(self.style.SUCCESS('Stopping WebSocket client...'))
            self.ws.stop()