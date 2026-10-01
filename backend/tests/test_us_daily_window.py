"""美股日线增量「交易日判定 + 断点游标窗口绑定」测试。

与港股同源的两处修复（见 test_hk_daily_window.py），在美股侧一并落实：
- 缺陷1：窗口交易日取样改用**美股真实交易日**（数据源驱动，纳斯达克指数），
  不得用 `weekday()` 推断——美股假日（感恩节/独立日/马丁·路德·金日等）与 A 股、
  港股均不同。
- 缺陷2：断点续传游标须与日期窗口绑定，且回写 last_sync_date 前校验窗口覆盖度，
  防止被游标跳过的标的永久缺失该窗口数据（静默缺口）。

全部用例使用假数据源/假连接，不访问网络与数据库。

2026-09-29 创建
"""
import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional, Set
from unittest.mock import patch

import pytest

# 保证 `collector.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import import_us_daily as us  # noqa: E402


# ==================== 假对象 ====================
class _FakeCursor:
    """假游标：execute 只记录语句，fetchone 按序吐出预置行。"""

    def __init__(self, rows: List[Any]):
        self._rows = list(rows)
        self.executed: List[Any] = []

    def __enter__(self) -> '_FakeCursor':
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None


class _FakeConn:
    """假连接：cursor() 返回同一假游标，记录 commit/rollback 次数。"""

    def __init__(self, rows: Optional[List[Any]] = None):
        self.cur = _FakeCursor(rows or [])
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _FakeCursor:
        return self.cur

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeCfg:
    """假市场配置：无批间休眠（测试不产生真实等待）。"""

    batch_interval_min_sleep = 0.0
    batch_interval_max_sleep = 0.0
    incremental_lookback_days = 7


class _FakeSrc:
    """假数据源：可注入美股交易日集合（None 模拟探测失败）。"""

    def __init__(self, calendar: Optional[Set[date]]):
        self._calendar = calendar
        self.cfg = _FakeCfg()

    def download_us_trade_dates(self, start: Optional[str] = None,
                                end: Optional[str] = None) -> Optional[Set[date]]:
        return self._calendar


# 美股交易日场景：9/24（周四）、9/25（周五）开市，9/26/27 周末休市，9/28（周一）开市
US_CALENDAR = {date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28)}


class TestUsTradingDaysWindow:
    """美股交易日窗口取样（[start, end] 闭区间）。"""

    def test_closed_interval_includes_end(self):
        """闭区间 [9/25, 9/28] 同时含 9/25 与 9/28。"""
        src = _FakeSrc(US_CALENDAR)
        assert us._us_trading_days_between(src, '2026-09-25', '2026-09-28') == {
            date(2026, 9, 25), date(2026, 9, 28)
        }

    def test_weekend_only_window_is_empty(self):
        """仅含周末（9/26~9/28 起点处）时无待校验交易日 → 空集。"""
        src = _FakeSrc(US_CALENDAR)
        assert us._us_trading_days_between(src, '2026-09-26', '2026-09-27') == set()

    def test_us_only_holiday_not_counted(self):
        """美股独有假日（工作日但非美股交易日）不计入应校验交易日。

        以 2026-11-26 感恩节（周四）为例：休市。窗口 [11/26, 11/27] 内只有
        11/27 是交易日 → 只校验 11/27，避免把假日误判为缺口。
        """
        cal = {date(2026, 11, 25), date(2026, 11, 27)}
        src = _FakeSrc(cal)
        assert us._us_trading_days_between(src, '2026-11-26', '2026-11-27') == {date(2026, 11, 27)}

    def test_calendar_unavailable_returns_none(self):
        """交易日历探测失败返回 None（调用方须保守处理）。"""
        src = _FakeSrc(None)
        assert us._us_trading_days_between(src, '2026-09-25', '2026-09-28') is None


class TestWindowCoverage:
    """回写 last_sync_date 前的窗口覆盖度校验。"""

    def test_pass_when_all_days_covered(self):
        """每个交易日覆盖均 ≥90% → 允许推进进度。"""
        conn = _FakeConn([(200,), (190,), (196,)])   # 基准 200，两日分别 190/196
        assert us._window_coverage_ok(conn, {date(2026, 9, 25), date(2026, 9, 28)}) is True

    def test_fail_when_any_day_below_threshold(self):
        """任一日低于阈值（被游标跳过）→ 不得推进进度。"""
        conn = _FakeConn([(200,), (190,), (100,)])
        assert us._window_coverage_ok(conn, {date(2026, 9, 25), date(2026, 9, 28)}) is False

    def test_fail_when_calendar_unavailable(self):
        """日历不可用（None）→ 保守判定为不通过。"""
        conn = _FakeConn([(200,)])
        assert us._window_coverage_ok(conn, None) is False

    def test_pass_when_no_codes_in_stock_basic(self):
        """stock_basic 无美股标的时跳过校验（不误判失败）。"""
        conn = _FakeConn([(0,)])
        assert us._window_coverage_ok(conn, {date(2026, 9, 28)}) is True


class TestIncrementalWindowIntegration:
    """增量主流程：窗口不一致的旧游标不得跳过标的；覆盖度不足不得回写进度。"""

    def test_stale_cursor_does_not_skip_codes(self):
        """回归用例：上一轮窗口遗留的游标不得在本轮（窗口已变）跳过前段标的。"""
        conn = _FakeConn([('2026-09-24',), ('AAPL', '2026-09-24~2026-09-25')])
        src = _FakeSrc(US_CALENDAR)
        processed: List[str] = []

        def _fake_import_one(_src, _conn, code, start=None, end=None, dry_run=False):
            processed.append(code)
            return 1, 0, '2026-09-28'

        with patch.object(us, 'import_one', side_effect=_fake_import_one), \
                patch.object(us, '_list_us_codes', return_value=['AAPL', 'MSFT', 'NVDA']), \
                patch.object(us, '_probe_src_latest', return_value='2026-09-28'), \
                patch.object(us, '_window_coverage_ok', return_value=True):
            us.run_incremental(src, conn)

        assert processed == ['AAPL', 'MSFT', 'NVDA']

    def test_null_stored_window_cursor_ignored(self):
        """游标窗口为 NULL（迁移前遗留/未绑定）→ 视为不一致，游标作废。"""
        conn = _FakeConn([('2026-09-24',), ('AAPL', None)])
        src = _FakeSrc(US_CALENDAR)
        processed: List[str] = []

        def _fake_import_one(_src, _conn, code, start=None, end=None, dry_run=False):
            processed.append(code)
            return 1, 0, '2026-09-28'

        with patch.object(us, 'import_one', side_effect=_fake_import_one), \
                patch.object(us, '_list_us_codes', return_value=['AAPL', 'MSFT']), \
                patch.object(us, '_probe_src_latest', return_value='2026-09-28'), \
                patch.object(us, '_window_coverage_ok', return_value=True):
            us.run_incremental(src, conn)

        assert processed == ['AAPL', 'MSFT']

    def test_matching_window_cursor_still_resumes(self):
        """窗口一致时仍可断点续传（不因窗口绑定丢失续传能力）。"""
        conn = _FakeConn([('2026-09-24',), ('AAPL', '2026-09-25~2026-09-28')])
        src = _FakeSrc(US_CALENDAR)
        processed: List[str] = []

        def _fake_import_one(_src, _conn, code, start=None, end=None, dry_run=False):
            processed.append(code)
            return 1, 0, '2026-09-28'

        with patch.object(us, 'import_one', side_effect=_fake_import_one), \
                patch.object(us, '_list_us_codes', return_value=['AAPL', 'MSFT', 'NVDA']), \
                patch.object(us, '_probe_src_latest', return_value='2026-09-28'), \
                patch.object(us, '_window_coverage_ok', return_value=True):
            us.run_incremental(src, conn)

        assert processed == ['MSFT', 'NVDA']

    def test_no_writeback_when_coverage_incomplete(self):
        """窗口覆盖度不达标时不得推进 last_sync_date（并已清空游标）。"""
        conn = _FakeConn([('2026-09-24',), ('AAPL', '2026-09-24~2026-09-25')])
        src = _FakeSrc(US_CALENDAR)

        with patch.object(us, 'import_one', return_value=(1, 0, '2026-09-28')), \
                patch.object(us, '_list_us_codes', return_value=['AAPL']), \
                patch.object(us, '_probe_src_latest', return_value='2026-09-28'), \
                patch.object(us, '_window_coverage_ok', return_value=False), \
                patch.object(us, 'set_last_sync_date') as mock_write:
            stats = us.run_incremental(src, conn)

        mock_write.assert_not_called()
        assert stats['quotes'] == 1
        # 最后一次游标写入应为清空（None, None）
        _, params = conn.cur.executed[-1]
        assert params == (None, None, 'us')

    def test_writeback_when_coverage_ok(self):
        """覆盖度达标时按实际覆盖的最后交易日回写进度。"""
        conn = _FakeConn([('2026-09-24',), (None, None)])
        src = _FakeSrc(US_CALENDAR)

        with patch.object(us, 'import_one', return_value=(1, 0, '2026-09-28')), \
                patch.object(us, '_list_us_codes', return_value=['AAPL']), \
                patch.object(us, '_probe_src_latest', return_value='2026-09-28'), \
                patch.object(us, '_window_coverage_ok', return_value=True), \
                patch.object(us, 'set_last_sync_date') as mock_write:
            us.run_incremental(src, conn)

        mock_write.assert_called_once_with(conn, '2026-09-28')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])