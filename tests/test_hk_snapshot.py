#!/usr/bin/env python3
"""
港股「当日增量」批量快照加速 - 单元测试

覆盖 import_hk_daily.py 的批量快照路径：
- 数据源层 download_hk_snapshot_all 的快照 → 规范化代码 + 数值容错
- _hk_snapshot_latest 复权锚点读取
- _hk_rate_diverges 除权疑似检测
- _snapshot_quotes_df 锚定换算（原始价 × C → 后复权价）
- import_hk_snapshot_daily 主流程（直写/无锚点回退/除权回退/空快照）
- _window_is_single_day 窗口判定（仅最新单日才启用批量）
- run_incremental 批量路径接入与 last_sync_date 回写
"""
import sys
import os
import unittest
from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from collector.etl import import_hk_daily as m  # noqa: E402


def _fake_src():
    src = Mock()
    src.cfg.incremental_lookback_days = 7
    src.cfg.timezone = 'Asia/Hong_Kong'
    return src


def _fake_conn():
    """返回支持游标读写的 MagicMock 连接（fetchone=None = 无锚点）。"""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    return conn


def _snapshot_frame(codes=('0700.HK', '9988.HK')):
    """构造与 download_hk_snapshot_all 同构的快照 DataFrame（索引=交易日期，列含 code）。"""
    d = date(2026, 9, 7)
    rows = [
        {'code': '0700.HK', 'Open': 300.0, 'High': 310.0, 'Low': 298.0,
         'Close': 305.0, 'prev_close': 302.0, 'Volume': 1000, 'Amount': 305000.0},
        {'code': '9988.HK', 'Open': 120.0, 'High': 122.0, 'Low': 118.0,
         'Close': 121.0, 'prev_close': 119.0, 'Volume': 500, 'Amount': 60500.0},
    ]
    df = pd.DataFrame(rows)
    df.insert(0, 'Date', pd.Timestamp(d))
    df = df.set_index('Date')
    df.index.name = 'Date'
    return df


class TestHkSnapshotLatest(unittest.TestCase):
    """复权锚点读取：库中最近 (adj_close, raw_close)"""

    def test_returns_anchor_tuple(self):
        conn = _fake_conn()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = ('200.0', '100.0')
        result = m._hk_snapshot_latest(conn, '0700.HK')
        self.assertEqual(result, (200.0, 100.0))

    def test_none_when_no_row(self):
        conn = _fake_conn()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        self.assertIsNone(m._hk_snapshot_latest(conn, '0700.HK'))

    def test_none_when_raw_null(self):
        # adj_close 或 raw_close 为 NULL 时视为无效锚点 → None
        # （raw_close=0 已在 SQL 层以 raw_close>0 过滤，不会到达此处判断）
        for row in ((None, '100.0'), ('200.0', None)):
            conn = _fake_conn()
            conn.cursor.return_value.__enter__.return_value.fetchone.return_value = row
            self.assertIsNone(m._hk_snapshot_latest(conn, '0700.HK'))


class TestHkRateDiverges(unittest.TestCase):
    """除权疑似检测：快照昨收 vs 库 T-1 raw_close（阈值 2%）"""

    def test_approx_equal_not_diverged(self):
        # 微差（tick 噪声 <2%）→ 正常，不回退
        self.assertFalse(m._hk_rate_diverges(302.0, 301.0))
        self.assertFalse(m._hk_rate_diverges(302.0, 302.0))
        # 低价仙股 tick 噪声 0.75%（0.66 vs 0.665）
        self.assertFalse(m._hk_rate_diverges(0.66, 0.665))

    def test_small_noise_not_diverged(self):
        # 1.2% 噪声仍在 2% 阈值内 → 不回退
        self.assertFalse(m._hk_rate_diverges(1.136, 1.15))
        # 0.77% 噪声
        self.assertFalse(m._hk_rate_diverges(19.35, 19.5))

    def test_big_divergence(self):
        # 昨收 250 vs 库最近 302 → 偏离 > 2%，判定疑似除权
        self.assertTrue(m._hk_rate_diverges(250.0, 302.0))
        # 昨收 285 vs 300（5%）→ 除权
        self.assertTrue(m._hk_rate_diverges(285.0, 300.0))

    def test_missing_prev_conservative(self):
        # 缺昨收 → 保守回退
        self.assertTrue(m._hk_rate_diverges(None, 302.0))
        self.assertTrue(m._hk_rate_diverges(302.0, None))
        self.assertTrue(m._hk_rate_diverges(302.0, 0))


class TestSnapshotQuotesDf(unittest.TestCase):
    """批量快照单行锚定换算"""

    def test_anchor_conversion(self):
        # 锚点 C = 2.0，原始 Close 305 → 后复权 610
        row = pd.Series({'Open': 300.0, 'High': 310.0, 'Low': 298.0, 'Close': 305.0,
                         'prev_close': 302.0, 'Volume': 1000})
        d = date(2026, 9, 7)
        out = m._snapshot_quotes_df('0700.HK', row, 2.0, d)
        self.assertEqual(out.iloc[0]['code'], '0700.HK')
        self.assertEqual(out.iloc[0]['close'], 610.0)        # 305 × 2
        self.assertEqual(out.iloc[0]['raw_close'], 305.0)
        self.assertEqual(out.iloc[0]['adj_close'], 610.0)
        self.assertEqual(out.iloc[0]['pre_close'], 604.0)    # 302 × 2
        self.assertEqual(out.iloc[0]['volume'], 1000)
        self.assertEqual(out.iloc[0]['amount'], 610000.0)

    def test_missing_close_returns_empty(self):
        # 无有效成交价（停牌）→ 返回空 df（调用方跳过）
        row = pd.Series({'Open': 300.0, 'High': None, 'Low': None, 'Close': None,
                         'prev_close': 302.0, 'Volume': None})
        out = m._snapshot_quotes_df('0700.HK', row, 2.0, date(2026, 9, 7))
        self.assertTrue(out.empty)

    def test_volume_conversion_and_amount_none(self):
        # Volume 缺失/负值 → volume None，amount None；pre_close 兜底为 adj_open
        row = pd.Series({'Open': 100.0, 'High': 105.0, 'Low': 99.0, 'Close': 104.0,
                         'prev_close': None, 'Volume': None})
        out = m._snapshot_quotes_df('0700.HK', row, 3.0, date(2026, 9, 7))
        r = out.iloc[0]
        self.assertIsNone(r['volume'])
        self.assertIsNone(r['amount'])
        self.assertEqual(r['pre_close'], 300.0)  # 兜底 = adj_open = 100×3


class TestImportSnapshotDaily(unittest.TestCase):
    """import_hk_snapshot_daily 主流程"""

    def setUp(self):
        # 权威除权名单走真实外网请求：测试中固定为空名单（不触发回退），避免联网/慢
        self._erx = patch.object(m, '_hk_exright_codes', return_value=set())
        self._erx.start()

    def tearDown(self):
        self._erx.stop()

    @patch.object(m, 'write_quotes', side_effect=lambda conn, df, code: len(df))
    @patch.object(m, 'resolve_one')
    @patch.object(m, '_hk_rate_diverges', return_value=False)
    @patch.object(m, '_hk_snapshot_latest', return_value=(200.0, 100.0))
    def test_direct_write(self, mock_anchor, mock_diverge, mock_resolve, mock_write):
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = _snapshot_frame()
        result = m.import_hk_snapshot_daily(_fake_conn(), src, dry_run=False)
        self.assertTrue(result['snap_ok'])
        self.assertEqual(result['direct'], 2)
        self.assertEqual(result['fallback'], 0)
        self.assertEqual(mock_write.call_count, 2)
        mock_resolve.assert_not_called()

    @patch.object(m, '_hk_snapshot_latest', return_value=None)
    @patch.object(m, 'resolve_one')
    @patch.object(m, 'write_quotes')
    def test_no_anchor_fallback(self, mock_write, mock_resolve, mock_anchor):
        """无复权锚点（新股）→ 回退 resolve_one，不直写。"""
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = _snapshot_frame()
        result = m.import_hk_snapshot_daily(_fake_conn(), src, dry_run=False)
        self.assertEqual(result['direct'], 0)
        self.assertEqual(result['fallback'], 2)
        self.assertEqual(mock_resolve.call_count, 2)
        mock_write.assert_not_called()

    @patch.object(m, '_hk_rate_diverges', return_value=True)
    @patch.object(m, '_hk_snapshot_latest', return_value=(200.0, 100.0))
    @patch.object(m, 'resolve_one')
    @patch.object(m, 'write_quotes')
    def test_diverge_fallback(self, mock_write, mock_resolve, mock_anchor, mock_diverge):
        """疑似除权 → 回退 resolve_one。"""
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = _snapshot_frame()
        result = m.import_hk_snapshot_daily(_fake_conn(), src, dry_run=False)
        self.assertEqual(result['direct'], 0)
        self.assertEqual(result['fallback'], 2)
        self.assertEqual(mock_resolve.call_count, 2)

    @patch.object(m, '_hk_exright_codes', return_value={'0700.HK'})
    @patch.object(m, '_hk_rate_diverges', return_value=False)
    @patch.object(m, '_hk_snapshot_latest', return_value=(200.0, 100.0))
    @patch.object(m, 'resolve_one')
    @patch.object(m, 'write_quotes')
    def test_exright_authoritative_fallback(self, mock_write, mock_resolve, mock_anchor, mock_diverge, mock_erx):
        """港交所权威名单命中（当日除净）→ 无视启发式，无条件回退逐只。"""
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = _snapshot_frame()
        result = m.import_hk_snapshot_daily(_fake_conn(), src, dry_run=False)
        self.assertEqual(result['direct'], 1)      # 仅 9988 直写
        self.assertEqual(result['fallback'], 1)    # 0700 权威除权回退
        self.assertEqual(result['exright'], 1)
        mock_resolve.assert_called_once()

    def test_empty_snapshot_not_ok(self):
        """快照为空 → snap_ok=False（调用方回退逐只）"""
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = None
        result = m.import_hk_snapshot_daily(_fake_conn(), src, dry_run=False)
        self.assertFalse(result['snap_ok'])


class TestWindowIsSingleDay(unittest.TestCase):
    """增量窗口判定：仅最新单日才启用批量快照"""

    def _frame_days(self, days):
        return pd.DataFrame({'Close': [1.0] * len(days)}, index=pd.to_datetime(days))

    def test_single_day_true(self):
        src = _fake_src()
        src.download_single.return_value = self._frame_days(['2026-09-03', '2026-09-04'])
        # 窗口 [09-04, 09-04] 内仅 09-04 一个交易日
        self.assertTrue(m._window_is_single_day(src, '2026-09-04', '2026-09-04'))

    def test_multi_day_false(self):
        src = _fake_src()
        src.download_single.return_value = self._frame_days(['2026-09-03', '2026-09-04'])
        # 窗口 [09-03, 09-04) 内含 09-03 交易日 → 存在缺口，回退逐只
        self.assertFalse(m._window_is_single_day(src, '2026-09-03', '2026-09-04'))

    def test_probe_fail_false(self):
        src = _fake_src()
        src.download_single.return_value = None
        self.assertFalse(m._window_is_single_day(src, '2026-09-04', '2026-09-04'))


class TestRunIncrementalBatch(unittest.TestCase):
    """run_incremental 批量快照路径接入"""

    @patch.object(m, '_list_hk_codes', return_value=['0700.HK'])
    @patch.object(m, '_probe_src_latest', return_value='2026-09-04')
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-03')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'set_market_last_processed_code')
    @patch.object(m, '_window_is_single_day', return_value=True)
    @patch.object(m, 'import_hk_snapshot_daily',
                  return_value={'snap_ok': True, 'direct': 5, 'fallback': 1, 'failed': 0})
    @patch.object(m, 'import_one')
    def test_batch_path_writes_and_returns(self, mock_import_one, mock_batch, mock_window,
                                           mock_setproc, mock_set, mock_get, mock_probe, mock_list):
        """仅最新单日 + 快照成功：整批对齐，回写 last_sync_date，不再走逐只循环。"""
        stats = m.run_incremental(_fake_src(), _fake_conn())
        self.assertEqual(stats['success'], 6)   # direct 5 + fallback 1
        self.assertEqual(stats['quotes'], 5)
        self.assertEqual(stats['max_trade_date'], '2026-09-04')
        mock_set.assert_called_once_with(mock_get.call_args.args[0], '2026-09-04')
        mock_import_one.assert_not_called()

    @patch.object(m, '_list_hk_codes', return_value=['0700.HK'])
    @patch.object(m, '_probe_src_latest', return_value='2026-09-04')
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-03')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'set_market_last_processed_code')
    @patch.object(m, '_window_is_single_day', return_value=True)
    @patch.object(m, 'import_hk_snapshot_daily',
                  return_value={'snap_ok': False, 'direct': 0, 'fallback': 0, 'failed': 0})
    @patch.object(m, 'import_one', return_value=(3, 0, '2026-09-04'))
    def test_batch_snap_fail_falls_back(self, mock_import_one, mock_batch, mock_window,
                                        mock_setproc, mock_set, mock_get, mock_probe, mock_list):
        """快照接口失败（snap_ok=False）→ 回退逐只增量路径。"""
        stats = m.run_incremental(_fake_src(), _fake_conn())
        mock_import_one.assert_called()
        self.assertEqual(stats['quotes'], 3)


# 港交所 eent.htm 表格结构样例（6 列：名称为索引1、Ex-Date 为索引4）
_EENT_HTML = """<html><body>
<table><tr><td>Dividends &amp; Other Entitlements</td></tr></table>
<table>
<tr><td></td><td>Stock Short Name (Stock Code)</td><td></td><td>Description</td><td>Ex-Date</td><td>Book Closing Date</td></tr>
<tr><td></td><td>TENCENT (00700)</td><td></td><td>FINAL DIVIDEND HKD3.4 PER SHARE</td><td>30/05</td><td>03/06</td></tr>
<tr><td></td><td>ABC (01288)</td><td></td><td>INTERIM DIVIDEND</td><td>09/09</td><td>11/09</td></tr>
<tr><td></td><td>NO PAREN CELL</td><td></td><td>DESC</td><td>09/09</td><td>11/09</td></tr>
<tr><td></td><td>OBS (00567)</td><td></td><td>DESC</td><td></td><td>NO B/C DATE</td></tr>
</table>
</body></html>"""


class TestHkExrightCodes(unittest.TestCase):
    """港交所权威除权名单解析：Ex-Date 命中 → 回退名单"""

    def _resp(self, html=_EENT_HTML):
        resp = Mock()
        resp.text = html
        resp.raise_for_status.return_value = None
        resp.status_code = 200
        return resp

    @patch.object(m.requests, 'get')
    def test_matches_exdate(self, mock_get):
        mock_get.return_value = self._resp()
        # 05/30 除净 → 0700.HK
        self.assertEqual(m._hk_exright_codes(date(2026, 5, 30)), {'0700.HK'})
        # 09/09 除净 → 零填充 01288.HK
        self.assertEqual(m._hk_exright_codes(date(2026, 9, 9)), {'1288.HK'})

    @patch.object(m.requests, 'get')
    def test_no_match_empty(self, mock_get):
        mock_get.return_value = self._resp()
        # 无任何除净日命中 → 空集合（而非 None）
        self.assertEqual(m._hk_exright_codes(date(2026, 1, 1)), set())

    @patch.object(m.requests, 'get')
    def test_fetch_failure_returns_none(self, mock_get):
        # 网络异常 → None（调用方回落启发式检测）
        mock_get.side_effect = Exception('network err')
        self.assertIsNone(m._hk_exright_codes(date(2026, 5, 30)))


if __name__ == '__main__':
    unittest.main()