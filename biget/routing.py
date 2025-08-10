from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from xysz import consumers
# from yourapp import consumers

application = ProtocolTypeRouter({
    'websocket': URLRouter([
        path('ws/data/', consumers.DataConsumer.as_asgi()),
    ])
})