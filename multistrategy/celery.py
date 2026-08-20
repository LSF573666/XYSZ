
# 现在才可以安全导入其他模块
import logging
import os
from celery import Celery

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'multistrategy.settings')

# 实例化 Celery
app = Celery('multistrategy')

# 从 Django settings 加载配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现任务
app.autodiscover_tasks()


class _SuppressNoopTaskSuccessFilter(logging.Filter):
    """过滤无实际业务结果的任务成功日志（空返回 / 跳过）。"""

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if 'succeeded' not in msg:
            return True
        # succeeded in ...s: None
        if msg.rstrip().endswith(': None'):
            return False
        if 'unsupported_interval' in msg or 'already_processed' in msg:
            return False
        if "'status': 'skipped'" in msg or '"status": "skipped"' in msg:
            return False
        if "'status': 'waiting'" in msg or '"status": "waiting"' in msg:
            return False
        return True


logging.getLogger('celery.app.trace').addFilter(_SuppressNoopTaskSuccessFilter())