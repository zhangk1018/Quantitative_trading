#!/usr/bin/env python3
"""
港股/美股下载 限流 + 断点续传 单元测试。

覆盖：
1. market_download_common.resume_codes：游标续传切片逻辑
2. import_us_daily.run_incremental 集成：每只回写游标、整批清空游标、每只调用限流、
   从上次游标处续传跳过已处理标的。
"""
import sys
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from collector.etl import market_download_common as common  # noqa: E402
from collector.etl import import_us_daily as m  # noqa: E402
from collector.etl import import_hk_daily as hk  # noqa: E402


class TestResumeCodes(unittest.TestCase):
    """断点续传游标切片逻辑"""

    CODES = ['0001.HK', '0700.HK', '9988.HK']

    def test_no_cursor_returns_all(self):
        self.assertEqual(common.resume_codes(self.CODES, None), self.CODES)
        self.assertEqual(common.resume_codes(self.CODES, ''), self.CODES)

    def test_cursor_in_middle_resumes_after(self):
        self.assertEqual(common.resume_codes(self.CODES, '0700.HK'), ['9988.HK'])

    def test_cursor_at_end_returns_empty(self):
        self.assertEqual(common.resume_codes(self.CODES, '9988.HK'), [])

    def test_cursor_not_in_list_filters_by_order(self):
        # 游标不在当前列表（列表变化防御）：按 code > 游标 过滤
        self.assertEqual(common.resume_codes(self.CODES, '0123.HK'), ['0700.HK', '9988.HK'])

    def test_input_not_mutated(self):
        codes = list(self.CODES)
        common.resume_codes(codes, '0700.HK')
        self.assertEqual(codes, self.CODES)


class TestRateLimitConfig(unittest.TestCase):
    """限流函数对 config 空值/异常的安全处理"""

    @patch('time.sleep')
    def test_config_throttles(self, mock_sleep):
        common.rate_limit_sleep(SimpleNamespace(batch_interval_min_sleep=1.0, batch_interval_max_sleep=1.0))
        mock_sleep.assert_called_once()

    @patch('time.sleep')
    def test_zero_interval_no_sleep(self, mock_sleep):
        common.rate_limit_sleep(SimpleNamespace(batch_interval_min_sleep=0.0, batch_interval_max_sleep=0.0))
        mock_sleep.assert_not_called()


def _make_src():
    cfg = SimpleNamespace(incremental_lookback_days=7,
                          batch_interval_min_sleep=1.0,
                          batch_interval_max_sleep=1.0)
    src = Mock()
    src.cfg = cfg
    return src


class TestUsIncrementalResumeAndThrottle(unittest.TestCase):
    """美股 run_incremental 断点续传 + 限流集成"""

    @patch.object(m, 'rate_limit_sleep')
    @patch.object(m, 'set_market_last_processed_code')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-02')
    @patch.object(m, '_list_us_codes', return_value=['AAPL', 'MSFT', 'NVDA'])
    @patch.object(m, 'get_market_last_processed_code', return_value='MSFT')
    @patch.object(m, 'import_one', return_value=(5, 0, '2026-09-03'))
    def test_resumes_after_cursor_and_writeback(self, mock_import, mock_getproc, mock_list,
                                                mock_getsync, mock_setlsc, mock_setproc, mock_sleep):
        """有游标 'MSFT' 时：跳过 'AAPL','MSFT'，只处理 'NVDA'，并回写游标与清空。"""
        stats = m.run_incremental(_make_src(), Mock(), dry_run=False)
        # 只处理游标之后的 NVDA
        self.assertEqual(mock_import.call_count, 1)
        self.assertEqual(mock_import.call_args.args[2], 'NVDA')
        self.assertEqual(stats['success'], 1)
        # 每只处理完回写游标
        # 断言包含：(conn, 'us', 'NVDA') 与 (conn, 'us', None)
        calls = [c.args for c in mock_setproc.call_args_list]
        any_mask = [c for c in calls if len(c) == 3 and c[1] == 'us']
        self.assertEqual(len(any_mask), 2)
        written = [c[2] for c in any_mask]
        self.assertIn('NVDA', written)   # 每只回写
        self.assertIn(None, written)     # 整批清空
        # 每只调用限流一次
        self.assertEqual(mock_sleep.call_count, 1)
        # 成功写入 → 回写 last_sync_date
        mock_setlsc.assert_called()
        # 使用游标读取（get_market_last_processed_code 被调用）
        mock_getproc.assert_called()

    @patch.object(m, 'rate_limit_sleep')
    @patch.object(m, 'set_market_last_processed_code')
    @patch.object(m, 'set_last_sync_date')
    @patch.object(m, 'get_last_sync_date', return_value='2026-09-02')
    @patch.object(m, 'get_market_last_processed_code', return_value=None)
    @patch.object(m, 'import_one', return_value=(0, 0, None))
    @patch.object(m, '_list_us_codes', return_value=['AAPL', 'MSFT'])
    def test_no_cursor_processes_all_and_throttles_each(self, mock_list, mock_import, mock_getproc,
                                                        mock_getsync, mock_setlsc, mock_setproc, mock_sleep):
        """无游标：处理全部标的，每个处理后调用一次限流，无成功则回写游标但不清 last_sync_date。"""
        stats = m.run_incremental(_make_src(), Mock(), dry_run=False)
        self.assertEqual(mock_import.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 2)
        # 无成功写入 → 不回写 last_sync_date
        mock_setlsc.assert_not_called()
        # 游标每只回写 + 整批清空
        calls = [c.args for c in mock_setproc.call_args_list]
        written = [c[2] for c in calls if len(c) == 3 and c[1] == 'us']
        self.assertEqual(written, ['AAPL', 'MSFT', None])


class TestImportCommonIsShared(unittest.TestCase):
    """确认港/美两脚本复用同一公共模块（而非各自复制）"""

    def test_hk_uses_common_module(self):
        self.assertIs(hk.rate_limit_sleep, common.rate_limit_sleep)
        self.assertIs(hk.resume_codes, common.resume_codes)
        self.assertIs(hk.set_market_last_processed_code, common.set_market_last_processed_code)


if __name__ == "__main__":
    unittest.main()