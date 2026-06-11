"""
my_strategies.py - 内置示例策略

包含：
- DoubleMAStrategy: 双均线（经典）
- MACrossStrategy: 均线交叉（金叉死叉）
- RSIStrategy: RSI 超买超卖
- BollBandStrategy: 布林带突破
"""

import pandas as pd
from typing import Dict, List

from .base_strategy import BaseStrategy
from shared.constants import SignalType


class DoubleMAStrategy(BaseStrategy):
    """
    双均线策略

    信号：
    - 短期均线上穿长期均线 → buy
    - 短期均线下穿长期均线 → sell
    - 否则 → hold
    """
    name = 'double_ma'
    description = '双均线策略：快线上穿慢线买入，下穿卖出'
    params = {'fast': 5, 'slow': 20}

    def generate_signals(self, df: pd.DataFrame) -> List[str]:
        if df.empty or len(df) < self.params['slow']:
            return ['hold'] * len(df)

        signals = []
        prev_signal = 'hold'
        fast = self.params['fast']
        slow = self.params['slow']

        for i in range(len(df)):
            if i < slow:
                signals.append('hold')
                continue

            fast_ma = df['close'].iloc[i - fast + 1:i + 1].mean()
            slow_ma = df['close'].iloc[i - slow + 1:i + 1].mean()

            # 金叉：快线从下方穿越到上方
            if prev_signal in ('hold', 'sell') and fast_ma > slow_ma:
                signals.append('buy')
                prev_signal = 'buy'
            # 死叉：快线从上方穿越到下方
            elif prev_signal in ('hold', 'buy') and fast_ma < slow_ma:
                signals.append('sell')
                prev_signal = 'sell'
            else:
                signals.append('hold')

        return signals


class MACrossStrategy(BaseStrategy):
    """
    均线交叉策略（更严格的版本，必须金叉/死叉当日才触发）
    """
    name = 'ma_cross'
    description = '金叉死叉：当日发生穿越才触发'
    params = {'fast': 5, 'slow': 20}

    def generate_signals(self, df: pd.DataFrame) -> List[str]:
        if df.empty or len(df) < self.params['slow'] + 1:
            return ['hold'] * len(df)

        fast = self.params['fast']
        slow = self.params['slow']

        # 一次性计算所有均线（向量化，比 for 循环快 100x）
        fast_ma = df['close'].rolling(window=fast).mean()
        slow_ma = df['close'].rolling(window=slow).mean()

        signals = ['hold'] * len(df)
        for i in range(slow, len(df)):
            # 当日快线 vs 慢线
            if fast_ma.iloc[i] > slow_ma.iloc[i] and fast_ma.iloc[i - 1] <= slow_ma.iloc[i - 1]:
                signals[i] = 'buy'
            elif fast_ma.iloc[i] < slow_ma.iloc[i] and fast_ma.iloc[i - 1] >= slow_ma.iloc[i - 1]:
                signals[i] = 'sell'
        return signals


class RSIStrategy(BaseStrategy):
    """
    RSI 超买超卖策略

    信号：
    - RSI < 超卖线（默认 30）→ buy
    - RSI > 超买线（默认 70）→ sell
    """
    name = 'rsi'
    description = 'RSI超买超卖：RSI<30买入，RSI>70卖出'
    params = {'period': 14, 'oversold': 30, 'overbought': 70}

    def _calc_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def generate_signals(self, df: pd.DataFrame) -> List[str]:
        if df.empty or len(df) < self.params['period'] + 1:
            return ['hold'] * len(df)

        rsi = self._calc_rsi(df['close'], self.params['period'])
        signals = ['hold'] * len(df)
        for i in range(self.params['period'] + 1, len(df)):
            if pd.isna(rsi.iloc[i]):
                continue
            if rsi.iloc[i] < self.params['oversold']:
                signals[i] = 'buy'
            elif rsi.iloc[i] > self.params['overbought']:
                signals[i] = 'sell'
        return signals


class BollBandStrategy(BaseStrategy):
    """
    布林带策略

    信号：
    - 收盘价跌破下轨 → buy（超卖反弹）
    - 收盘价升破上轨 → sell（超买回落）
    """
    name = 'boll'
    description = '布林带：跌破下轨买入，升破上轨卖出'
    params = {'period': 20, 'num_std': 2.0}

    def generate_signals(self, df: pd.DataFrame) -> List[str]:
        if df.empty or len(df) < self.params['period']:
            return ['hold'] * len(df)

        period = self.params['period']
        std_num = self.params['num_std']
        mid = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper = mid + std_num * std
        lower = mid - std_num * std

        signals = ['hold'] * len(df)
        for i in range(period, len(df)):
            if pd.isna(mid.iloc[i]):
                continue
            if df['close'].iloc[i] < lower.iloc[i]:
                signals[i] = 'buy'
            elif df['close'].iloc[i] > upper.iloc[i]:
                signals[i] = 'sell'
        return signals
