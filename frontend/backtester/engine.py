"""
engine.py - 回测引擎

【两种模式】
1. 向量化（推荐）：先生成所有信号，再批量撮合。速度快，适合参数扫描。
2. 事件驱动：一根 K 线一根 K 线模拟。速度慢但灵活，支持止损/止盈。

【使用示例】
```python
from frontend.backtester import BacktestEngine
from frontend.strategies import DoubleMAStrategy

engine = BacktestEngine(
    strategy=DoubleMAStrategy(fast=5, slow=20),
    initial_cash=1_000_000,
)
result = engine.run(df, stock_code='000001.SZ')
print(result.metrics.summary())
```
"""

import logging
from typing import Dict, Optional

import pandas as pd

from frontend.backtester.broker import Broker
from frontend.strategies.base_strategy import BaseStrategy
from frontend.analyzer.metrics import calculate_metrics, PerformanceMetrics

logger = logging.getLogger(__name__)


class BacktestResult:
    """回测结果"""
    def __init__(
        self,
        equity_curve: pd.Series,
        trades: list,
        metrics: PerformanceMetrics,
        signals: list,
    ):
        self.equity_curve = equity_curve
        self.trades = trades
        self.metrics = metrics
        self.signals = signals

    def __repr__(self):
        return f'<BacktestResult trades={self.metrics.total_trades} return={self.metrics.total_return*100:.2f}%>'


class BacktestEngine:
    """
    回测引擎（向量化 + 事件驱动混合）

    流程：
    1. 加载 K线 + 策略
    2. 调用 strategy.generate_signals() 生成所有信号
    3. 遍历每根 K 线，根据信号调用 broker.buy() / broker.sell()
    4. 计算绩效指标
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        stamp_tax_rate: float = 0.001,
        slippage: float = 0.001,
    ):
        self.strategy = strategy
        self.broker = Broker(
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            stamp_tax_rate=stamp_tax_rate,
            slippage=slippage,
        )

    def run(
        self,
        df: pd.DataFrame,
        stock_code: str = '',
        risk_free_rate: float = 0.025,
    ) -> BacktestResult:
        """
        执行回测

        Args:
            df: K线 DataFrame, columns = [trade_date, open, high, low, close, volume, ...]
                必须按 trade_date 升序
            stock_code: 股票代码（用于 trade 记录）

        Returns:
            BacktestResult
        """
        if df.empty:
            raise ValueError('K线数据为空')

        # 标准化索引
        df = df.copy()
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.sort_values('trade_date').reset_index(drop=True)

        logger.info(f'🚀 回测开始: {self.strategy.name}, 数据 {len(df)} 根, 股票 {stock_code}')

        # 1. 生成信号
        signals = self.strategy.generate_signals(df)
        logger.info(f'  ✅ 信号生成完成: buy={signals.count("buy")} sell={signals.count("sell")}')

        # 2. 逐根 K 线撮合
        for i, row in df.iterrows():
            trade_date = row['trade_date']
            if hasattr(trade_date, 'strftime'):
                trade_date_str = trade_date.strftime('%Y-%m-%d')
            else:
                trade_date_str = str(trade_date)[:10]

            signal = signals[i]

            if signal == 'buy':
                self.broker.buy(
                    stock_code=stock_code,
                    price=row['close'],
                    trade_date=trade_date_str,
                    reason=f'{self.strategy.name}_buy',
                )
            elif signal == 'sell':
                self.broker.sell(
                    stock_code=stock_code,
                    price=row['close'],
                    trade_date=trade_date_str,
                    reason=f'{self.strategy.name}_sell',
                )

            # 记录当日权益
            self.broker.update_equity(
                trade_date=trade_date_str,
                prices={stock_code: row['close']} if stock_code else {},
            )

        # 3. 强制平仓（最后一日）
        if self.broker.positions:
            last = df.iloc[-1]
            last_date = last['trade_date']
            if hasattr(last_date, 'strftime'):
                last_date_str = last_date.strftime('%Y-%m-%d')
            else:
                last_date_str = str(last_date)[:10]
            for code in list(self.broker.positions.keys()):
                self.broker.sell(code, last['close'], last_date_str, reason='force_close')

        # 4. 计算绩效
        equity_curve = self.broker.get_equity_curve()
        trades = self.broker.get_trades()
        metrics = calculate_metrics(equity_curve, trades, risk_free_rate)

        logger.info(metrics.summary())

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            metrics=metrics,
            signals=signals,
        )
