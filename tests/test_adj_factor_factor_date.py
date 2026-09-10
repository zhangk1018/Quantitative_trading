#!/usr/bin/env python3
"""
31.0 协作单：复权因子除权日（factor_date）口径单元测试

覆盖 sync_adj_factor.expand_factor_to_daily 的 factor_date 打标逻辑：
按 detect_factor_dates 口径（因子相对上一日变化 >1%）标记除权生效日。
"""
import sys
import os
import unittest
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from collector.etl.sync_adj_factor import expand_factor_to_daily  # noqa: E402


class TestExpandFactorToDailyFactorDate(unittest.TestCase):
    """expand_factor_to_daily 的 factor_date 打标边界"""

    @staticmethod
    def _fdates(res: pd.DataFrame) -> list:
        df = res[res['factor_date'].notna()].sort_values('trade_date')
        return [d for d in df['trade_date'].tolist()]

    def test_seed_large_change_marks(self):
        """大除权（1.0→0.9=10%）标记；微小变化（0.898/0.9≈0.22%）不标记。"""
        df = pd.DataFrame({
            'date': ['2026-06-12', '2026-06-25'],
            'qfq_factor': [0.9, 0.898],
        })
        res = expand_factor_to_daily('000001', df, date(2026, 6, 1), date(2026, 7, 1), prev_factor_seed=1.0)
        self.assertEqual(self._fdates(res), [date(2026, 6, 12)])

    def test_no_seed_first_change_not_marked(self):
        """无 prev_factor_seed 时，窗口内首个变更日无更早基准，不标记（不含除权生效日的确定判断）。"""
        df = pd.DataFrame({'date': ['2026-06-12'], 'qfq_factor': [0.8]})
        res = expand_factor_to_daily('000001', df, date(2026, 6, 1), date(2026, 7, 1))
        self.assertEqual(self._fdates(res), [])

    def test_seed_inclusive_first_change_marked(self):
        """有 prev_factor_seed 且变更日在窗口首日 → 窗口首日标记为除权生效日。"""
        df = pd.DataFrame({'date': ['2026-06-01'], 'qfq_factor': [0.8]})
        res = expand_factor_to_daily('000001', df, date(2026, 6, 1), date(2026, 7, 1), prev_factor_seed=1.0)
        self.assertEqual(self._fdates(res), [date(2026, 6, 1)])

    def test_no_exdivid_never_marks(self):
        """全程因子≈1.0（无除权）→ 无任何 factor_date。"""
        df = pd.DataFrame({'date': ['2026-06-12'], 'qfq_factor': [1.0]})
        res = expand_factor_to_daily('000001', df, date(2026, 6, 1), date(2026, 7, 1))
        self.assertEqual(self._fdates(res), [])

    def test_output_shape_includes_factor_date(self):
        """展开结果含 factor_date 列，且每日一条。"""
        df = pd.DataFrame({'date': ['2026-06-12'], 'qfq_factor': [0.9]})
        res = expand_factor_to_daily('000001', df, date(2026, 6, 1), date(2026, 6, 5), prev_factor_seed=1.0)
        self.assertIn('factor_date', res.columns)
        self.assertEqual(len(res), 5)
        # 6/12 变更在展开末段外（6/1~6/5），seed=1.0 全额一致 → 无标记
        self.assertEqual(self._fdates(res), [])


if __name__ == '__main__':
    unittest.main()