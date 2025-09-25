from datetime import datetime
import json
import os

class MockAccount:
    def __init__(self, initial_balance, leverage=5, fee_rate=0.0008, file_path="mock_account.json"):
        self.file_path = file_path
        self.initial_balance = initial_balance  # 初始资金，仅用于文件不存在时初始化
        self.balance = initial_balance  # 当前余额
        self.leverage = leverage  # 默认持仓倍数
        self.fee_rate = fee_rate  # 默认手续费率 (0.08%)
        self.positions = {}  # 持仓信息 {strategy: {exchange: {symbol: position_data}}}
        self.trade_records = []  # 交易记录
        self.total_balance = initial_balance  # 账户总值（初始为初始余额）
        self.strategy_performance = {}  # 策略表现统计
        self.load_data()  # 从文件加载账户状态

    def save_data(self, external_data=None):
        """保存账户状态到文件"""
        data = {
            "balance": self.balance,
            "initial_balance": self.initial_balance,
            "leverage": self.leverage,
            "fee_rate": self.fee_rate,
            "positions": self.positions,
            # "trade_records": self.trade_records,
            "total_balance": self.total_balance,
            "strategy_performance": self.strategy_performance,
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
                    self.total_balance = data.get("total_balance", self.total_balance)
                    self.strategy_performance = data.get("strategy_performance", {})
            except Exception as e:
                self.reset_to_initial()
        else:
            self.reset_to_initial()

    def reset_to_initial(self):
        """将账户状态重置为初始值"""
        self.balance = self.initial_balance
        self.positions = {}
        self.trade_records = []
        self.total_balance = self.initial_balance
        self.strategy_performance = {}
        self.save_data()

    def buy(self, strategy, exchange, symbol, price, position_side='long', position_percentage=0.1, leverage=None, fee_rate=None):
        """
        买入操作
        strategy: 策略名称
        exchange: 交易所名称
        symbol: 交易对
        price: 价格
        position_side: 持仓方向 (long/short)
        position_percentage: 仓位百分比
        leverage: 杠杆倍数，如果为None则使用默认值
        fee_rate: 手续费率，如果为None则使用默认值
        """
        leverage = leverage if leverage is not None else self.leverage
        fee_rate = fee_rate if fee_rate is not None else self.fee_rate
        
        leverage = float(leverage)
        price = float(price)
        fee_rate = float(fee_rate)
        
        # 检查该策略、交易所和交易对是否已有持仓
        strategy_positions = self.positions.get(strategy, {})
        exchange_positions = strategy_positions.get(exchange, {})
        if symbol in exchange_positions:
            # 已有持仓，可以加仓或忽略
            return False
        
        # 计算实际开仓金额和手续费
        position_amount = self.balance * position_percentage
        fee = position_amount * fee_rate * leverage
        actual_amount = position_amount - fee

        # 计算基础仓位数量
        base_position_size = round(actual_amount * leverage / price, 8)
        position_size = base_position_size

        # 创建持仓记录
        position_data = {
            'position_side': position_side,
            'position_size': position_size,
            'entry_price': price,
            'leverage': leverage,
            'fee_rate': fee_rate,
            'actual_amount': actual_amount,
            'fee_paid': fee,
            'position_percentage': position_percentage,
            'entry_time': datetime.now().isoformat(),
            'strategy': strategy
        }

        # 更新持仓信息（三层结构：策略->交易所->交易对）
        if strategy not in self.positions:
            self.positions[strategy] = {}
        if exchange not in self.positions[strategy]:
            self.positions[strategy][exchange] = {}
        self.positions[strategy][exchange][symbol] = position_data

        # 扣除开仓金额和手续费
        self.balance -= position_amount
        
        # 记录交易
        trade_record = {
            'action': 'buy',
            'strategy': strategy,
            'exchange': exchange,
            'symbol': symbol,
            'price': price,
            'position_side': position_side,
            'amount': actual_amount,
            'fee': fee,
            'leverage': leverage,
            'position_percentage': position_percentage,
            'timestamp': datetime.now().isoformat()
        }
        self.trade_records.append(trade_record)
        
        # 更新策略表现统计
        self._update_strategy_performance(strategy, trade_record)
        
        # 保存到文件
        self.save_data()
        return True

    def sell(self, strategy, exchange, symbol, price):
        """
        卖出操作
        strategy: 策略名称
        exchange: 交易所名称
        symbol: 交易对
        price: 价格
        """
        # 检查持仓是否存在
        if (strategy not in self.positions or 
            exchange not in self.positions[strategy] or 
            symbol not in self.positions[strategy][exchange]):
            return False
        
        position = self.positions[strategy][exchange][symbol]
        price = float(price)
        
        # 计算盈亏
        pnl = self.calculate_pnl(strategy, exchange, symbol, price)
        
        # 计算手续费（平仓手续费）
        fee = position['actual_amount'] * position['fee_rate'] * position['leverage']
        
        # 更新余额
        self.balance = float(self.balance)
        returned_amount = position['actual_amount'] + pnl - fee
        self.balance += returned_amount
        
        # 记录交易
        trade_record = {
            'action': 'sell',
            'strategy': strategy,
            'exchange': exchange,
            'symbol': symbol,
            'price': price,
            'pnl': pnl,
            'fee': fee,
            'returned_amount': returned_amount,
            'timestamp': datetime.now().isoformat()
        }
        self.trade_records.append(trade_record)
        
        # 更新策略表现统计
        self._update_strategy_performance(strategy, trade_record)
        
        # 删除持仓记录
        del self.positions[strategy][exchange][symbol]
        # 清理空字典
        if not self.positions[strategy][exchange]:
            del self.positions[strategy][exchange]
        if not self.positions[strategy]:
            del self.positions[strategy]
        
        # 保存到文件
        self.save_data()
        return True

    def _update_strategy_performance(self, strategy, trade_record):
        """更新策略表现统计"""
        if strategy not in self.strategy_performance:
            self.strategy_performance[strategy] = {
                'total_trades': 0,
                'win_trades': 0,
                'loss_trades': 0,
                'total_pnl': 0,
                'total_fees': 0,
                'last_trade_time': None
            }
        
        stats = self.strategy_performance[strategy]
        stats['total_trades'] += 1
        stats['total_fees'] += trade_record.get('fee', 0)
        stats['last_trade_time'] = trade_record['timestamp']
        
        if trade_record['action'] == 'sell':
            pnl = trade_record.get('pnl', 0)
            stats['total_pnl'] += pnl
            if pnl > 0:
                stats['win_trades'] += 1
            elif pnl < 0:
                stats['loss_trades'] += 1

    def calculate_pnl(self, strategy, exchange, symbol, current_price):
        """计算盈亏"""
        if (strategy not in self.positions or 
            exchange not in self.positions[strategy] or 
            symbol not in self.positions[strategy][exchange]):
            return 0
        
        position = self.positions[strategy][exchange][symbol]
        entry_price = float(position['entry_price'])
        position_size = float(position['position_size'])
        leverage = float(position['leverage'])
        
        if position['position_side'] == 'long':
            pnl = (current_price - entry_price) * position_size * leverage
        else:  # short
            pnl = (entry_price - current_price) * position_size * leverage
        
        return pnl

    def get_total_balance(self):
        """计算并更新账户总值，包括余额和所有持仓的浮动盈亏"""
        total_value = self.balance
        
        # 计算所有持仓的当前价值
        for strategy, exchanges in self.positions.items():
            for exchange, symbols in exchanges.items():
                for symbol, position in symbols.items():
                    current_price = position['entry_price']  # 模拟当前价格
                    pnl = self.calculate_pnl(strategy, exchange, symbol, current_price)
                    total_value += pnl
        
        self.total_balance = total_value
        return self.total_balance

    def get_account_summary(self):
        """返回账户总值及详细信息"""
        self.get_total_balance()
        return {
            "current_balance": self.balance,
            "total_balance": self.total_balance,
            "positions_count": self.get_total_positions_count(),
            "strategies": list(self.positions.keys()),
            "exchanges": self.get_all_exchanges(),
            "strategy_performance": self.strategy_performance
        }

    def get_total_positions_count(self):
        """获取总持仓数量"""
        count = 0
        for strategy in self.positions.values():
            for exchange in strategy.values():
                count += len(exchange)
        return count

    def get_all_exchanges(self):
        """获取所有交易所列表"""
        exchanges = set()
        for strategy in self.positions.values():
            for exchange in strategy.keys():
                exchanges.add(exchange)
        return list(exchanges)

    def get_position_info(self, strategy=None, exchange=None, symbol=None, position_side=None):
        """
        获取持仓信息，支持多维度筛选
        """
        result = {}
        
        for strat, exchanges in self.positions.items():
            if strategy and strat != strategy:
                continue
                
            result[strat] = {}
            for exch, symbols in exchanges.items():
                if exchange and exch != exchange:
                    continue
                    
                result[strat][exch] = {}
                for sym, position in symbols.items():
                    if symbol and sym != symbol:
                        continue
                        
                    if position_side and position['position_side'] != position_side:
                        continue
                        
                    result[strat][exch][sym] = position
        
        return result

    def get_strategy_positions(self, strategy=None, exchange=None, symbol=None):
        """
        获取持仓信息，支持多维度筛选
        如果只提供strategy参数，返回该策略的所有持仓
        """
        if strategy is None:
            return self.positions
        
        if strategy not in self.positions:
            return {}
        
        strategy_data = self.positions[strategy]
        
        # 如果没有指定exchange和symbol，返回整个策略的持仓
        if exchange is None and symbol is None:
            return strategy_data
        
        result = {}
        for exch, symbols in strategy_data.items():
            if exchange and exch != exchange:
                continue
                
            result[exch] = {}
            for sym, position in symbols.items():
                if symbol and sym != symbol:
                    continue
                result[exch][sym] = position
        
        return result


    def get_exchange_positions(self, exchange):
        """获取特定交易所的所有持仓"""
        result = {}
        for strategy, exchanges in self.positions.items():
            if exchange in exchanges:
                result[strategy] = {exchange: exchanges[exchange]}
        return result

    def has_position(self, strategy, exchange, symbol):
        """检查是否有特定持仓"""
        return (strategy in self.positions and 
                exchange in self.positions[strategy] and 
                symbol in self.positions[strategy][exchange])

    def get_entry_price(self, strategy, exchange, symbol):
        """获取特定持仓的买入价格"""
        if self.has_position(strategy, exchange, symbol):
            return self.positions[strategy][exchange][symbol]["entry_price"]
        return None

    def get_balance(self):
        """获取当前余额"""
        return self.balance

    def get_trade_history(self, strategy=None, exchange=None, symbol=None, action=None):
        """获取交易历史，支持多维度筛选"""
        filtered_records = []
        
        for record in self.trade_records:
            if strategy and record.get('strategy') != strategy:
                continue
            if exchange and record.get('exchange') != exchange:
                continue
            if symbol and record.get('symbol') != symbol:
                continue
            if action and record.get('action') != action:
                continue
            filtered_records.append(record)
        
        return filtered_records

    def get_strategy_performance(self, strategy=None):
        """获取策略表现统计"""
        if strategy:
            return self.strategy_performance.get(strategy, {})
        return self.strategy_performance

    def close_all_positions(self, current_prices):
        """平掉所有持仓"""
        for strategy, exchanges in list(self.positions.items()):
            for exchange, symbols in list(exchanges.items()):
                for symbol in list(symbols.keys()):
                    price = current_prices.get((strategy, exchange, symbol), symbols[symbol]['entry_price'])
                    self.sell(strategy, exchange, symbol, price)