
# 现在才可以安全导入其他模块
import os
from celery import Celery

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biget.settings')

# 实例化 Celery
app = Celery('biget')

# 从 Django settings 加载配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现任务
app.autodiscover_tasks()