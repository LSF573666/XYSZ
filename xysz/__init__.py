# import redis

# # 全局同步Redis连接
# sync_redis_client = None

# def init_sync_redis():
#     """初始化同步Redis连接"""
#     global sync_redis_client
#     try:
#         sync_redis_client = redis.Redis(
#             host='47.84.194.2',
#             port=6379,
#             password='yyz135246',
#             db=0,
#             decode_responses=True,
#             socket_connect_timeout=10,
#             socket_timeout=10,
#             retry_on_timeout=True
#         )
#         sync_redis_client.ping()
#         print("同步Redis连接初始化成功！")
#         return True
#     except Exception as e:
#         print(f"同步Redis连接初始化失败: {e}")
#         sync_redis_client = None
#         return False