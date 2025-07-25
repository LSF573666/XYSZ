from django.urls import re_path

from xysz import consumers
# from yourapp import consumers

websocket_urlpatterns = [
    re_path(r'ws/kline/$', consumers.KlineConsumer.as_asgi()),
]