"""
frontend/analyzer - 绩效分析模块

【设计目标】
接收回测引擎输出的资金曲线和交易记录，计算：
- 总收益率 & 年化收益率（CAGR）
- 最大回撤（Max Drawdown）及持续时间
- 夏普比率（Sharpe Ratio）& 索提诺比率（Sortino Ratio）
- 胜率（Win Rate）& 盈亏比（Profit/Loss Ratio）
- 卡尔玛比率（Calmar Ratio）
"""

from .metrics import (
    calculate_metrics,
    PerformanceMetrics,
)


__all__ = [
    'calculate_metrics',
    'PerformanceMetrics',
]
