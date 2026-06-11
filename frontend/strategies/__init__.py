"""
frontend/strategies - 策略模块

【设计目标】
- 策略与回测引擎解耦：策略只关心"看到数据后怎么办"
- 提供两种接口：
  1. 事件驱动: on_bar(bar) - 模拟实盘，一根 K 线触发一次
  2. 向量化: generate_signals(df) - 一次性输出所有信号
"""

from .base_strategy import BaseStrategy
from .my_strategies import (
    DoubleMAStrategy,
    MACrossStrategy,
    RSIStrategy,
    BollBandStrategy,
)


__all__ = [
    'BaseStrategy',
    'DoubleMAStrategy',
    'MACrossStrategy',
    'RSIStrategy',
    'BollBandStrategy',
]
