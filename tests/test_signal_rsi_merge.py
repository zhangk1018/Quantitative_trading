#!/usr/bin/env python3
"""
signal_service._generate_rsi_signals 连续超买/超卖段合并逻辑单元测试
覆盖协作单 34.1：一段连续超买/超卖只产出 1 条拐点信号（退出阈值当天）。
"""
import sys
import os
import unittest
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.service.signal_service import SignalService


def _make_df(rsis):
    """构造升序日期 DataFrame：date/close/rsi_6"""
    n = len(rsis)
    return pd.DataFrame({
        'date': [date(2026, 9, 1 + i) for i in range(n)],
        'close': [10.0 + i for i in range(n)],
        'rsi_6': rsis,
    })


class TestRsiSignals(unittest.TestCase):
    """RSI 信号合并（每段 1 条拐点）"""

    def test_single_overbought_segment(self):
        """连续 5 日超买（>70）→ 仅在回落日产出 1 条超买信号"""
        df = _make_df([72, 75, 78, 80, 76, 68, 60])  # 6/1-6/5 超买，6/6 回落到 68
        sigs = SignalService.__new__(SignalService)._generate_rsi_signals(df)
        ob = [s for s in sigs if s.signal_type == 'rsi_overbought']
        os_ = [s for s in sigs if s.signal_type == 'rsi_oversold']
        self.assertEqual(len(ob), 1, '超买段应只产 1 条信号')
        self.assertEqual(len(os_), 0)
        self.assertEqual(ob[0].trade_date, date(2026, 9, 6), '信号应落在退出超买区当天')
        self.assertIn('< 70', ob[0].reason)

    def test_alternating_ob_os(self):
        """超买→回落→超卖→回升 交替：各段 1 条，共 2 条"""
        df = _make_df([75, 65, 40, 25, 20, 35, 55])  # 9/1超买,9/2回落; 9/4-5超卖,9/6回升
        sigs = SignalService.__new__(SignalService)._generate_rsi_signals(df)
        self.assertEqual(len(sigs), 2)
        types = sorted(s.signal_type for s in sigs)
        self.assertEqual(types, ['rsi_overbought', 'rsi_oversold'])
        dates = sorted(s.trade_date for s in sigs)
        self.assertEqual(dates, [date(2026, 9, 2), date(2026, 9, 6)])

    def test_flat_rsi_no_signal(self):
        """RSI 全程在 30-70 区间 → 无信号"""
        df = _make_df([50, 55, 45, 60, 40])
        sigs = SignalService.__new__(SignalService)._generate_rsi_signals(df)
        self.assertEqual(len(sigs), 0)

    def test_end_of_data_still_overbought(self):
        """序列末尾仍在超买区（未回落）→ 不产出信号（无拐点确认）"""
        df = _make_df([60, 72, 75, 80])  # 末尾 3 日超买但无回落
        sigs = SignalService.__new__(SignalService)._generate_rsi_signals(df)
        self.assertEqual(len(sigs), 0)

    def test_single_day_df(self):
        """单日数据 → 无信号（无法确认拐点）"""
        df = _make_df([80])
        sigs = SignalService.__new__(SignalService)._generate_rsi_signals(df)
        self.assertEqual(len(sigs), 0)

    def test_reenter_after_exit(self):
        """回落出超买区后再次进入并回落 → 2 条独立超买信号"""
        df = _make_df([72, 68, 74, 66])  # 段1: 9/1超买→9/2回落; 段2: 9/3超买→9/4回落
        sigs = SignalService.__new__(SignalService)._generate_rsi_signals(df)
        ob = [s for s in sigs if s.signal_type == 'rsi_overbought']
        self.assertEqual(len(ob), 2)


if __name__ == '__main__':
    unittest.main()
