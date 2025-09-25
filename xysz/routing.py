# xysz/routing.py
from django.urls import re_path

from xysz import consumers

websocket_urlpatterns = [
    re_path(r'ws/market/(?P<symbol>\w+)/$', consumers.MarketConsumer.as_asgi()),
]