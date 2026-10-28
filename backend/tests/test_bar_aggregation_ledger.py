# -*- coding: utf-8 -*-
"""周/月K 聚合任务的 task_run_log 台账测试（协作单 61.0）。

背景：周/月K 聚合此前不写 `task_run_log`，导致调度看护（`scheduler_watchdog.py`，协作单 60.0）
无法判定其「是否已执行」→ 触发被 launchd 错过时无法自动补执行。
本文件覆盖：
- 任务名口径 `{market}:{周K|月K}`（与看护槽位声明一致）；
- `log_ledger_start/end` 的 SQL 与参数（running → success/failed，data_date 取值）；
- 台账写失败**不得阻断**聚合本身；
- `main()` 每「市场 × 周期」各写一行台账（多市场单进程、失败分支、cn 跳过分支）；
- 与 `scheduler_watchdog.SLOTS` 的任务名对齐。

全部用例使用假连接，不访问网络与数据库。
"""
import sys
from argparse import Namespace
from datetime import date
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import compute_bar_aggregation as mod  # noqa: E402


# ===================== 假连接 =====================

class _FakeCursor:
    def __init__(self, one_rows: Optional[Sequence[Any]] = None,
                 all_rows: Optional[Sequence[Any]] = None):
        self._one = list(one_rows or [])
        self._all = list(all_rows or [])
        self.executed: List[Tuple[str, Any]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        self.rowcount = 1

    def fetchone(self) -> Any:
        return self._one.pop(0) if self._one else None

    def fetchall(self) -> List[Any]:
        return self._all.pop(0) if self._all else []

    def close(self) -> None:
        pass

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False


class _FakeConn:
    """最小连接替身：记录 commit/rollback/close 与全部执行语句。"""

    def __init__(self, one_rows: Optional[Sequence[Any]] = None):
        self.cur = _FakeCursor(one_rows=one_rows)
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0
        self.autocommit = True

    def cursor(self) -> _FakeCursor:
        return self.cur

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


class _LedgerConnPool:
    """get_db_conn() 替身：每次调用返回一个新连接，并记录其执行语句。"""

    def __init__(self, one_rows: Optional[Sequence[Any]] = None, fail_on: int = -1):
        self.conns: List[_FakeConn] = []
        self._one_rows = one_rows
        self._fail_on = fail_on
        self.calls = 0

    def __call__(self) -> _FakeConn:
        self.calls += 1
        if self._fail_on == self.calls:
            raise RuntimeError('connect refused')
        conn = _FakeConn(one_rows=self._one_rows)
        self.conns.append(conn)
        return conn

    @property
    def sqls(self) -> List[str]:
        return [s for c in self.conns for s, _ in c.cur.executed]

    @property
    def params(self) -> List[Any]:
        return [p for c in self.conns for _, p in c.cur.executed]


def _args(**kw) -> Namespace:
    base = dict(cycle='1w', market='cn', date=None, force=False, lookback_periods=None,
                rebuild=False, rebuild_from=None, rebuild_to=None)
    base.update(kw)
    return Namespace(**base)


# ===================== 任务名口径 =====================

class TestTaskNaming:

    @pytest.mark.parametrize('market,cycle,expected', [
        ('cn', '1w', 'cn:周K'),
        ('cn', '1m', 'cn:月K'),
        ('hk', '1w', 'hk:周K'),
        ('us', '1w', 'us:周K'),
        ('hk', '1m', 'hk:月K'),
        ('us', '1m', 'us:月K'),
    ])
    def test_market_task_name(self, market, cycle, expected):
        assert mod.market_task_name(market, cycle) == expected

    def test_ledger_stage_is_within_constraint(self):
        """stage 必须落在 task_run_log 的 CHECK (0~11) 内，且取实测空缺的 10（0~9 已被占用）。"""
        assert 0 <= mod.LEDGER_STAGE <= 11
        assert mod.LEDGER_STAGE == 10

    def test_names_align_with_watchdog_slots(self):
        """与调度看护 SLOTS 声明的任务名逐一对齐（两侧各写一半即失败）。"""
        import importlib.util
        wd_path = BACKEND_DIR / 'cron' / 'scheduler_watchdog.py'
        spec = importlib.util.spec_from_file_location('scheduler_watchdog', wd_path)
        wd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wd)

        assert set(wd.expected_task_names(wd.SLOT_BY_KEY['cn-weekly'])) == {mod.market_task_name('cn', '1w')}
        assert set(wd.expected_task_names(wd.SLOT_BY_KEY['cn-monthly'])) == {mod.market_task_name('cn', '1m')}
        assert set(wd.expected_task_names(wd.SLOT_BY_KEY['hk-weekly'])) == {mod.market_task_name('hk', '1w')}
        assert set(wd.expected_task_names(wd.SLOT_BY_KEY['us-weekly'])) == {mod.market_task_name('us', '1w')}
        assert set(wd.expected_task_names(wd.SLOT_BY_KEY['overseas-monthly'])) == {
            mod.market_task_name('hk', '1m'), mod.market_task_name('us', '1m')}


# ===================== 台账写入/回填 =====================

class TestLedgerHelpers:

    def test_start_inserts_running_and_commits(self, monkeypatch):
        pool = _LedgerConnPool(one_rows=[(123,)])
        monkeypatch.setattr(mod, 'get_db_conn', pool)

        log_id = mod.log_ledger_start('cn:周K', date(2026, 10, 30), detail={'market': 'cn'})

        assert log_id == 123
        sql, params = pool.conns[0].cur.executed[0]
        assert 'INSERT INTO task_run_log' in sql
        assert "'running'" in sql
        assert params[0] == 'cn:周K' and params[1] == mod.LEDGER_STAGE
        assert params[2] == date(2026, 10, 30)
        assert '{"market": "cn"}' == params[3]
        assert pool.conns[0].commits == 1
        assert pool.conns[0].closed == 1        # 独立短连接必须关闭

    def test_start_without_detail_passes_null(self, monkeypatch):
        pool = _LedgerConnPool(one_rows=[(1,)])
        monkeypatch.setattr(mod, 'get_db_conn', pool)
        mod.log_ledger_start('hk:月K', date(2026, 10, 27))
        assert pool.params[0][3] is None

    def test_start_failure_returns_negative_and_never_raises(self, monkeypatch):
        pool = _LedgerConnPool(one_rows=[(1,)], fail_on=1)
        monkeypatch.setattr(mod, 'get_db_conn', pool)
        assert mod.log_ledger_start('us:周K', date(2026, 10, 27)) == -1

    def test_start_failure_when_insert_raises(self, monkeypatch):
        class _Boom(_FakeConn):
            def cursor(self):
                raise RuntimeError('permission denied')

        monkeypatch.setattr(mod, 'get_db_conn', lambda: _Boom())
        assert mod.log_ledger_start('cn:月K', date(2026, 10, 27)) == -1

    def test_end_marks_success_with_rows_and_data_date(self, monkeypatch):
        pool = _LedgerConnPool()
        monkeypatch.setattr(mod, 'get_db_conn', pool)

        mod.log_ledger_end(7, True, rows=2807, data_date=date(2026, 10, 2),
                           detail={'buckets_written': 1})
        sql, params = pool.conns[0].cur.executed[0]
        assert 'UPDATE task_run_log' in sql
        assert params[0] == 'success' and params[1] == 0
        assert params[3] == 2807
        assert params[4] == date(2026, 10, 2)
        assert 'buckets_written' in params[5]
        assert params[6] == 7

    def test_end_marks_failed_with_error(self, monkeypatch):
        pool = _LedgerConnPool()
        monkeypatch.setattr(mod, 'get_db_conn', pool)

        mod.log_ledger_end(7, False, rows=0, error='RuntimeError: boom',
                           data_date=date(2026, 10, 27))
        _, params = pool.conns[0].cur.executed[0]
        assert params[0] == 'failed' and params[1] == 1
        assert params[2] == 'RuntimeError: boom'

    def test_end_skips_when_log_id_negative(self, monkeypatch):
        pool = _LedgerConnPool()
        monkeypatch.setattr(mod, 'get_db_conn', pool)
        mod.log_ledger_end(-1, True, rows=1)
        assert pool.calls == 0

    def test_end_failure_never_raises(self, monkeypatch):
        monkeypatch.setattr(mod, 'get_db_conn', lambda: (_ for _ in ()).throw(RuntimeError('x')))
        mod.log_ledger_end(7, True, rows=1)      # 不应抛出


# ===================== main() 每市场一行台账 =====================

class TestMainLedger:

    @pytest.fixture
    def patched(self, monkeypatch):
        """替换聚合主体与日志清理，暴露台账调用记录。"""
        calls = {'start': [], 'end': []}
        monkeypatch.setattr(mod, 'get_db_conn', lambda: _FakeConn())
        monkeypatch.setattr(mod, 'log_ledger_start',
                            lambda name, dd, detail=None: calls['start'].append((name, dd, detail)) or 1)
        monkeypatch.setattr(mod, 'log_ledger_end',
                            lambda _id, ok, **kw: calls['end'].append((ok, kw)))
        monkeypatch.setattr(mod, 'cleanup_expired_logs', lambda *a, **k: None)
        return calls

    def test_cn_single_run_writes_one_row(self, patched, monkeypatch, capsys):
        monkeypatch.setattr(mod, 'run_cn', lambda c, cy, a: {
            'rows_affected': 5213, 'date': '2026-10-30'})
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w'])
        mod.main()                                   # 成功路径正常返回（不 sys.exit）
        assert [c[0] for c in patched['start']] == ['cn:周K']
        ok, kw = patched['end'][0]
        assert ok is True and kw['rows'] == 5213
        assert kw['data_date'] == date(2026, 10, 30)
        out = capsys.readouterr().out
        assert 'TASK_RESULT:' in out and '"rows_affected": 5213' in out

    def test_overseas_multi_market_writes_two_rows(self, patched, monkeypatch, capsys):
        results = {
            'hk': {'rows_affected': 2807, 'buckets_written': 1, 'buckets_skipped': 0,
                   'label': date(2026, 10, 30)},
            'us': {'rows_affected': 205, 'buckets_written': 1, 'buckets_skipped': 0,
                   'label': date(2026, 10, 30)},
        }
        monkeypatch.setattr(mod, 'run_overseas', lambda c, m, cy, a: results[m])
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w', '--market', 'hk,us'])
        mod.main()
        assert [c[0] for c in patched['start']] == ['hk:周K', 'us:周K']
        assert [kw['rows'] for _, kw in patched['end']] == [2807, 205]
        assert all(kw['data_date'] == date(2026, 10, 30) for _, kw in patched['end'])
        # 回归：results 含 date 时 TASK_RESULT 必须可序列化（default=str）
        out = capsys.readouterr().out
        assert '"rows_affected": 3012' in out and '"label": "2026-10-30"' in out

    def test_cn_noop_skip_still_recorded_success(self, patched, monkeypatch):
        """沪深「非本周最后交易日」跳过 → 仍写 success（noop 视为已执行，看护不再重试）。"""
        monkeypatch.setattr(mod, 'run_cn', lambda c, cy, a: {
            'rows_affected': 0, 'skipped_reason': '2026-10-27 不是该周最后一个交易日，跳过',
            'date': '2026-10-27'})
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w'])
        mod.main()
        ok, kw = patched['end'][0]
        assert ok is True and kw['rows'] == 0
        assert '不是该周最后一个交易日' in kw['detail']['skipped_reason']

    def test_overseas_calendar_unavailable_label_falls_back_to_run_date(self, patched, monkeypatch):
        """日历不可用（无产出、无 label）→ data_date 退回运行日，仍记 success。"""
        monkeypatch.setattr(mod, 'run_overseas', lambda c, m, cy, a: {
            'rows_affected': 0, 'buckets_written': 0, 'buckets_skipped': 4,
            'label': None, 'calendar_unavailable': True})
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1m', '--market', 'hk,us'])
        mod.main()
        assert all(kw['data_date'] == date.today() for _, kw in patched['end'])

    def test_failure_records_failed_ledger_and_exits_nonzero(self, patched, monkeypatch):
        def boom(c, cy, a):
            raise RuntimeError('聚合炸了')
        monkeypatch.setattr(mod, 'run_cn', boom)
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w'])
        with pytest.raises(SystemExit) as e:
            mod.main()
        assert e.value.code == 1
        ok, kw = patched['end'][0]
        assert ok is False and 'RuntimeError' in kw['error']

    def test_earlier_market_success_is_preserved_when_later_fails(self, patched, monkeypatch):
        """hk 成功、us 失败：hk 台账保持 success，us 记 failed（互不牵连）。"""
        def run_overseas(c, m, cy, a):
            if m == 'us':
                raise RuntimeError('us boom')
            return {'rows_affected': 2807, 'buckets_written': 1, 'buckets_skipped': 0,
                    'label': date(2026, 10, 30)}
        monkeypatch.setattr(mod, 'run_overseas', run_overseas)
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w', '--market', 'hk,us'])
        with pytest.raises(SystemExit) as e:
            mod.main()
        assert e.value.code == 1
        assert [ok for ok, _ in patched['end']] == [True, False]

    def test_system_exit_from_cn_still_records_failed(self, patched, monkeypatch):
        """run_cn 内部 sys.exit(1)（日线表为空）也要留下 failed 台账，不静默消失。"""
        def boom(c, cy, a):
            sys.exit(1)
        monkeypatch.setattr(mod, 'run_cn', boom)
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w'])
        with pytest.raises(SystemExit) as e:
            mod.main()
        assert e.value.code == 1
        assert patched['end'][0][0] is False
        assert 'SystemExit' in patched['end'][0][1]['error']

    def test_ledger_failure_does_not_block_aggregation(self, monkeypatch, capsys):
        """台账连接不可用时聚合照常输出 TASK_RESULT（台账只是旁路，绝非关键路径）。"""
        pool = _LedgerConnPool(fail_on=2)            # 第 1 次给主流程，第 2 次台账连接失败
        monkeypatch.setattr(mod, 'get_db_conn', pool)
        monkeypatch.setattr(mod, 'run_cn', lambda c, cy, a: {
            'rows_affected': 99, 'date': '2026-10-30'})
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w'])

        mod.main()                                   # 不抛异常
        out = capsys.readouterr().out
        assert '"rows_affected": 99' in out

    def test_ledger_end_failure_does_not_block_aggregation(self, monkeypatch, capsys):
        """回填台账失败同样不得影响 TASK_RESULT / 退出码。"""
        state = {'n': 0}

        def conn_factory():
            state['n'] += 1
            if state['n'] >= 3:                      # main + ledger_start 之后失败
                raise RuntimeError('db down')
            return _FakeConn(one_rows=[(1,)] if state['n'] == 2 else None)

        monkeypatch.setattr(mod, 'get_db_conn', conn_factory)
        monkeypatch.setattr(mod, 'run_cn', lambda c, cy, a: {
            'rows_affected': 77, 'date': '2026-10-30'})
        monkeypatch.setattr(sys, 'argv', ['x', '--cycle', '1w'])

        mod.main()
        assert '"rows_affected": 77' in capsys.readouterr().out
