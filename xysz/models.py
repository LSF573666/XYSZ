import cron_descriptor
from django.db import models
from django.utils import timezone
import time
from django.db.models import Q

# Create your models here.
# 查询基础类（只更新is_deleted为True的数据）
class BaseModelQuerySet(models.QuerySet):
    def delete(self):
        self.update(is_deleted=True)

# 数据库行为管理 过滤伪删除（过滤is_deleted为False的数据）
class BaseModelManager(models.Manager):
    def get_queryset(self):
        return BaseModelQuerySet(self.model, using=self._db).filter(is_deleted=False)

# 基础类

class BaseModel(models.Model):
    # 默认保存ID
    id = models.BigAutoField(primary_key=True, verbose_name="ID")
    create_datetime = models.DateTimeField(auto_now_add=True, verbose_name="创建日期")  # 自动获取当前时间
    update_datetime = models.DateTimeField(null=True, blank=True, verbose_name="更新日期")
    is_deleted = models.BooleanField(default=False, verbose_name="伪删除标记")
    
    objects = BaseModelManager()
        
    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.save()
        
    class Meta:
        abstract = True  # 基类不会生成数据库表

# 用户管理模块
class UserConfig(BaseModel):
    USER_TYPE_CHOICES = (
        ('real', '真实用户'),
        ('simulated', '模拟用户'),
    )
    
    username = models.CharField(max_length=50, unique=True, verbose_name="用户名")
    apikey = models.CharField(max_length=100, verbose_name="用户apikey")
    secret = models.CharField(max_length=100, verbose_name="用户secret")
    user_type = models.CharField(max_length=100, choices=USER_TYPE_CHOICES, verbose_name="用户类型")

    class Meta:
        verbose_name = '用户配置列表'
        verbose_name_plural = '用户配置列表'
    
    def __str__(self):
        return self.username


class UserAccount(BaseModel):
    username = models.ForeignKey(UserConfig, on_delete=models.CASCADE, verbose_name="用户名")
    currency = models.CharField(max_length=100, verbose_name="币种")
    balance = models.DecimalField(max_digits=50, decimal_places=16, verbose_name="持仓量")

    class Meta:
        verbose_name = '用户账户列表'
        verbose_name_plural = '用户账户列表'


    def __str__(self):
        return f"{self.username} - {self.currency}"
    
class Userbal(BaseModel):
    username = models.ForeignKey(UserConfig, on_delete=models.CASCADE, verbose_name="用户名")
    currency = models.CharField(max_length=100, verbose_name="币种")
    avail_bal = models.DecimalField(max_digits=50, decimal_places=16, verbose_name="可用余额")
    eq_usd = models.DecimalField(max_digits=50, decimal_places=16, verbose_name="总权益（美元）")
    frozen_bal = models.DecimalField(max_digits=50, decimal_places=16, verbose_name="冻结余额")
    upl = models.DecimalField(max_digits=50, decimal_places=16, verbose_name="未实现盈亏")

    class Meta:
        verbose_name = '用户账户余额列表'
        verbose_name_plural = '用户账户余额列表'


    def __str__(self):
        return f"{self.username} - {self.currency}"

# 用户持仓模块
class UserOrder(BaseModel):
    POSITION_TYPE_CHOICES = (
        ('regular', '普通订单'),
        ('isolated', '逐仓合约'),
        ('cross', '全仓合约'),
    )
    DIRECTION_CHOICES = (
        ('long', '做多'),
        ('short', '做空'),
    )
    
    username = models.ForeignKey(UserConfig, on_delete=models.CASCADE, verbose_name="用户名")
    order_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="订单ID")  # ordId
    position_type = models.CharField(max_length=100, null=True, blank=True,choices=POSITION_TYPE_CHOICES, verbose_name="持仓类型")
    currency = models.CharField(max_length=100, null=True, blank=True,verbose_name="币种名称")
    leverage = models.CharField(max_length=100, null=True, blank=True, verbose_name="持仓倍数")
    direction = models.CharField(max_length=100, null=True, blank=True,choices=DIRECTION_CHOICES, verbose_name="持仓方向")
    margin = models.CharField(max_length=100, null=True, blank=True, verbose_name="保证金")
    position_amount = models.CharField(max_length=100, null=True, blank=True, verbose_name="持仓金额")
    

    class Meta:
        verbose_name = '用户持仓信息'
        verbose_name_plural = '用户持仓信息'


    def __str__(self):
        return f"{self.username} - {self.currency} ({self.position_type})"
    

"""
用户当前订单详细信息
"""

class Ballist(models.Model):
    ord_id = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="订单ID")  # 订单ID
    acc_fill_sz = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="已成交数量")  # 已成交数量
    avg_px = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="平均价格")  # 平均价格
    c_time = models.DateTimeField(null=True, blank=True, verbose_name="创建时间")  # 创建时间
    fee = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="手续费")  # 手续费
    fill_px = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="成交价格")  # 成交价格
    fill_sz = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="成交数量")  # 成交数量
    fill_time = models.DateTimeField(null=True, blank=True, verbose_name="成交时间")  # 成交时间
    inst_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="交易对ID")  # 交易对ID
    inst_type = models.CharField(max_length=20, null=True, blank=True, verbose_name="交易类型")  # 交易类型
    ord_type = models.CharField(max_length=20, null=True, blank=True, verbose_name="订单类型")  # 订单类型
    pnl = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="盈亏")  # 盈亏
    pos_side = models.CharField(max_length=10, null=True, blank=True, verbose_name="持仓方向")  # 持仓方向
    side = models.CharField(max_length=10, null=True, blank=True, verbose_name="订单方向")  # 订单方向
    lever = models.CharField(max_length=10, null=True, blank=True, verbose_name="杠杆倍数") 
    slOrdPx = models.CharField(max_length=50,null=True, blank=True, verbose_name="止损委托价") 
    slTriggerPx = models.CharField(max_length=50,null=True, blank=True, verbose_name="止损触发价") 
    # lever = models.CharField(max_length=10, null=True, blank=True, verbose_name="杠杆倍数")  # 杠杆倍数
    state = models.CharField(max_length=20, null=True, blank=True, verbose_name="订单状态")  # 订单状态
    sz = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="订单总数量")  # 订单总数量
    trade_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="交易ID")  # 交易ID
    u_time = models.DateTimeField(null=True, blank=True, verbose_name="更新时间")  # 更新时间


    class Meta:
        verbose_name = '用户当前订单信息'
        verbose_name_plural = '用户当前订单信息'

    def __str__(self):
        return f"{self.inst_id} - {self.ord_id}"



# class Ballist(BaseModel):
#     POSITION_TYPE_CHOICES = (
#         ('regular', '普通订单'),
#         ('isolated', '逐仓合约'),
#         ('cross', '全仓合约'),
#     )
#     DIRECTION_CHOICES = (
#         ('long', '做多'),
#         ('short', '做空'),
#     )
#     c_time = models.CharField(max_length=50,  null=True, blank=True,default=timezone.now, verbose_name="创建时间")  # 保存为字符串
#     ccy = models.CharField(max_length=10, null=True, blank=True, verbose_name="货币类型")
#     close_avg_px = models.CharField(max_length=128, null=True, blank=True, verbose_name="平仓均价")
#     close_total_pos = models.CharField(max_length=128, null=True, blank=True, verbose_name="平仓总头寸")
#     direction = models.CharField(max_length=10, null=True, blank=True, choices=DIRECTION_CHOICES, verbose_name="方向")
#     fee = models.CharField(max_length=128, null=True, blank=True,verbose_name="手续费")
#     funding_fee = models.CharField(max_length=128, null=True, blank=True,verbose_name="资金费用")
#     inst_id = models.CharField(max_length=20,  null=True, blank=True,verbose_name="合约ID")
#     inst_type = models.CharField(max_length=10, null=True, blank=True, verbose_name="合约类型")
#     lever = models.CharField(max_length=128, null=True, blank=True, verbose_name="杠杆倍数")
#     liq_penalty = models.CharField(max_length=128, null=True, blank=True, verbose_name="强平罚金")
#     mgn_mode = models.CharField(max_length=10, null=True, blank=True, choices=POSITION_TYPE_CHOICES, verbose_name="保证金模式")
#     open_avg_px = models.CharField(max_length=128, null=True, blank=True, verbose_name="开仓均价")
#     open_max_pos = models.CharField(max_length=128, null=True, blank=True, verbose_name="开仓最大头寸")
#     pnl = models.CharField(max_length=128, null=True, blank=True, verbose_name="浮动盈亏")
#     pnl_ratio = models.CharField(max_length=128, null=True, blank=True, verbose_name="盈亏比率")
#     ordid = models.CharField(max_length=50, verbose_name="头寸ID")  # 设置唯一约束
#     pos_side = models.CharField(max_length=10, null=True, blank=True, verbose_name="持仓方向")
#     realized_pnl = models.CharField(max_length=128, null=True, blank=True, verbose_name="已实现盈亏")
#     trigger_px = models.CharField(max_length=20, null=True, blank=True, verbose_name="触发价格")
#     trade_type = models.IntegerField( null=True, blank=True,verbose_name="交易类型")
#     u_time = models.CharField(max_length=50,  null=True, blank=True,verbose_name="更新时间")
#     uly = models.CharField(max_length=20, null=True, blank=True,verbose_name="基础货币对")


#     class Meta:
#         verbose_name = '用户当前订单信息'
#         verbose_name_plural = '用户当前订单信息'

#     def __str__(self):
#         return f"{self.inst_id} - {self.ordid}"
