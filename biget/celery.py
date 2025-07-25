import os
from celery import Celery

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biget.settings')

# 实例化
app = Celery(
    'biget',  # 应用名称
    # broker='redis://localhost:6379/0',  # 使用 Redis
    # backend='redis://localhost:6379/1',  # 存储任务结果（可选）
    # include=['biget.tasks']  # 包含任务模块
)
# print("Broker URL:", app.conf.broker_url)

# app.conf.broker_url = 'redis://localhost:6379/0'

app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动从Django的已注册app中发现任务
app.autodiscover_tasks()

