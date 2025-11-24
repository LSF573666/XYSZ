import os
from django.apps import AppConfig
import redis.asyncio as redis
import asyncio


class XyszConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'xysz'
    
    # def ready(self):
    #     # 应用启动时初始化Redis连接
    #     from django.conf import settings
    #     if not hasattr(settings, 'REDIS_CONNECTION'):
    #         settings.REDIS_CONNECTION = None
    #         asyncio.run(self.init_redis())
    
    # async def init_redis(self):
    #     """初始化Redis连接"""
    #     from django.conf import settings
    #     try:
    #         r = redis.Redis(
    #             host='47.84.194.2',
    #             port=6379,
    #             password='yyz135246',
    #             db=0,
    #             decode_responses=True,
    #             max_connections=20,  # 设置连接池大小
    #             socket_connect_timeout=5,
    #             socket_timeout=5,
    #             retry_on_timeout=True
    #         )
    #         await r.ping()
    #         settings.REDIS_CONNECTION = r
    #         print("Redis连接初始化成功！")
    #     except Exception as e:
    #         print(f"Redis连接初始化失败: {e}")
    #         settings.REDIS_CONNECTION = None
    
    # @classmethod
    # async def close_redis(cls):
    #     """关闭Redis连接"""
    #     from django.conf import settings
    #     if settings.REDIS_CONNECTION:
    #         await settings.REDIS_CONNECTION.close()
    #         settings.REDIS_CONNECTION = None
    #         print("Redis连接已关闭")