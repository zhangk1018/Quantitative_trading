"""
broker.py - 模拟撮合器

【职责】
1. 处理买卖订单（按收盘价成交，可配置滑点）
2. 计算手续费（双边收取）
3. 维护账户（现金、持仓、市值）

【避坑指南】
1. 撮合价格必须是"次日开盘价"或"当日收盘价"，不能是未来价格
2. 手续费按"成交金额"计算，不是"成交股数"
3. T+1 规则：A 股当日买入次日才能卖出
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd


@dataclass
class Order:
    """订单"""
    stock_code: str
    side: str            # 'buy' / 'sell'
    price: float
    quantity: int
    trade_date: str      # 成交日期（YYYY-MM-DD）
    reason: str = ''     # 信号原因

    @property
    def amount(self) -> float:
        return self.price * self.quantity


@dataclass
class Position:
    """持仓"""
    stock_code: str
    quantity: int
    avg_cost: float      # 平均成本
    open_date: str

    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_cost) * self.quantity


@dataclass
class Trade:
    """完成的交易"""
    stock_code: str
    side: str            # 'long' (买入开仓) / 'short' (卖出平仓) - 简化只做多
    open_date: str
    close_date: str
    open_price: float
    close_price: float
    quantity: int
    pnl: float = 0.0
    return_pct: float = 0.0
    commission: float = 0.0


class Broker:
    """
    模拟撮合器（A 股规则）
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.0003,   # 手续费率（万三）
        stamp_tax_rate: float = 0.001,     # 印花税（千一，卖出收取）
        slippage: float = 0.001,           # 滑点（千一）
        lot_size: int = 100,               # A 股最小 100 股
        t_plus_1: bool = True,             # T+1 规则
    ):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.stamp_tax_rate = stamp_tax_rate
        self.slippage = slippage
        self.lot_size = lot_size
        self.t_plus_1 = t_plus_1

        self.positions: Dict[str, Position] = {}
        self.open_trades: Dict[str, Trade] = {}   # stock_code -> 持仓中的 trade
        self.trades: List[Trade] = []            # 已平仓
        self.equity_curve: List[Dict] = []        # [{date, cash, position_value, total}]

    def _round_lots(self, quantity: int) -> int:
        """A 股最小 100 股，向下取整"""
        return (quantity // self.lot_size) * self.lot_size

    def _calc_commission(self, amount: float, is_buy: bool) -> float:
        """计算手续费（最低 5 元）"""
        commission = max(amount * self.commission_rate, 5.0)
        if not is_buy:
            commission += amount * self.stamp_tax_rate  # 卖出加印花税
        return commission

    def buy(
        self,
        stock_code: str,
        price: float,
        trade_date: str,
        reason: str = '',
    ) -> Optional[Order]:
        """
        买入下单（按 price 加滑点成交）

        Returns:
            成功返回 Order，失败（资金不足）返回 None
        """
        # 应用滑点
        fill_price = price * (1 + self.slippage)
        # 计算可买股数（预留手续费）
        available_cash = self.cash * 0.99  # 留 1% 缓冲
        max_shares = self._round_lots(int(available_cash / fill_price))
        if max_shares <= 0:
            return None

        # 实际成交
        amount = fill_price * max_shares
        commission = self._calc_commission(amount, is_buy=True)
        total_cost = amount + commission

        if total_cost > self.cash:
            return None

        self.cash -= total_cost

        # 更新持仓
        if stock_code in self.positions:
            pos = self.positions[stock_code]
            total_qty = pos.quantity + max_shares
            pos.avg_cost = (pos.avg_cost * pos.quantity + fill_price * max_shares) / total_qty
            pos.quantity = total_qty
        else:
            self.positions[stock_code] = Position(
                stock_code=stock_code,
                quantity=max_shares,
                avg_cost=fill_price,
                open_date=trade_date,
            )
            self.open_trades[stock_code] = Trade(
                stock_code=stock_code,
                side='long',
                open_date=trade_date,
                close_date='',
                open_price=fill_price,
                close_price=0.0,
                quantity=max_shares,
            )

        return Order(
            stock_code=stock_code,
            side='buy',
            price=fill_price,
            quantity=max_shares,
            trade_date=trade_date,
            reason=reason,
        )

    def sell(
        self,
        stock_code: str,
        price: float,
        trade_date: str,
        reason: str = '',
    ) -> Optional[Order]:
        """
        卖出下单（按 price 减滑点成交）

        Returns:
            成功返回 Order，失败（无持仓）返回 None
        """
        if stock_code not in self.positions or self.positions[stock_code].quantity == 0:
            return None

        pos = self.positions[stock_code]

        # T+1 检查
        if self.t_plus_1 and pos.open_date == trade_date:
            return None

        fill_price = price * (1 - self.slippage)
        amount = fill_price * pos.quantity
        commission = self._calc_commission(amount, is_buy=False)
        proceeds = amount - commission

        self.cash += proceeds

        # 平仓 trade
        if stock_code in self.open_trades:
            trade = self.open_trades.pop(stock_code)
            trade.close_date = trade_date
            trade.close_price = fill_price
            trade.pnl = proceeds - (fill_price * trade.quantity * 0)  # 简化：买入成本已在 cash 扣除
            trade.return_pct = (fill_price - trade.open_price) / trade.open_price
            trade.commission = commission
            self.trades.append(trade)

        # 清理持仓
        del self.positions[stock_code]

        return Order(
            stock_code=stock_code,
            side='sell',
            price=fill_price,
            quantity=pos.quantity,
            trade_date=trade_date,
            reason=reason,
        )

    def update_equity(self, trade_date: str, prices: Dict[str, float]):
        """
        记录每日权益（按当日收盘价）
        """
        position_value = sum(
            pos.market_value(prices.get(pos.stock_code, pos.avg_cost))
            for pos in self.positions.values()
        )
        total = self.cash + position_value
        self.equity_curve.append({
            'date': trade_date,
            'cash': self.cash,
            'position_value': position_value,
            'total': total,
        })

    def get_equity_curve(self) -> pd.Series:
        """返回资金曲线 Series"""
        if not self.equity_curve:
            return pd.Series(dtype=float)
        df = pd.DataFrame(self.equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date')['total']

    def get_trades(self) -> List[Dict]:
        """返回交易记录"""
        return [
            {
                'stock_code': t.stock_code,
                'open_date': t.open_date,
                'close_date': t.close_date,
                'open_price': t.open_price,
                'close_price': t.close_price,
                'quantity': t.quantity,
                'pnl': t.pnl,
                'return': t.return_pct,
            }
            for t in self.trades
        ]
