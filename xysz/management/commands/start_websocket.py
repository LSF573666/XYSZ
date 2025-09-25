from django.core.management.base import BaseCommand
import time
import signal
import sys

from xysz.tasks import fetch_klines_task

class Command(BaseCommand):
    help = 'Start periodic K-line data fetching task'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting K-line data fetching task...'))
        
        # 注册信号处理，以便优雅退出
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 启动Celery任务
        task_result = fetch_klines_task.delay()
        self.stdout.write(self.style.SUCCESS(f'Task started with ID: {task_result.id}'))
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.signal_handler(signal.SIGINT, None)
    
    def signal_handler(self, signum, frame):
        self.stdout.write(self.style.WARNING(f'Received signal {signum}, stopping task...'))
        self.running = False
        sys.exit(0)