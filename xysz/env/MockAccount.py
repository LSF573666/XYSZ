from datetime import datetime
import time
from django.utils import timezone
from xysz.models import Ballist, UserOrder, Userbal, UserConfig
from django.http import HttpResponse
from django.db import transaction
import json
import os

class MockAccount:
    def __init__(self, initial_balance, leverage=5, fee_rate=0.0003, file_path="mock_account.json"):
        self.file_path = file_path
        self.initial_balance = initial_balance  # 初始资金，仅用于文件不存在时初始化
        self.balance = initial_balance  # 当前余额
        self.leverage = leverage  # 持仓倍数
        self.fee_rate = fee_rate  # 手续费率 (0.03%)
        self.positions = {}  # 持仓信息
        self.trade_records = []  # 交易记录
        self.first_buyprice = None
        self.first_sellprice = None
        self.actual_amount = None
        self.total_balance = initial_balance  # 账户总值（初始为初始余额）
        self.position_size = None
        self.load_data()  # 从文件加载账户状态

    def save_data(self, external_data=None):
        """保存账户状态到文件"""
        data = {
            "balance": self.balance,
            "initial_balance": self.initial_balance,
            "leverage": self.leverage,
            "fee_rate": self.fee_rate,
            "positions": self.positions,
            "trade_records": self.trade_records,
            "first_buyprice": self.first_buyprice,
            "first_sellprice": self.first_sellprice,
            "actual_amount": self.actual_amount,
            "total_balance": self.total_balance,
            "position_size": self.position_size,
        }
        if external_data:
            data.update(external_data)
        with open(self.file_path, "w") as f:
            json.dump(data, f)

    def load_data(self):
        """从文件加载账户状态"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                    self.balance = data.get("balance", self.initial_balance)
                    self.initial_balance = data.get("initial_balance", self.initial_balance)
                    self.leverage = data.get("leverage", self.leverage)
                    self.fee_rate = data.get("fee_rate", self.fee_rate)
                    self.positions = data.get("positions", self.positions)
                    self.trade_records = data.get("trade_records", self.trade_records)
                    self.first_buyprice = data.get("first_buyprice", self.first_buyprice)
                    self.first_sellprice = data.get("first_sellprice", self.first_sellprice)
                    self.actual_amount = data.get("actual_amount", self.actual_amount)
                    self.total_balance = data.get("total_balance", self.total_balance)
                    self.position_size = data.get("position_size", self.position_size)
                # print("✅ 从文件加载账户状态成功！")
            except Exception as e:
                print(f"⚠️ 无法加载账户状态，文件损坏或格式错误：{e}")
                self.reset_to_initial()
        else:
            self.reset_to_initial()

    def reset_to_initial(self):
        """将账户状态重置为初始值"""
        print("⚠️ 文件不存在或加载失败，重置为初始账户状态。")
        self.balance = self.initial_balance
        self.positions = {}
        self.trade_records = []
        self.first_buyprice = None
        self.first_sellprice = None
        self.actual_amount = None
        self.total_balance = self.initial_balance
        self.position_size = None
        self.save_data()

    """买入计算"""
    def buy(self, symbol, price,position_side='long', position_percentage=0.3):
        # 检查持仓数量上限
        # if len(self.positions) >= 2:
        #     print(f"本地已达到最大持仓数量，等待卖出后再买入 {symbol}。")
        #     return

        self.leverage = float(self.leverage)

        price = float(price)
        # 计算实际开仓金额和手续费
        position_amount = self.balance * position_percentage  # 例如：200 * 0.3 = 60
        fee = position_amount * self.fee_rate * self.leverage  # 手续费
        self.actual_amount = position_amount - fee  # 扣除手续费后的实际金额

        # 检查余额是否足够
        if self.balance < (position_amount + fee):
            print(f"本地余额不足，无法支付手续费和开仓金额，无法买入 {symbol}。")
            return

        # 计算基础仓位数量
        base_position_size = round(self.actual_amount * self.leverage / price, 4)
        self.position_size = base_position_size * 100  # 放大100倍后的仓位数量
        self.actual_amount = base_position_size * price / self.leverage

        self.positions[symbol] = {
            'position_side': position_side,
            'position_size': self.position_size,
            'position_price': price,
            'leverage': self.leverage,
            'actual_amount' : self.actual_amount,
            'fee' : fee,
        }

        # 扣除开仓金额和手续费
        self.balance -= position_amount
        self.trade_records.append(('buy', symbol, price, position_side, self.actual_amount, fee))
        if self.first_buyprice is None :
            self.first_buyprice=price 
        # print(f"📈 本地买入{position_side} {symbol}，价格：{price}，开仓金额：{self.actual_amount:.2f}，手续费：{fee:.2f}")
        # 保存到 JSON 文件
        self.save_data()

    # """爆仓计算"""
    # def calculate_liquidation_price(self,symbol,high_price, low_price, tariff=0.005,is_long=True):

    #     if symbol in self.positions:
    #         # 计算强平价格
    #         # 系统止损价 = 开仓价 *（1-止损率/杠杆倍数）-（保证金/持仓数量） #有追加时再加
    #         if is_long:
    #             liquidation_price = self.first_buyprice * (1 - 1 /self.leverage + tariff)
    #             if liquidation_price > low_price :
    #                 self.actual_amount == 0
    #         else:
    #             liquidation_price = self.first_buyprice * (1 + 1 /self.leverage - tariff)
    #             if liquidation_price < high_price:
    #                 self.actual_amount == 0
    #         return liquidation_price


    """卖出计算"""
    def sell(self, symbol, price):
        if symbol in self.positions:
            if self.actual_amount is None :
                self.actual_amount == price * self.positions['BTC']['position_size']
            # print(f"Sell 请求:类型: {type(price)}{type(self.actual_amount)}{type(self.fee_rate)}{type(self.leverage )}")
            self.actual_amount = float(self.actual_amount)
            self.leverage = float(self.leverage)

            # 计算 fee
            fee = self.actual_amount * self.fee_rate * self.leverage
            # fee = self.actual_amount * self.fee_rate * self.leverage 

            if self.first_sellprice is None :
                self.first_sellprice=price 
            pnl = self.calculate_pnl(symbol, price)  # 盈亏计算

            # 更新余额：加上盈亏，扣除手续费
            self.balance = float(self.balance)
            self.balance += pnl - fee + self.actual_amount
            # print(f"📉 平仓 {symbol}，盈亏：{pnl:.4f}，手续费：{fee:.4f}，当前余额：{self.balance:.4f}")

            # 删除持仓记录
            del self.positions[symbol]
            self.trade_records.append(('sell', symbol, price, pnl, fee))
            self.trend_balance = None
            self.position_size = None
            # 保存到 JSON 文件
            self.save_data()
        else:
            print(f"本地没有持仓 {symbol}，无法平仓。")


    """盈亏计算"""
    def calculate_pnl(self, symbol, price):
        if symbol in self.positions:
            position = self.positions[symbol]
            self.position_size = position['position_size']
            position_side = position['position_side']

            # 检查 buyprice 和 sellprice 是否已设置
            if self.first_buyprice is None or self.first_sellprice is None:
                print(f"无法计算盈亏，买入价格或卖出价格未设置。")
                return 0
            
            self.first_sellprice = float(self.first_sellprice)
            self.first_buyprice = float(self.first_buyprice)
            self.position_size = float(self.position_size)

            # 盈利 = （卖出价格 - 开仓价格）* 持仓量    (买入时已计算杠杆)
            if self.first_sellprice is not None and self.first_buyprice is not None:
                if position_side == 'long':
                    pnl = (self.first_sellprice - self.first_buyprice) * self.position_size / 100
                    self.first_buyprice = None
                    self.first_sellprice = None
                elif position_side == 'short':
                    pnl = (self.first_buyprice - self.first_sellprice) * self.position_size / 100
                    self.first_buyprice = None
                    self.first_sellprice = None
                else:
                    pnl = 0
            else:
                pnl = 0
            return pnl
        return 0

    def get_total_balance(self):
        """
        计算并更新账户总值，包括余额和浮动盈亏。
        """
        self.total_balance = self.balance
        for symbol in self.positions:
            current_price = self.positions[symbol]['position_price']  # 假设当前价与持仓价相同（模拟）
            self.total_balance += self.calculate_pnl(symbol, current_price)
        return self.total_balance

    def get_account_summary(self):
        """
        返回账户总值及详细信息。
        """
        self.get_total_balance()  # 更新总值
        return {
            # "current_balance": self.balance,
            "total_balance": self.total_balance,
            "positions": self.positions,
            # "trade_records": self.trade_records,
        }


    def get_position_info(self, symbol, position_side=None):
        """
        获取持仓信息。
        """
        position = self.positions.get(symbol)
        if position and (position_side is None or position['position_side'] == position_side):
            return position
        elif position and (position_side is None or position['position_side'] != position_side):
            return position
        return None



    
    
