#!/usr/bin/env python3
"""
港股日线导入 - 增量 last_sync_date 条件回写逻辑单元测试
覆盖 import_hk_daily.py 建议1修复：仅在成功写入时才回写，
且回写【实际覆盖的最后交易日】而非 date.today()，避免失败轮次吞掉缺口。
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from collector.etl import import_hk_daily as m


def _fake_src():
    src = Mock()
    src.cfg.incremental_lookback_days = 7
    return src


def _fake_conn():
    """返回支持断点续传游标读写的 MagicMock 连接（fetchone 返回 None = 无游标）。"""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    return conn


class TestIncrementalWriteback(unittest.TestCase):
    """run_incremental 的条件回写行为"""

    @patch.object(m, '_list_hk_codes', return_value=['0001.HK', '0002.HK'])
    @patch.object(m, '_probe_src_latest', return_value='2026-09-04')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'import_one', return_value=(0, 0, None))
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-03')
    def test_all_failed_no_writeback(self, mock_get, mock_import, mock_set, mock_probe, mock_list):
        """全部拉取为空（0 成功）时：必须【跳过】回写 last_sync_date，保留旧进度。"""
        stats = m.run_incremental(_fake_src(), _fake_conn(), limit=2)   # --limit 强制逐只路径
        self.assertEqual(stats['quotes'], 0)
        self.assertEqual(stats['success'], 0)
        self.assertEqual(stats['fail'], 2)
        mock_set.assert_not_called()

    @patch.object(m, '_list_hk_codes', return_value=['0001.HK', '0002.HK'])
    @patch.object(m, '_probe_src_latest', return_value='2026-09-04')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, '_window_coverage_ok', return_value=True)
    @patch.object(m, 'import_one', side_effect=[
        (5, 1, '2026-09-03'),   # 0001.HK 成功，覆盖到 9/3
        (0, 0, None),           # 0002.HK 空
    ])
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-02')
    def test_partial_success_writes_actual_max_date(self, mock_get, mock_import, mock_cov,
                                                    mock_set, mock_probe, mock_list):
        """部分成功时：回写【实际覆盖的最后交易日】（9/3），而非 date.today()。"""
        src = _fake_src()
        src.download_hk_trade_dates.return_value = set()   # 无交易日历（覆盖度已 patch）
        stats = m.run_incremental(src, _fake_conn(), limit=2)   # --limit 强制逐只路径
        self.assertEqual(stats['success'], 1)
        self.assertEqual(stats['fail'], 1)
        mock_set.assert_called_once_with(mock_get.call_args.args[0], '2026-09-03')

    @patch.object(m, '_list_hk_codes', return_value=['0001.HK'])
    @patch.object(m, '_probe_src_latest', return_value='2026-09-04')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'import_one', return_value=(8, 0, '2026-09-04'))
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-03')
    def test_dry_run_no_writeback(self, mock_get, mock_import, mock_set, mock_probe, mock_list):
        """dry-run 模式即使成功也不回写。"""
        m.run_incremental(_fake_src(), _fake_conn(), dry_run=True)
        mock_set.assert_not_called()


class TestIncrementalProbeLatest(unittest.TestCase):
    """run_incremental 数据源最新日期探测（防新浪延迟空跑）"""

    def _frame_latest(self, latest_date):
        """构造 index 为 DatetimeIndex 的探针返回 DataFrame。"""
        idx = pd.to_datetime(['2026-09-02', latest_date])
        return pd.DataFrame({'Open': [1.0, 2.0]}, index=idx)

    def test_probe_earlier_end(self):
        """数据源最新 9/3 < 今天：探针把窗口终点降级为 9/3（而非今天），避免整批空跑。"""
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = self._frame_latest('2026-09-03')
        self.assertEqual(m._probe_src_latest(src, '2026-09-04'), '2026-09-03')

    @patch.object(m, '_list_hk_codes')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'import_one')
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-03')
    def test_probe_earlier_than_start_skip(self, mock_get, mock_import, mock_set, mock_list):
        """数据源最新(9/2)早于增量起点(9/4)：整轮跳过，不拉取、不回写。"""
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = self._frame_latest('2026-09-02')
        stats = m.run_incremental(src, _fake_conn())
        self.assertEqual(stats['quotes'], 0)
        self.assertEqual(stats['success'], 0)
        mock_import.assert_not_called()
        mock_set.assert_not_called()

    @patch.object(m, '_list_hk_codes')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'import_one')
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-03')
    def test_snapshot_unavailable_fails_fast(self, mock_get, mock_import, mock_set, mock_list):
        """快照源不可用 → 非零退出快失败，不再静默回退逐只空转（协作单 53.0）。

        旧行为：沿用今天为终点 → 回退逐只路径 → 当日窗口拿不到数据、空转数小时且 exit=0。
        """
        src = _fake_src()
        src.download_hk_snapshot_all.return_value = None
        with self.assertRaises(SystemExit) as ctx:
            m.run_incremental(src, _fake_conn())
        self.assertNotEqual(ctx.exception.code, 0)
        mock_import.assert_not_called()
        mock_set.assert_not_called()


class TestInitWriteback(unittest.TestCase):
    """run_init 的全量失败不推进 last_sync_date"""

    @patch.object(m, '_list_hk_codes', return_value=['0001.HK'])
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'import_one', return_value=(0, 0, None))
    def test_all_failed_no_writeback(self, mock_import, mock_set, mock_list):
        """全量导入全部为空时：跳过回写。"""
        stats = m.run_init(_fake_src(), _fake_conn())
        self.assertEqual(stats['quotes'], 0)
        mock_set.assert_not_called()


class TestInitStartDate(unittest.TestCase):
    """run_init 指定 start_date：按 [起始日期, 今天] 区间拉取而非全量 period"""

    def _setup(self, mock_import, mock_getproc, mock_setproc, mock_set, mock_list):
        mock_list.return_value = ['0001.HK']
        mock_import.return_value = (5, 0, '2026-09-03')
        mock_getproc.return_value = None
        return m.run_init(_fake_src(), _fake_conn(), start_date='2025-01-01')

    @patch.object(m, '_list_hk_codes')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'set_market_last_processed_code')
    @patch.object(m, 'get_market_last_processed_code')
    @patch.object(m, 'import_one')
    def test_start_date_uses_interval(self, mock_import, mock_getproc, mock_setproc, mock_set, mock_list):
        """指定 start_date：import_one 用 start/end 区间（而非 period）。"""
        self._setup(mock_import, mock_getproc, mock_setproc, mock_set, mock_list)
        _, kwargs = mock_import.call_args
        self.assertEqual(kwargs.get('start'), '2025-01-01')
        self.assertIsNotNone(kwargs.get('end'))
        self.assertNotIn('period', kwargs)

    @patch.object(m, '_list_hk_codes')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'set_market_last_processed_code')
    @patch.object(m, 'get_market_last_processed_code')
    @patch.object(m, 'import_one')
    def test_no_start_date_uses_period(self, mock_import, mock_getproc, mock_setproc, mock_set, mock_list):
        """未指定 start_date：import_one 用 period（全量）。"""
        mock_list.return_value = ['0001.HK']
        mock_import.return_value = (5, 0, '2026-09-03')
        mock_getproc.return_value = None
        m.run_init(_fake_src(), _fake_conn())
        _, kwargs = mock_import.call_args
        self.assertIn('period', kwargs)
        self.assertNotIn('start', kwargs)


if __name__ == '__main__':
    unittest.main()
