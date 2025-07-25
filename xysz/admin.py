from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from xysz.models import Ballist, UserAccount, UserConfig, UserOrder, Userbal

admin.site.site_header = '币安交易管理后台'  # 设置header
admin.site.site_title = '币安交易'   # 设置title
admin.site.index_title = '币安交易管理端'



@admin.register(UserConfig)
class UserConfigAdmin(admin.ModelAdmin):
    list_display = ('create_datetime','username', 'apikey', 'secret', 'user_type')
    search_fields = ('username', 'user_type')

@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = ('create_datetime','username', 'currency', 'balance')
    list_filter = ('currency',)
    search_fields = ('username__username',)

@admin.register(Userbal)
class UserbalAdmin(admin.ModelAdmin):
    list_display = ('create_datetime','username', 'currency', 'avail_bal','eq_usd','frozen_bal','upl')
    list_filter = ('currency',)
    search_fields = ('username__username','currency')

@admin.register(UserOrder)
class UserOrderAdmin(admin.ModelAdmin):
    list_display = ('create_datetime', 'username', 'order_id','position_type', 'currency', 'leverage', 'direction', 'margin', 'position_amount')  # 移除 'order_id'
    list_filter = ('order_id', 'direction', 'currency')
    search_fields = ('username__username', 'currency')

@admin.register(Ballist)
class BallistAdmin(admin.ModelAdmin):
    list_display = ('ord_id','acc_fill_sz','avg_px','c_time','fee','fill_px','fill_sz','fill_time','inst_id','inst_type','ord_type','pnl','pos_side','side','lever','slOrdPx','slTriggerPx','state','sz','trade_id','u_time',)

    # 添加搜索功能的字段
    search_fields = ('ord_id', 'pos_side','slTriggerPx')

    # 添加过滤功能的字段
    list_filter = ('c_time', 'ord_id', 'pos_side', 'state')
    
