"""
URL configuration for biget project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
# from xysz import consumers
# from django.urls import re_path


urlpatterns = [
    path("admin/", admin.site.urls),
    # re_path(r'ws/multi-process/$', consumers.MultiWebSocketConsumer.as_asgi()),
    # re_path(r'ws/kline/$', consumers.KlineConsumer.as_asgi()),
    # # 获取历史数据 + 买卖操作
    # path('jyxt/FB_view', FB_view, name='FB_strategy'),
    # path('jyxt/KC_view', KC_view, name='KC_strategy'),
    # path('jyxt/query_main', query_main, name='query_main'),

    # 删除重复的订单信息
    # path('jyxt/delete_duplicate_orders', delete_duplicate_orders, name='delete_duplicate_orders'),
]
