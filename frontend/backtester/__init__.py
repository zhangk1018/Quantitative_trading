"""
frontend/backtester - 回测引擎

【设计目标】
1. 接收 K线 + 策略，输出资金曲线 + 交易记录
2. 支持向量化（快）和事件驱动（灵活）两种模式
3. 严格防未来函数：每根 K 线只能用当前及历史数据
"""

from .engine import BacktestEngine, BacktestResult
from .broker import Broker, Order, Position, Trade


__all__ = [
    'BacktestEngine',
    'BacktestResult',
    'Broker',
    'Order',
    'Position',
    'Trade',
]
