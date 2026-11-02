# -*- coding: utf-8 -*-
"""港股快照代码级对账与补拉测试（P1，2026-11-02）。

背景：2026-10-30 批量快照漏掉 16 只（信和置业 0083、新奥能源 2688、越秀交通 1052 等），
快照内回退拉取当时为空且不重试，日期级覆盖率≥90% 门禁也看不到代码级缺口。

修复：快照落库后，以「近 N 日有过日线」的代码集合为基准，找当日缺失代码，
用 `resolve_one` 做有界补拉（默认 2 轮），残留代码计入 `fail` 并输出清单。

全部用例使用假数据源/假连接，不访问网络与数据库。
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import import_hk_daily as hk  # noqa: E402

SNAP = date(2026, 11, 2)


# ==================== 假对象 ====================

class _CodesCursor:
    """根据 SQL 参数返回指定日期区间内的代码集合。"""

    def __init__(self, conn: '_CodesConn'):
        self.conn = conn
        self._rows: List[tuple] = []
        self.executed: List[Any] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str, params: Any = None):
        self.executed.append((sql, params))
        start, end_excl = params[1], params[2]
        codes: Set[str] = set()
        for day, day_codes in self.conn.codes_by_day.items():
            if start <= day < end_excl:
                codes |= day_codes
        self._rows = [(c,) for c in sorted(codes)]

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return None


class _CodesConn:
    def __init__(self, codes_by_day: Dict[date, Set[str]]):
        self.codes_by_day = codes_by_day

    def cursor(self):
        return _CodesCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


class _FakeCfg:
    batch_retry_min_sleep = 0.0
    batch_retry_max_sleep = 0.0
    incremental_lookback_days = 7


class _FakeSrc:
    def __init__(self):
        self.cfg = _FakeCfg()


def _resolver(responses: Dict[str, List[Optional[str]]]):
    """按代码返回预置的 max_date 序列（逐次弹出），并统计调用次数。"""
    calls: Dict[str, List[str]] = {}

    def _fn(_conn, _src, code, dry_run=False):
        calls.setdefault(code, []).append(code)
        seq = responses.get(code, [SNAP.isoformat()])
        item = seq[min(len(calls[code]) - 1, len(seq) - 1)]
        if isinstance(item, BaseException):
            raise item
        return 1, 0, item

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


# ==================== 对账逻辑 ====================

class TestReconcileSnapshotGaps:

    def test_noop_when_no_recent_codes(self):
        """基准窗口内无任何代码（首次运行）→ 不补拉。"""
        conn = _CodesConn({})
        resolver = _resolver({})
        with patch.object(hk, 'resolve_one', side_effect=resolver):
            recon = hk._reconcile_snapshot_gaps(conn, _FakeSrc(), SNAP)
        assert recon['expected'] == 0
        assert recon['residual'] == []
        assert resolver.calls == {}

    def test_recovers_missing_and_reports_residual(self):
        """B 可在补拉中恢复、C 始终无当日数据 → recovered=[B], residual=[C]。"""
        recent = {SNAP - timedelta(days=d) for d in range(1, 8)}
        codes_by_day = {d: {'A', 'B', 'C'} for d in recent}
        codes_by_day[SNAP] = {'A'}
        conn = _CodesConn(codes_by_day)
        resolver = _resolver({'B': [SNAP.isoformat()], 'C': [None]})

        with patch.object(hk, 'resolve_one', side_effect=resolver):
            recon = hk._reconcile_snapshot_gaps(conn, _FakeSrc(), SNAP, retry_rounds=2)

        assert recon['expected'] == 3
        assert recon['recovered'] == ['B']
        assert recon['residual'] == ['C']
        assert recon['rounds'] == 2
        # C 每轮重试一次（共 2 次），B 仅首轮一次
        assert len(resolver.calls['C']) == 2
        assert len(resolver.calls['B']) == 1

    def test_stops_early_when_all_recovered(self):
        """首轮全部恢复 → 不再进入第二轮。"""
        codes_by_day = {SNAP - timedelta(days=1): {'A', 'B'}, SNAP: {'A'}}
        resolver = _resolver({'B': [SNAP.isoformat()]})
        with patch.object(hk, 'resolve_one', side_effect=resolver), \
                patch.object(hk, 'retry_sleep') as mock_sleep:
            recon = hk._reconcile_snapshot_gaps(_CodesConn(codes_by_day), _FakeSrc(), SNAP, retry_rounds=2)

        assert recon['residual'] == []
        assert recon['rounds'] == 1
        assert mock_sleep.call_count == 1       # 每轮补拉前退避一次
        assert len(resolver.calls['B']) == 1

    def test_retry_rounds_are_bounded(self):
        """始终拉不到时，调用次数 = 缺失数 × 轮数（不会无限重试）。"""
        codes_by_day = {SNAP - timedelta(days=1): {'A', 'B', 'C'}, SNAP: set()}
        calls: Dict[str, List[str]] = {}

        def _fn(_conn, _src, code, dry_run=False):
            calls.setdefault(code, []).append(code)
            return 1, 0, '2026-10-30'   # 最新数据仍停留在前一日

        with patch.object(hk, 'resolve_one', side_effect=_fn), \
                patch.object(hk, 'retry_sleep'):
            recon = hk._reconcile_snapshot_gaps(_CodesConn(codes_by_day), _FakeSrc(), SNAP, retry_rounds=2)

        assert recon['residual'] == ['A', 'B', 'C']
        assert recon['rounds'] == 2
        assert {c: len(v) for c, v in calls.items()} == {'A': 2, 'B': 2, 'C': 2}

    def test_exception_is_residual_not_crash(self):
        """单只补拉异常被吸收为残留，不中断其它标的。"""
        codes_by_day = {SNAP - timedelta(days=1): {'A', 'B'}, SNAP: set()}
        resolver = _resolver({'A': [RuntimeError('boom')], 'B': [SNAP.isoformat()]})
        with patch.object(hk, 'resolve_one', side_effect=resolver), \
                patch.object(hk, 'retry_sleep'):
            recon = hk._reconcile_snapshot_gaps(_CodesConn(codes_by_day), _FakeSrc(), SNAP, retry_rounds=1)

        assert recon['residual'] == ['A']
        assert recon['recovered'] == ['B']


# ==================== 增量主流程接线 ====================

class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._cur = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._cur = self._rows.pop(0) if self._rows else None

    def fetchone(self):
        return self._cur

    def fetchall(self):
        return self._cur or []

    def close(self):
        pass


class _Conn:
    def __init__(self, rows):
        self.cur = _Cursor(rows)

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def rollback(self):
        pass


def _snapshot() -> pd.DataFrame:
    return pd.DataFrame({'Close': [100.0]}, index=pd.DatetimeIndex(['2026-11-02']))


class _Src:
    def __init__(self):
        self.cfg = _FakeCfg()

    def download_hk_snapshot_all(self):
        return _snapshot()

    def download_hk_trade_dates(self, start=None, end=None):
        return {SNAP}


class TestRunIncrementalReconcileWiring:

    def test_residual_counts_as_fail_and_recovered_counts_as_quotes(self):
        conn = _Conn([('2026-10-30',)])
        batch = {'snap_ok': True, 'direct': 2776, 'fallback': 33, 'failed': 0}
        recon = {'expected': 2800, 'recovered': ['B'], 'residual': ['C'], 'rounds': 2}
        with patch.object(hk, 'import_hk_snapshot_daily', return_value=batch), \
                patch.object(hk, '_list_hk_codes', return_value=['A.HK']), \
                patch.object(hk, '_reconcile_snapshot_gaps', return_value=recon), \
                patch.object(hk, '_window_coverage_ok', return_value=True), \
                patch.object(hk, 'set_last_sync_date'), \
                patch.object(hk, 'set_market_last_processed_code'):
            stats = hk.run_incremental(_Src(), conn)

        assert stats['quotes'] == 2776 + 1          # 直写 + 对账恢复
        assert stats['success'] == 2776 + 33 + 1    # 覆盖 + 对账恢复
        assert stats['fail'] == 1                    # 残留 1 只
        assert stats['max_trade_date'] == '2026-11-02'

    def test_reconcile_failure_does_not_break_snapshot_import(self):
        """对账异常不影响已成功的快照落库与进度推进。"""
        conn = _Conn([('2026-10-30',)])
        batch = {'snap_ok': True, 'direct': 2776, 'fallback': 33, 'failed': 0}
        with patch.object(hk, 'import_hk_snapshot_daily', return_value=batch), \
                patch.object(hk, '_list_hk_codes', return_value=['A.HK']), \
                patch.object(hk, '_reconcile_snapshot_gaps', side_effect=RuntimeError('db down')), \
                patch.object(hk, '_window_coverage_ok', return_value=True), \
                patch.object(hk, 'set_last_sync_date') as mock_set, \
                patch.object(hk, 'set_market_last_processed_code'):
            stats = hk.run_incremental(_Src(), conn)

        mock_set.assert_called_once_with(conn, '2026-11-02')
        assert stats['quotes'] == 2776
        assert stats['fail'] == 0
