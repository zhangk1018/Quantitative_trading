"""港股日线增量「交易日判定 + 断点游标窗口绑定」测试。

覆盖港股数据更新失败排查引入的两处修复：
- 缺陷1：增量窗口缺口判定改用**港股真实交易日**（数据源驱动），替代 `weekday()` 粗判。
  例：中秋节 A 股休市而港股开市，用工作日判定会漏判 9/25 这个真实交易日 → 误启用
  批量快照路径 → 静默跳过该交易日数据。
- 缺陷2：断点续传游标须与日期窗口绑定，且回写 last_sync_date 前校验窗口覆盖度，
  防止被游标跳过的标的永久缺失该窗口数据（静默缺口）。

全部用例使用假数据源/假连接，不访问网络与数据库。

2026-09-28 创建
"""
import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional, Set
from unittest.mock import patch

import pandas as pd
import pytest

# 保证 `collector.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import import_hk_daily as hk  # noqa: E402
from collector.etl import market_download_common as mdc  # noqa: E402


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
    """假数据源：可注入快照 DataFrame 与港股交易日集合（None 模拟探测失败）。

    `snapshot_calls` 统计全市场快照拉取次数（协作单 53.0：一次运行只允许拉 1 次，
    旧实现判定链会连发 3 次而触发源端限流）。
    """

    def __init__(self, snapshot: Optional[pd.DataFrame], calendar: Optional[Set[date]]):
        self._snapshot = snapshot
        self._calendar = calendar
        self.cfg = _FakeCfg()
        self.snapshot_calls = 0

    def download_hk_snapshot_all(self) -> Optional[pd.DataFrame]:
        self.snapshot_calls += 1
        return self._snapshot

    def download_hk_trade_dates(self, start: Optional[str] = None,
                                end: Optional[str] = None) -> Optional[Set[date]]:
        return self._calendar


def _snapshot_on(day: str) -> pd.DataFrame:
    """构造 index=指定交易日 的最小快照 DataFrame。"""
    return pd.DataFrame({'Close': [100.0]}, index=pd.DatetimeIndex([day]))


# 中秋节场景数据：9/25（周五）港股照常开市、9/26 周六休市、9/28（周一）开市
HK_CALENDAR = {date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28)}


class TestHkTradingDaysWindow:
    """港股交易日窗口取样（[start, end) 半开 / [start, end] 闭区间）。"""

    def test_half_open_excludes_end(self):
        """半开窗口 [9/25, 9/28) 只含 9/25，不含终点 9/28。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        assert hk._hk_trading_days_in_window(src, '2026-09-25', '2026-09-28') == {date(2026, 9, 25)}

    def test_closed_interval_includes_end(self):
        """闭区间 [9/25, 9/28] 同时含 9/25 与 9/28（覆盖度校验需含终点当天）。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        assert hk._hk_trading_days_between(src, '2026-09-25', '2026-09-28') == {
            date(2026, 9, 25), date(2026, 9, 28)
        }

    def test_weekend_only_window_is_empty(self):
        """仅含周末（9/26~9/28）时无缺口交易日 → 空集。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        assert hk._hk_trading_days_in_window(src, '2026-09-26', '2026-09-28') == set()

    def test_calendar_unavailable_returns_none(self):
        """交易日历探测失败返回 None（调用方须保守处理）。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), None)
        assert hk._hk_trading_days_in_window(src, '2026-09-26', '2026-09-28') is None


class TestSnapshotProbeAndGapDays:
    """快照探针（`_snapshot_latest_date` / `_probe_src_latest`）与窗口缺口判定。

    协作单 53.0 起，「是否走快照」不再由 `_window_is_single_day` 判定，而是：
    ① 快照源可用（否则**快速失败**）；② 窗口 [start, end) 内无港股交易日缺口。
    这两个判据分别由 `_snapshot_latest_date` / `_probe_src_latest` 与
    `_hk_trading_days_in_window` 提供。
    """

    def test_latest_date_parsed_from_snapshot(self):
        """快照索引即当日交易日，取 max 转换为 ISO 日期。"""
        assert hk._snapshot_latest_date(_snapshot_on('2026-09-28')) == '2026-09-28'

    def test_latest_date_none_when_unavailable(self):
        """快照缺失/为空 → None（调用方据此快速失败）。"""
        assert hk._snapshot_latest_date(None) is None
        assert hk._snapshot_latest_date(pd.DataFrame()) is None

    def test_no_gap_when_window_weekend_only(self):
        """窗口仅剩周末且快照已覆盖终点 → 无缺口 → 可走快照单路径。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        assert hk._hk_trading_days_in_window(src, '2026-09-26', '2026-09-28') == set()
        assert hk._probe_src_latest(src, '2026-09-28', snapshot=src._snapshot) == '2026-09-28'

    def test_gap_on_hk_trading_day(self):
        """回归用例：9/25 是港股交易日（A 股中秋休市）→ 存在缺口 → 走「缺口逐只+快照」拼接。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        assert hk._hk_trading_days_in_window(src, '2026-09-25', '2026-09-28') == {date(2026, 9, 25)}

    def test_no_gap_on_hk_only_holiday(self):
        """港股独有假日（工作日但非港股交易日）不计缺口（以真实交易日历为准，非 weekday 判据）。

        2026-10-01 香港国庆日：周四休市。窗口 [10/1, 10/2) 内无交易日 → 无缺口。
        """
        cal = {date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 2)}
        src = _FakeSrc(_snapshot_on('2026-10-02'), cal)
        assert hk._hk_trading_days_in_window(src, '2026-10-01', '2026-10-02') == set()

    def test_probe_degrades_end_when_source_lags(self):
        """数据源最新日早于今天 → 窗口终点降级为数据源最新日（避免整批空跑）。"""
        src = _FakeSrc(_snapshot_on('2026-09-25'), HK_CALENDAR)
        assert hk._probe_src_latest(src, '2026-09-28', snapshot=src._snapshot) == '2026-09-25'

    def test_probe_keeps_end_when_snapshot_unavailable(self):
        """快照探测失败 → 保守沿用窗口终点（随后由 run_incremental 快速失败）。"""
        src = _FakeSrc(None, HK_CALENDAR)
        assert hk._probe_src_latest(src, '2026-09-28') == '2026-09-28'

    def test_gap_days_none_when_calendar_unavailable(self):
        """交易日历不可用 → None（调用方须快速失败，不得误判为无缺口）。"""
        src = _FakeSrc(_snapshot_on('2026-09-28'), None)
        assert hk._hk_trading_days_in_window(src, '2026-09-26', '2026-09-28') is None


class TestWindowCoverage:
    """回写 last_sync_date 前的窗口覆盖度校验。"""

    def test_pass_when_all_days_covered(self):
        """每个交易日覆盖均 ≥90% → 允许推进进度。"""
        conn = _FakeConn([(100,), (95,), (96,)])   # 基准 100，两日分别 95/96
        assert hk._window_coverage_ok(conn, {date(2026, 9, 25), date(2026, 9, 28)}) is True

    def test_fail_when_any_day_below_threshold(self):
        """任一日低于阈值（被游标跳过）→ 不得推进进度。"""
        conn = _FakeConn([(100,), (95,), (50,)])
        assert hk._window_coverage_ok(conn, {date(2026, 9, 25), date(2026, 9, 28)}) is False

    def test_fail_when_calendar_unavailable(self):
        """日历不可用（None）→ 保守判定为不通过。"""
        conn = _FakeConn([(100,)])
        assert hk._window_coverage_ok(conn, None) is False

    def test_pass_when_no_codes_in_stock_basic(self):
        """stock_basic 无港股标的时跳过校验（不误判失败）。"""
        conn = _FakeConn([(0,)])
        assert hk._window_coverage_ok(conn, {date(2026, 9, 28)}) is True


class TestCursorWindowBinding:
    """断点续传游标的窗口绑定（market_download_common）。"""

    def test_window_key_format(self):
        """窗口标识格式为 `起始日~结束日`。"""
        assert mdc.market_window_key('2026-09-25', '2026-09-28') == '2026-09-25~2026-09-28'

    def test_cursor_ignored_on_window_mismatch(self):
        """回归用例：游标属旧窗口（9/25）而本轮窗口已变（9/26~9/28）→ 忽略游标。"""
        conn = _FakeConn([('3886.HK', '2026-09-25~2026-09-28')])
        assert mdc.get_market_last_processed_code(conn, 'hk', window='2026-09-26~2026-09-28') is None

    def test_cursor_reused_on_window_match(self):
        """窗口一致时可复用游标（保留断点续传能力）。"""
        conn = _FakeConn([('3886.HK', '2026-09-25~2026-09-28')])
        assert mdc.get_market_last_processed_code(
            conn, 'hk', window='2026-09-25~2026-09-28') == '3886.HK'

    def test_cursor_reused_without_window_arg(self):
        """未传 window 时保持旧行为（不做窗口校验，兼容 import_us_daily 现状）。"""
        conn = _FakeConn([('AAPL', '2026-09-25~2026-09-28')])
        assert mdc.get_market_last_processed_code(conn, 'us') == 'AAPL'

    def test_no_cursor_returns_none(self):
        """无游标记录时返回 None。"""
        conn = _FakeConn([(None, None)])
        assert mdc.get_market_last_processed_code(conn, 'hk', window='2026-09-26~2026-09-28') is None

    def test_clear_cursor_also_clears_window(self):
        """整批跑完清空游标时，窗口一并清空。"""
        conn = _FakeConn()
        mdc.set_market_last_processed_code(conn, 'hk', None, window='2026-09-25~2026-09-28')
        _, params = conn.cur.executed[-1]
        assert params == (None, None, 'hk')
        assert conn.commits == 1

    def test_set_cursor_persists_window(self):
        """写游标时窗口随游标一并落库。"""
        conn = _FakeConn()
        mdc.set_market_last_processed_code(conn, 'hk', '0700.HK', window='2026-09-25~2026-09-28')
        _, params = conn.cur.executed[-1]
        assert params == ('0700.HK', '2026-09-25~2026-09-28', 'hk')


class TestIncrementalWindowIntegration:
    """增量主流程（逐只路径，`--limit` 强制）：窗口不一致的旧游标不得跳过标的。"""

    @staticmethod
    def _collector(processed: List[str]):
        def _fake_import_one(_src, _conn, code, start=None, end=None, dry_run=False):
            processed.append(code)
            return 1, 0, '2026-09-28'
        return _fake_import_one

    def test_stale_cursor_does_not_skip_codes(self):
        """回归用例：9/25 遗留游标 3886.HK 不得在 9/28 窗口跳过前段标的。

        9/25 那轮窗口为 `2026-09-25~2026-09-25`，本轮（9/28，last_sync 仍为 9/24）窗口为
        `2026-09-25~2026-09-28`，两者不一致 → 游标作废，全部标的重新处理。
        """
        conn = _FakeConn([('2026-09-24',), ('3886.HK', '2026-09-25~2026-09-25')])
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        processed: List[str] = []

        with patch.object(hk, 'import_one', side_effect=self._collector(processed)), \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK', '0002.HK', '0700.HK']), \
                patch.object(hk, '_window_coverage_ok', return_value=True):
            hk.run_incremental(src, conn, limit=3)   # --limit 强制逐只路径

        assert processed == ['0001.HK', '0002.HK', '0700.HK']

    def test_null_stored_window_cursor_ignored(self):
        """游标窗口为 NULL（迁移前遗留/未绑定）→ 视为不一致，游标作废。"""
        conn = _FakeConn([('2026-09-24',), ('3886.HK', None)])
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        processed: List[str] = []

        with patch.object(hk, 'import_one', side_effect=self._collector(processed)), \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK', '0700.HK']), \
                patch.object(hk, '_window_coverage_ok', return_value=True):
            hk.run_incremental(src, conn, limit=2)

        assert processed == ['0001.HK', '0700.HK']

    def test_no_writeback_when_coverage_incomplete(self):
        """窗口覆盖度不达标时不得推进 last_sync_date（并已清空游标）。"""
        conn = _FakeConn([('2026-09-24',), ('3886.HK', '2026-09-25~2026-09-25')])
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)

        with patch.object(hk, 'import_one', return_value=(1, 0, '2026-09-28')), \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK']), \
                patch.object(hk, '_window_coverage_ok', return_value=False), \
                patch.object(hk, 'set_last_sync_date') as mock_write:
            stats = hk.run_incremental(src, conn, limit=1)

        mock_write.assert_not_called()
        assert stats['quotes'] == 1
        # 最后一次游标写入应为清空（None, None）
        _, params = conn.cur.executed[-1]
        assert params == (None, None, 'hk')


class TestIncrementalSnapshotPath:
    """协作单 53.0：快照单次拉取复用 + 缺口拼接 + 快失败（替代静默回退逐只）。"""

    _BATCH_OK = {'snap_ok': True, 'direct': 5, 'fallback': 1, 'failed': 0}

    def test_snapshot_fetched_once_and_no_per_stock(self):
        """无缺口窗口：仅走快照、不再逐只；整轮快照源**只拉 1 次**（旧实现连发 3 次）。"""
        conn = _FakeConn([('2026-09-25',)])          # start=9/26，窗口 [9/26, 9/28) 仅周末
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)

        with patch.object(hk, 'import_one') as mock_one, \
                patch.object(hk, '_list_hk_codes', return_value=['0700.HK']), \
                patch.object(hk, 'import_hk_snapshot_daily', return_value=dict(self._BATCH_OK)) as mock_batch, \
                patch.object(hk, '_window_coverage_ok', return_value=True) as mock_cov, \
                patch.object(hk, 'set_last_sync_date') as mock_set:
            stats = hk.run_incremental(src, conn)

        mock_one.assert_not_called()
        assert src.snapshot_calls == 1
        mock_batch.assert_called_once()                       # 复用同一份快照，不再自行拉取
        assert mock_cov.call_args.args[1] == {date(2026, 9, 28)}
        mock_set.assert_called_once_with(conn, '2026-09-28')
        assert stats['quotes'] == 5 and stats['success'] == 6
        assert stats['max_trade_date'] == '2026-09-28'

    def test_gap_window_splices_per_stock_then_snapshot(self):
        """跨日窗口：缺口日走逐只（end_excl=窗口终点）→ 最新日走快照 → 覆盖度按两日校验。"""
        conn = _FakeConn([('2026-09-24',)])          # start=9/25 → 缺口 {9/25}
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)
        calls: List[tuple] = []

        def _fake_import_one(_src, _conn, code, start=None, end=None, dry_run=False):
            calls.append((code, start, end))
            return 1, 0, '2026-09-25'

        with patch.object(hk, 'import_one', side_effect=_fake_import_one), \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK']), \
                patch.object(hk, 'import_hk_snapshot_daily',
                             return_value={'snap_ok': True, 'direct': 3, 'fallback': 0, 'failed': 0}) as mock_batch, \
                patch.object(hk, '_window_coverage_ok', return_value=True) as mock_cov, \
                patch.object(hk, 'set_last_sync_date'), \
                patch.object(hk, 'set_market_last_processed_code'):
            stats = hk.run_incremental(src, conn)

        # 缺口日：区间为 [start, end)（半开，不含最新交易日 end）
        assert calls == [('0001.HK', '2026-09-25', '2026-09-28')]
        mock_batch.assert_called_once()
        assert src.snapshot_calls == 1
        assert mock_cov.call_args.args[1] == {date(2026, 9, 25), date(2026, 9, 28)}
        assert stats['quotes'] == 4                # 逐只 1 + 快照直写 3
        assert stats['max_trade_date'] == '2026-09-28'

    def test_fail_fast_when_snapshot_unavailable(self):
        """快照源不可用 → 立即非零失败，**不再静默回退逐只**空转数小时。"""
        conn = _FakeConn([('2026-09-25',)])
        src = _FakeSrc(None, HK_CALENDAR)

        with patch.object(hk, 'import_one') as mock_one, \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK']):
            with pytest.raises(SystemExit) as exc:
                hk.run_incremental(src, conn)

        assert exc.value.code != 0
        mock_one.assert_not_called()

    def test_fail_fast_when_calendar_unavailable(self):
        """交易日历不可用 → 无法判定缺口 → 非零失败（防误判无缺口而静默跳过交易日）。"""
        conn = _FakeConn([('2026-09-25',)])
        src = _FakeSrc(_snapshot_on('2026-09-28'), None)

        with patch.object(hk, 'import_one') as mock_one, \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK']):
            with pytest.raises(SystemExit) as exc:
                hk.run_incremental(src, conn)

        assert exc.value.code != 0
        mock_one.assert_not_called()

    def test_fail_fast_when_snap_ok_false(self):
        """快照接口返回空/失败（snap_ok=False）→ 非零失败（旧行为：回退逐只）。"""
        conn = _FakeConn([('2026-09-25',)])
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)

        with patch.object(hk, 'import_one') as mock_one, \
                patch.object(hk, '_list_hk_codes', return_value=['0001.HK']), \
                patch.object(hk, 'import_hk_snapshot_daily',
                             return_value={'snap_ok': False, 'direct': 0, 'fallback': 0, 'failed': 0}):
            with pytest.raises(SystemExit) as exc:
                hk.run_incremental(src, conn)

        assert exc.value.code != 0
        mock_one.assert_not_called()

    def test_fail_fast_when_zero_rows(self):
        """快照直写与内部回退均为 0 → 最新交易日零入库 → 非零失败（防「假成功」）。"""
        conn = _FakeConn([('2026-09-25',)])
        src = _FakeSrc(_snapshot_on('2026-09-28'), HK_CALENDAR)

        with patch.object(hk, '_list_hk_codes', return_value=['0001.HK']), \
                patch.object(hk, 'import_hk_snapshot_daily',
                             return_value={'snap_ok': True, 'direct': 0, 'fallback': 0, 'failed': 0}), \
                patch.object(hk, 'set_last_sync_date') as mock_set:
            with pytest.raises(SystemExit) as exc:
                hk.run_incremental(src, conn)

        assert exc.value.code != 0
        mock_set.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])