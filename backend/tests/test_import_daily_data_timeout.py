"""日线增量导入的有界重试 + 失败响铃（协作单 57.0）测试。

背景：Tushare 批量接口卡死 / 硬失败时，import_by_trade_date 原实现无重试且失败可能
静默 exit 0（假成功）。修复后：下载层硬超时 + 有界重试，并以既有的完整度口径
（0.90）判定「是否响铃」（exit 1 → runner 重试 + CRITICAL 告警）。

全部用例使用假数据源（不联网、不连库）。

2026-10-16 创建
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.datasource.tushare import TushareDataSource  # noqa: E402
from collector.etl.import_daily_data import DailyDataImporter  # noqa: E402


def _make_importer(batch_impl) -> DailyDataImporter:
    """构造一个不走 __init__（避免联网/连库）的导入器，注入假 Tushare 批量实现。"""
    imp = DailyDataImporter.__new__(DailyDataImporter)
    imp._dry_run = False
    imp.BATCH_RETRY_BACKOFF = (0.0, 0.0)  # 测试用：去掉退避等待
    src = TushareDataSource()             # 仅构造，不 connect()
    src.connected = True
    src.batch_get_daily = batch_impl
    imp.datasource_manager = SimpleNamespace(sources=[{'source': src}])
    return imp


class TestImportByTradeDateRetry:
    """import_by_trade_date 的重试与失败语义。"""

    def test_empty_is_not_failed_no_retry(self) -> None:
        """空返回（接口未发布/非交易日）→ (0, False)，且不重试。"""
        calls = {'n': 0}

        def impl(trade_date):
            calls['n'] += 1
            return pd.DataFrame()

        imp = _make_importer(impl)
        assert imp.import_by_trade_date('2026-10-15') == (0, False)
        assert calls['n'] == 1

    def test_timeout_retries_then_hard_fails(self) -> None:
        """超时可重试，重试耗尽后 → (0, True)，次数恰为 BATCH_MAX_RETRIES。"""
        calls = {'n': 0}

        def impl(trade_date):
            calls['n'] += 1
            raise TimeoutError('read timeout')

        imp = _make_importer(impl)
        assert imp.import_by_trade_date('2026-10-15') == (0, True)
        assert calls['n'] == imp.BATCH_MAX_RETRIES

    def test_non_retryable_fails_immediately(self) -> None:
        """非可重试错误（数据/参数类）只调 1 次即放弃。"""
        calls = {'n': 0}

        def impl(trade_date):
            calls['n'] += 1
            raise ValueError('bad param')

        imp = _make_importer(impl)
        assert imp.import_by_trade_date('2026-10-15') == (0, True)
        assert calls['n'] == 1

    def test_dry_run_skips_call(self) -> None:
        """dry-run 不触发任何下载。"""
        calls = {'n': 0}

        def impl(trade_date):
            calls['n'] += 1
            return pd.DataFrame()

        imp = _make_importer(impl)
        imp._dry_run = True
        assert imp.import_by_trade_date('2026-10-15') == (0, False)
        assert calls['n'] == 0


class TestIncrementalVerdict:
    """_incremental_verdict：是否响铃（exit 1）的表驱动判定。"""

    @staticmethod
    def _v(stats, attempted_trade_day, check_date, completeness):
        imp = DailyDataImporter.__new__(DailyDataImporter)
        return imp._incremental_verdict(stats, attempted_trade_day, check_date, completeness)

    def test_no_attempt_is_ok(self) -> None:
        """未尝试任何交易日（周末/节假日/已完整早退）→ 不响铃。"""
        ok, _ = self._v({}, False, '2026-10-15', None)
        assert ok is True

    def test_complete_is_ok(self) -> None:
        ok, _ = self._v({}, True, '2026-10-15',
                        {'existing_count': 5215, 'total_stocks': 5215, 'completeness': 1.0})
        assert ok is True

    def test_low_completeness_rings(self) -> None:
        """入库 26/5209 = 0.5% → 响铃。"""
        ok, reason = self._v({}, True, '2026-10-15',
                             {'existing_count': 26, 'total_stocks': 5209, 'completeness': 0.005})
        assert ok is False
        assert '完整度' in reason

    def test_zero_rows_rings(self) -> None:
        ok, _ = self._v({}, True, '2026-10-15',
                        {'existing_count': 0, 'total_stocks': 5209, 'completeness': 0.0})
        assert ok is False

    def test_no_baseline_not_blocking(self) -> None:
        """完整度基线不可用（查询失败）且无批量硬失败 → 不阻断（与阶段3门禁口径一致）。"""
        ok, _ = self._v({}, True, '2026-10-15',
                        {'existing_count': 0, 'total_stocks': 0, 'completeness': 0.0})
        assert ok is True

    def test_no_baseline_with_hard_fail_rings(self) -> None:
        """完整度基线不可用但批量硬失败 → 响铃。"""
        ok, _ = self._v({'batch_failed': True}, True, '2026-10-15', None)
        assert ok is False
