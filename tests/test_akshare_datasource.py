#!/usr/bin/env python3
"""
AkShare 数据源适配器单元测试：
- _to_ak_symbol 港股 0700.HK -> 00700 / 美股 AAPL -> AAPL
- anchor_us_adj_close 读取库中最近一笔 adj_close/raw_close 返回锚点 C
- 美股 import_one 锚定：持库连接时把占位前复权 Adj Close 还原为后复权水平
"""
import sys
import os
import unittest
from unittest.mock import Mock, MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from collector.datasource.akshare import _to_ak_symbol, anchor_us_adj_close  # noqa: E402
from collector.etl import import_us_daily as m  # noqa: E402
from collector.datasource import akshare as ak_datasource  # noqa: E402


def _cursor_mock(fetchone_return):
    """构造 anchor_us_adj_close 用 `with conn.cursor() as cur` 的 mock 游标。"""
    cur = Mock()
    cur.fetchone.return_value = fetchone_return
    ctx = MagicMock()
    ctx.__enter__.return_value = cur
    conn = Mock()
    conn.cursor.return_value = ctx
    return conn


class TestToAkSymbol(unittest.TestCase):
    def test_hk_zfill_five(self):
        self.assertEqual(_to_ak_symbol('0700.HK', 'hk'), '00700')
        self.assertEqual(_to_ak_symbol('9988.HK', 'hk'), '09988')
        self.assertEqual(_to_ak_symbol('1.HK', 'hk'), '00001')

    def test_us_uppercase(self):
        self.assertEqual(_to_ak_symbol('aapl', 'us'), 'AAPL')
        self.assertEqual(_to_ak_symbol('MSFT', 'us'), 'MSFT')


class TestAnchorUsAdjClose(unittest.TestCase):
    def test_returns_ratio(self):
        conn = _cursor_mock((500.0, 100.0))  # adj_close=500, raw_close=100
        self.assertAlmostEqual(anchor_us_adj_close(conn, 'AAPL'), 5.0)

    def test_returns_1_when_no_row(self):
        conn = _cursor_mock(None)
        self.assertEqual(anchor_us_adj_close(conn, 'NEW'), 1.0)


class TestImportUsAnchoring(unittest.TestCase):
    """美股 import_one 在持有库连接时，把占位前复权 Adj Close 乘锚点还原为后复权。"""

    @patch.object(m, 'clean_and_split')
    @patch.object(m, 'anchor_us_adj_close', return_value=5.0)
    def test_dry_run_no_anchoring(self, mock_anchor, mock_clean):
        """dry-run（conn=None）不读库、不做锚定，downstream clean_and_split 拿到的仍是占位 Adj Close。"""
        src = Mock()
        df = pd.DataFrame({
            'Open': [100.0], 'High': [105.0], 'Low': [99.0], 'Close': [100.0],
            'Adj Close': [100.0], 'Volume': [1000], 'Timezone': ['America/New_York'],
            'trade_date': pd.to_datetime(['2026-09-03']),
        })
        src.download_single.return_value = df
        mock_clean.return_value = (df, None)
        m.import_one(src, None, 'AAPL', start='2026-01-01', dry_run=True)
        mock_anchor.assert_not_called()

    @patch.object(m, 'clean_and_split')
    @patch.object(m, 'anchor_us_adj_close', return_value=5.0)
    @patch.object(m, 'write_quotes')
    @patch.object(m, 'write_adj_factor')
    def test_anchoring_multiplies_adj_close(self, mock_waf, mock_wq, mock_anchor, mock_clean):
        """持库连接时：Adj Close 占位前复权 × 锚点 5.0 → 后复权，再交 clean_and_split。"""
        src = Mock()
        df = pd.DataFrame({
            'Open': [100.0], 'High': [105.0], 'Low': [99.0], 'Close': [100.0],
            'Adj Close': [100.0], 'Volume': [1000], 'Timezone': ['America/New_York'],
            'trade_date': pd.to_datetime(['2026-09-03']),
        })
        src.download_single.return_value = df
        conn = _cursor_mock(None)  # 游标无关，锚点已被 patch 返回 5.0
        mock_clean.return_value = (df, None)
        m.import_one(src, conn, 'AAPL', start='2026-01-01', dry_run=False)
        # clean_and_split 收到的 df，其 Adj Close 应为 100 * 5.0 = 500
        got = mock_clean.call_args[0][0]
        self.assertAlmostEqual(float(got['Adj Close'].iloc[0]), 500.0)


if __name__ == '__main__':
    unittest.main()