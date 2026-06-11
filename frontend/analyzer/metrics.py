"""
metrics.py - 绩效指标计算

【输入】
- equity_curve: pd.Series, 索引=日期, 值=每日总资产
- trades: List[Dict], 每个 dict 包含:
  {'open_date': str, 'close_date': str, 'side': 'long'|'short',
   'open_price': float, 'close_price': float, 'pnl': float, 'return': float}

【输出】
PerformanceMetrics dataclass, 包含所有计算好的指标
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """绩效指标汇总"""
    # 收益指标
    total_return: float = 0.0           # 总收益率
    annual_return: float = 0.0          # 年化收益率
    cagr: float = 0.0                   # 复合年增长率

    # 风险指标
    max_drawdown: float = 0.0           # 最大回撤（%）
    max_drawdown_days: int = 0          # 最大回撤持续天数
    volatility: float = 0.0             # 年化波动率

    # 风险调整收益
    sharpe_ratio: float = 0.0           # 夏普比率
    sortino_ratio: float = 0.0          # 索提诺比率
    calmar_ratio: float = 0.0           # 卡尔玛比率

    # 交易统计
    total_trades: int = 0               # 总交易次数
    win_rate: float = 0.0               # 胜率
    profit_loss_ratio: float = 0.0      # 盈亏比
    avg_return: float = 0.0             # 平均单笔收益
    max_consecutive_wins: int = 0       # 最大连胜
    max_consecutive_losses: int = 0     # 最大连亏

    def to_dict(self) -> Dict:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"\n{'='*50}\n"
            f"  📊 绩效总结\n"
            f"{'='*50}\n"
            f"  💰 总收益: {self.total_return*100:.2f}%  |  年化: {self.annual_return*100:.2f}%\n"
            f"  📉 最大回撤: {self.max_drawdown*100:.2f}%  ({self.max_drawdown_days}天)\n"
            f"  📈 夏普比率: {self.sharpe_ratio:.2f}  |  索提诺: {self.sortino_ratio:.2f}\n"
            f"  🎯 胜率: {self.win_rate*100:.2f}%  |  盈亏比: {self.profit_loss_ratio:.2f}\n"
            f"  📊 交易次数: {self.total_trades}  |  卡尔玛: {self.calmar_ratio:.2f}\n"
            f"{'='*50}"
        )


def calculate_metrics(
    equity_curve: pd.Series,
    trades: Optional[List[Dict]] = None,
    risk_free_rate: float = 0.025,  # 无风险利率 2.5%
) -> PerformanceMetrics:
    """
    计算绩效指标

    Args:
        equity_curve: 资金曲线（索引=日期, 值=总资产）
        trades: 交易记录列表
        risk_free_rate: 年化无风险利率

    Returns:
        PerformanceMetrics
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return PerformanceMetrics()

    # 收益指标
    initial = equity_curve.iloc[0]
    final = equity_curve.iloc[-1]
    total_return = (final - initial) / initial
    days = (equity_curve.index[-1] - equity_curve.index[0]).days or 1
    years = days / 365.25
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    cagr = annual_return

    # 风险指标
    daily_returns = equity_curve.pct_change().dropna()
    volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0

    # 最大回撤
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax
    max_drawdown = drawdown.min()
    # 找最大回撤持续天数
    max_dd_end = drawdown.idxmin()
    max_dd_start = equity_curve[:max_dd_end].idxmax()
    max_dd_days = (max_dd_end - max_dd_start).days if max_dd_end and max_dd_start else 0

    # 夏普比率（年化）
    excess_return = annual_return - risk_free_rate
    sharpe_ratio = excess_return / volatility if volatility > 0 else 0

    # 索提诺比率（只考虑下行波动）
    downside_returns = daily_returns[daily_returns < 0]
    downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
    sortino_ratio = excess_return / downside_vol if downside_vol > 0 else 0

    # 卡尔玛比率
    calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0

    # 交易统计
    total_trades = 0
    win_rate = 0.0
    profit_loss_ratio = 0.0
    avg_return = 0.0
    max_wins = 0
    max_losses = 0

    if trades:
        pnls = [t.get('pnl', 0) for t in trades]
        total_trades = len(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        avg_return = np.mean(pnls) / initial if initial > 0 else 0

        # 最大连胜/连亏
        cur_wins = cur_losses = 0
        for p in pnls:
            if p > 0:
                cur_wins += 1
                cur_losses = 0
                max_wins = max(max_wins, cur_wins)
            elif p < 0:
                cur_losses += 1
                cur_wins = 0
                max_losses = max(max_losses, cur_losses)
            else:
                cur_wins = cur_losses = 0

    return PerformanceMetrics(
        total_return=float(total_return),
        annual_return=float(annual_return),
        cagr=float(cagr),
        max_drawdown=float(max_drawdown),
        max_drawdown_days=int(max_dd_days),
        volatility=float(volatility),
        sharpe_ratio=float(sharpe_ratio),
        sortino_ratio=float(sortino_ratio),
        calmar_ratio=float(calmar_ratio),
        total_trades=total_trades,
        win_rate=float(win_rate),
        profit_loss_ratio=float(profit_loss_ratio),
        avg_return=float(avg_return),
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
    )
