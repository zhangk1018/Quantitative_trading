# -*- coding: utf-8 -*-
"""
测试 scheduler_watchdog.py —— 定时任务「错过检测 + 自动补执行」（协作单 60.0）

覆盖范围：
- 调度时刻表：与 scripts/launchctl/*.plist **严格对齐**（防漂移）
- 判定逻辑：not_scheduled / not_due / satisfied / in_progress / unknown / missed
- 补执行：成功恢复、失败重试、冷却、重试上限 exhausted
- 状态持久化：scheduler_slot_log 的插入/更新与幂等
- 容错场景：服务中断（launchd 错过触发）、网络异常、系统休眠后补跑
- 零回归：正常时段（全部已成功）不产生任何动作
- 单实例文件锁
"""

import importlib.util
import os
import plistlib
import sys
from datetime import date, datetime, time as dtime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ===================== 模块加载 =====================

def _load_module():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(test_dir)
    module_path = os.path.join(backend_dir, "cron", "scheduler_watchdog.py")
    spec = importlib.util.spec_from_file_location("scheduler_watchdog", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def mod():
    return _load_module()


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 固定基准：2026-10-27 周二（ISO weekday=2），A 股交易日
DAY = date(2026, 10, 27)
PREV_DAY = date(2026, 10, 26)


# ===================== 轻量假数据库 =====================

class _Result:
    def __init__(self, rows=None, scalar=None, rowcount=0):
        self._rows = list(rows or [])
        self._scalar = scalar
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class _Conn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        return self.db._execute(str(sql), params or {})

    def commit(self):
        pass


class FakeDB:
    """按绑定参数分派的最小 SQLAlchemy Engine 替身（覆盖看护器用到的 5 类语句）。"""

    def __init__(self, open_days=None):
        # None => 所有日期都是交易日；否则仅集合内日期为交易日
        self.open_days = set(open_days) if open_days is not None else None
        self.statuses = {}   # {(date, task_name): status}
        self.started = {}    # {(date, task_name): start_time}（running 判定用）
        self.rows = {}       # {(slot_key, date): {...}}
        self.sql_log = []

    def connect(self):
        return _Conn(self)

    def _execute(self, sql, params):
        self.sql_log.append(sql)
        if 'names' in params:
            names = params['names']
            # `since` → 窗口查询（start_time >= since）；否则 → start_time::date = day
            if 'since' in params:
                allow = lambda d: d >= params['since'].date()      # noqa: E731
            else:
                allow = lambda d: d == params['day']               # noqa: E731
            latest = {}
            for (d, n), st in self.statuses.items():
                if n not in names or not allow(d):
                    continue
                if n not in latest or d > latest[n][0]:            # 每任务取最新一条
                    latest[n] = (d, st)
            return _Result(rows=[(n, st, self.started.get((d, n)))
                                 for n, (d, st) in latest.items()])
        if set(params.keys()) == {'day'}:
            if self.open_days is None:
                return _Result(scalar=1)
            return _Result(scalar=1 if params['day'] in self.open_days else 0)
        if 'k' in params:
            r = self.rows.get((params['k'], params['d']))
            if r is None:
                return _Result(rows=[])
            return _Result(rows=[(1, r.get('status'), r.get('attempts', 0),
                                  r.get('last_attempt_at'), r.get('last_error'))])
        if 'first_seen_at' in params:
            key = (params['slot_key'], params['biz_date'])
            if key in self.rows:
                return _Result(rowcount=0)
            self.rows[key] = {'status': params['status'], 'attempts': params['attempts'],
                              'last_attempt_at': params['last_attempt_at'],
                              'last_error': params['last_error']}
            return _Result(rowcount=1)
        key = (params['slot_key'], params['biz_date'])
        self.rows.setdefault(key, {}).update({
            'status': params['status'], 'attempts': params['attempts'],
            'last_attempt_at': params['last_attempt_at'], 'last_error': params['last_error']})
        return _Result(rowcount=1)

    # --------- 测试辅助 ---------
    def mark_success(self, day, task_names):
        for n in task_names:
            self.statuses[(day, n)] = 'success'

    def mark(self, day, task_name, status):
        self.statuses[(day, task_name)] = status


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture(autouse=True)
def _deterministic_defaults(monkeypatch):
    """隔离环境变量，使默认参数确定（回看 0 天、不停用任何槽位）。

    需要回看/停用的用例通过显式参数或 monkeypatch 覆盖。
    """
    monkeypatch.setenv('SCHED_WATCHDOG_LOOKBACK_DAYS', '0')
    monkeypatch.delenv('SCHED_WATCHDOG_DISABLED_SLOTS', raising=False)


@pytest.fixture
def alerts(mod):
    """拦截告警落盘，返回收集列表。"""
    collected = []
    with patch.object(mod, 'append_alerts', side_effect=lambda items: collected.extend(items) or len(items)):
        yield collected


# ===================== 调度时刻表 vs plist 对齐 =====================

class TestScheduleAlignment:
    """SLOTS 必须与 launchd plist 严格一致（防人工改时刻表后代码漂移）。"""

    PLIST_MAP = {
        'cn-stage1': 'com.quant.daily_job_runner.stage1.plist',
        'cn-stage2': 'com.quant.daily_job_runner.stage2.plist',
        'cn-stage3': 'com.quant.daily_job_runner.stage3.plist',
        'cn-weekly': 'com.quant.bar_aggregation.weekly.plist',
        'cn-monthly': 'com.quant.bar_aggregation.monthly.plist',
        'hk-job': 'com.quant.hk_job.plist',
        'hk-weekly': 'com.quant.bar_aggregation.overseas.weekly.hk.plist',
        'us-job': 'com.quant.us_job.plist',
        'us-weekly': 'com.quant.bar_aggregation.overseas.weekly.us.plist',
        'overseas-monthly': 'com.quant.bar_aggregation.overseas.monthly.plist',
    }

    @pytest.mark.parametrize('slot_key,plist_name', list(PLIST_MAP.items()))
    def test_slot_matches_plist(self, mod, slot_key, plist_name):
        path = os.path.join(PROJECT_ROOT, 'scripts', 'launchctl', plist_name)
        with open(path, 'rb') as f:
            cfg = plistlib.load(f)

        # StartCalendarInterval 的每一项 → (星期, 时, 分)；省略 Weekday 的项视为「每天」
        actual = set()
        for d in cfg['StartCalendarInterval']:
            hour, minute = d['Hour'], d['Minute']
            weekdays = [d['Weekday']] if 'Weekday' in d else sorted(mod.DAILY)
            for wd in weekdays:
                actual.add((wd, hour, minute))

        slot = mod.SLOT_BY_KEY[slot_key]
        assert actual == set(slot.schedule), f"{slot_key} 时刻表与 {plist_name} 不一致"

        # runner 脚本与参数也必须对齐
        args = cfg['ProgramArguments']
        assert any(a.endswith(os.path.basename(slot.runner)) for a in args), \
            f"{slot_key} runner 与 plist 不一致"
        for extra in slot.runner_args:
            assert extra in args, f"{slot_key} 参数 {extra} 未出现在 plist 中"

    def test_all_slots_have_plist(self, mod):
        assert set(self.PLIST_MAP) == set(mod.SLOT_BY_KEY)

    def test_expected_tasks_are_plist_backed(self, mod):
        """每个槽位都声明了用于判定「已完成」的任务名，且非空唯一。"""
        for slot in mod.SLOTS:
            names = mod.expected_task_names(slot)
            assert names, f"{slot.key} 未声明任务名"
            assert len(names) == len(set(names))

    def test_aggregation_slots_target_aggregation_script(self, mod):
        """聚合类槽位必须指向 compute_bar_aggregation.py 且台账任务名与脚本口径一致。"""
        from pathlib import Path
        agg = 'compute_bar_aggregation.py'
        for key in ('cn-weekly', 'cn-monthly', 'hk-weekly', 'us-weekly', 'overseas-monthly'):
            slot = mod.SLOT_BY_KEY[key]
            assert slot.runner.endswith(agg), f"{key} 应指向聚合脚本"
            assert '--cycle' in slot.runner_args, f"{key} 必须显式声明 --cycle"

        # 任务名口径与脚本 market_task_name() 完全一致（防止两侧各写一半）
        sys.path.insert(0, str(Path(PROJECT_ROOT) / 'backend'))
        from collector.etl import compute_bar_aggregation as agg_mod
        assert set(mod.expected_task_names(mod.SLOT_BY_KEY['cn-weekly'])) == {agg_mod.market_task_name('cn', '1w')}
        assert set(mod.expected_task_names(mod.SLOT_BY_KEY['cn-monthly'])) == {agg_mod.market_task_name('cn', '1m')}
        assert set(mod.expected_task_names(mod.SLOT_BY_KEY['hk-weekly'])) == {agg_mod.market_task_name('hk', '1w')}
        assert set(mod.expected_task_names(mod.SLOT_BY_KEY['us-weekly'])) == {agg_mod.market_task_name('us', '1w')}
        # 海外月K 单进程内含 hk + us 两条台账
        assert set(mod.expected_task_names(mod.SLOT_BY_KEY['overseas-monthly'])) == {
            agg_mod.market_task_name('hk', '1m'), agg_mod.market_task_name('us', '1m')}

    def test_hk_weekly_multi_trigger_uses_earliest_due_time(self, mod):
        """港股周K「周五 19:30 主 + 周六 09:30 兜底」：判定时点须取当日最早时刻。

        周五 19:35 就应判 missed 而**不能**因为周六那次触发而延后；
        周六 09:00（早于该日 09:30 触发）应判 not_due，避免数据源尚未产出就抢先补跑。
        """
        slot = mod.SLOT_BY_KEY['hk-weekly']
        friday, saturday = date(2026, 10, 30), date(2026, 10, 31)
        assert slot.due_time_on(friday) == dtime(19, 30)
        assert slot.due_time_on(saturday) == dtime(9, 30)
        assert slot.times_on(saturday) == (dtime(9, 30),)

        db = FakeDB()
        kind, _ = mod.evaluate_slot(db, slot, saturday, datetime(2026, 10, 31, 9, 0), 600)
        assert kind == 'not_due'
        kind, _ = mod.evaluate_slot(db, slot, friday, datetime(2026, 10, 30, 19, 45), 600)
        assert kind == 'missed'


# ===================== 判定逻辑 =====================

class TestEvaluateSlot:

    def test_not_scheduled_on_non_trading_day(self, mod):
        db = FakeDB(open_days=[])                      # A 股休市
        kind, msg = mod.evaluate_slot(db, mod.SLOT_BY_KEY['cn-stage1'], DAY,
                                      datetime(2026, 10, 27, 15, 45), 600)
        assert kind == 'not_scheduled'
        assert '非' in msg

    def test_not_scheduled_on_weekend(self, mod):
        db = FakeDB()
        sunday = date(2026, 10, 25)
        kind, _ = mod.evaluate_slot(db, mod.SLOT_BY_KEY['cn-stage1'], sunday,
                                    datetime(2026, 10, 25, 23, 0), 600)
        assert kind == 'not_scheduled'

    def test_not_due_within_grace(self, mod):
        db = FakeDB()
        slot = mod.SLOT_BY_KEY['cn-stage1']           # 15:30
        kind, msg = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 15, 35), 600)
        assert kind == 'not_due'
        assert '未到判定时刻' in msg

    def test_due_after_grace(self, mod):
        db = FakeDB()
        slot = mod.SLOT_BY_KEY['cn-stage1']
        kind, _ = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 15, 41), 600)
        assert kind == 'missed'

    def test_satisfied_when_all_tasks_success(self, mod, db):
        slot = mod.SLOT_BY_KEY['cn-stage2']
        db.mark_success(DAY, mod.expected_task_names(slot))
        kind, msg = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 17, 0), 600)
        assert kind == 'satisfied'
        assert '2/2' in msg

    def test_partial_success_is_missed(self, mod, db):
        slot = mod.SLOT_BY_KEY['cn-stage2']
        db.mark(DAY, 'daily_import', 'success')       # index_sync 缺失
        kind, msg = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 17, 0), 600)
        assert kind == 'missed'
        assert 'index_sync' in msg

    def test_running_is_in_progress(self, mod, db):
        slot = mod.SLOT_BY_KEY['cn-stage2']
        db.mark(DAY, 'daily_import', 'running')
        db.mark(DAY, 'index_sync', 'pending')
        kind, msg = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 17, 0), 600)
        assert kind == 'in_progress'

    def test_query_error_is_unknown(self, mod):
        broken = MagicMock()
        broken.connect.side_effect = RuntimeError('db down')
        kind, msg = mod.evaluate_slot(broken, mod.SLOT_BY_KEY['cn-stage1'], DAY,
                                      datetime(2026, 10, 27, 16, 0), 600)
        assert kind in ('unknown', 'not_scheduled')   # 日历查询失败按调度日处理 → unknown
        assert kind == 'unknown'

    def test_calendar_failure_defaults_to_scheduled(self, mod):
        broken = MagicMock()
        broken.connect.side_effect = RuntimeError('db down')
        assert mod.is_scheduled_day(broken, mod.SLOT_BY_KEY['cn-stage1'], DAY) is True


# ===================== 正常时段零回归 =====================

class TestNormalOperationUnaffected:

    def test_no_action_when_today_all_satisfied(self, mod, db, alerts):
        for slot in mod.SLOTS:                       # 含全部聚合槽位
            db.mark_success(DAY, mod.expected_task_names(slot))

        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 23, 0),
                                       grace_sec=600, lookback_days=0)
        runner.assert_not_called()
        assert summary['with_actions'] is False
        assert summary['failures'] == []
        assert summary['exhausted'] == []
        assert alerts == []
        assert db.rows == {}                    # 未产生任何台账行

    def test_no_action_before_any_slot_due(self, mod, db, alerts):
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 8, 0),
                                       grace_sec=600, lookback_days=0)
        runner.assert_not_called()
        assert summary['with_actions'] is False
        assert all(r['kind'] in ('not_due', 'not_scheduled') for r in summary['results'])


# ===================== 错过 → 自动补执行 =====================

class TestMissedCatchUp:

    def test_missed_slot_triggers_catchup_and_recovers(self, mod, db, alerts):
        """launchd 错过触发（当日无任何记录）→ 检测到 → 补执行 → 台账 success。"""
        slot = mod.SLOT_BY_KEY['cn-stage1']

        def fake_runner(_slot, _timeout):
            # 模拟既有 runner 补跑后写入 task_run_log 成功记录
            db.mark_success(DAY, mod.expected_task_names(_slot))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner) as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       only=['cn-stage1'], grace_sec=600,
                                       cooldown_sec=1800, max_attempts=3)

        runner.assert_called_once()
        row = db.rows[('cn-stage1', DAY)]
        assert row['status'] == 'success'
        assert row['attempts'] == 1
        assert summary['failures'] == []
        # 两条告警：检测到错过(WARNING) + 补执行成功(WARNING)
        levels = [a['level'] for a in alerts]
        assert levels.count('WARNING') == 2
        assert all(a['market'] == 'cn' for a in alerts)

    def test_already_recovered_slot_is_not_rerun(self, mod, db, alerts):
        db.rows[('cn-stage1', DAY)] = {'status': 'success', 'attempts': 1,
                                       'last_attempt_at': datetime(2026, 10, 27, 15, 45),
                                       'last_error': None}
        with patch.object(mod, 'invoke_runner') as runner:
            mod.run_watchdog(db, now=datetime(2026, 10, 27, 17, 0), only=['cn-stage1'],
                             grace_sec=600, cooldown_sec=1800, max_attempts=3)
        runner.assert_not_called()
        assert alerts == []

    def test_dry_run_has_no_side_effects(self, mod, db, alerts):
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       only=['cn-stage1'], grace_sec=600, dry_run=True)
        runner.assert_not_called()
        assert db.rows == {}
        assert alerts == []
        assert any(r['kind'] == 'would_catchup' for r in summary['results'])

    def test_only_filter_ignores_other_slots(self, mod, db, alerts):
        with patch.object(mod, 'invoke_runner', return_value=(True, "")) as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       only=['cn-stage2'], grace_sec=600)
        runner.assert_not_called()
        assert all(r['slot'] == 'cn-stage2' for r in summary['results'])

    def test_disabled_slot_via_env(self, mod, db, alerts, monkeypatch):
        monkeypatch.setenv('SCHED_WATCHDOG_DISABLED_SLOTS', 'cn-stage1,hk-job')
        for slot in mod.SLOTS:                              # 其余槽位正常完成
            if slot.key not in ('cn-stage1', 'hk-job'):
                db.mark_success(DAY, mod.expected_task_names(slot))
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       grace_sec=600)
        runner.assert_not_called()
        kinds = {r['slot']: r['kind'] for r in summary['results']}
        assert kinds['cn-stage1'] == 'disabled'
        assert kinds['hk-job'] == 'disabled'

    def test_status_scan_marks_stale_row_success(self, mod, db, alerts):
        """补执行后由 task_run_log 收敛：已成功但台账残留 failed 时改写为 success。"""
        slot = mod.SLOT_BY_KEY['cn-stage1']
        db.mark_success(DAY, mod.expected_task_names(slot))
        db.rows[('cn-stage1', DAY)] = {'status': 'failed', 'attempts': 1,
                                       'last_attempt_at': datetime(2026, 10, 27, 15, 40),
                                       'last_error': 'boom'}
        mod.run_watchdog(db, now=datetime(2026, 10, 27, 16, 0), only=['cn-stage1'], grace_sec=600)
        assert db.rows[('cn-stage1', DAY)]['status'] == 'success'


# ===================== 聚合槽位（周K/月K，协作单 61.0） =====================

class TestAggregationSlotsCatchUp:
    """聚合任务补台账后，看护须能识别其「错过」并自动补执行。"""

    def test_missed_cn_weekly_triggers_catchup(self, mod, db, alerts):
        """沪深周K 周五 18:30 未触发（无 cn:周K 台账）→ 判 missed → 补执行 → 台账 success。"""
        slot = mod.SLOT_BY_KEY['cn-weekly']
        friday = date(2026, 10, 30)
        db.mark_success(date(2026, 10, 26), ('cn:周K',))   # 上一交易日已执行（不构成今日豁免）
        assert mod.expected_task_names(slot) == ('cn:周K',)

        def fake_runner(_slot, _timeout):
            db.mark_success(friday, ('cn:周K',))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner) as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 30, 18, 45),
                                       only=['cn-weekly'], grace_sec=600, cooldown_sec=0)
        runner.assert_called_once()
        assert db.rows[('cn-weekly', friday)]['status'] == 'success'
        assert summary['failures'] == []

    def test_missed_hk_weekly_recovered_on_saturday_lookback(self, mod, db, alerts):
        """港股周K 周五 19:30 错过 → 次日（周六）巡检带 lookback 时补回周五。

        关键：补执行把台账写在**补执行当日（周六）**，因此复核必须按时间窗口判，
        否则回看日期会被误记 failed/exhausted 并刷 CRITICAL 假告警。
        """
        friday, saturday = date(2026, 10, 30), date(2026, 10, 31)

        def fake_runner(_slot, _timeout):
            db.mark_success(saturday, ('hk:周K',))     # 台账 start_time 落在「今天」（周六）
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 31, 9, 45),
                                       only=['hk-weekly'], grace_sec=600,
                                       cooldown_sec=0, lookback_days=1)
        assert db.rows[('hk-weekly', friday)]['status'] == 'success'
        assert summary['failures'] == [] and summary['exhausted'] == []
        assert [a['level'] for a in alerts] == ['WARNING', 'WARNING']

    def test_cross_day_catchup_not_marked_failed(self, mod, db, alerts):
        """纯行为回归：跨日补执行成功后不得出现 failed/exhausted（历史缺陷）。"""
        prev, today = date(2026, 10, 26), date(2026, 10, 27)
        db.mark(prev, 'daily_import', 'failed')        # 昨日失败，今日尚未跑
        db.mark(prev, 'index_sync', 'failed')

        def fake_runner(_slot, _timeout):
            db.statuses.pop((prev, 'daily_import'), None)   # 清理旧失败态
            db.statuses.pop((prev, 'index_sync'), None)
            db.mark_success(today, ('daily_import', 'index_sync'))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 4, 0),
                                       only=['cn-stage2'], grace_sec=600,
                                       cooldown_sec=0, lookback_days=1)
        assert db.rows[('cn-stage2', prev)]['status'] == 'success'
        assert summary['failures'] == [] and summary['exhausted'] == []
        assert not any(a['level'] == 'CRITICAL' for a in alerts)

    def test_overseas_monthly_requires_both_markets(self, mod, db):
        """海外月K 单进程内含 hk+us：只有其中一个成功时仍判 missed（不放过半程）。"""
        db.mark_success(DAY, ('hk:月K',))
        slot = mod.SLOT_BY_KEY['overseas-monthly']
        kind, msg = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 10, 30), 600)
        assert kind == 'missed'
        assert 'us:月K' in msg

    def test_overseas_monthly_satisfied_when_both_done(self, mod, db):
        db.mark_success(DAY, ('hk:月K', 'us:月K'))
        slot = mod.SLOT_BY_KEY['overseas-monthly']
        kind, _ = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 10, 30), 600)
        assert kind == 'satisfied'

    def test_cn_weekly_noop_run_still_satisfies(self, mod, db):
        """沪深周K 在「非本周最后交易日」的运行是 noop（rows=0）但仍写 success → 视为已执行。"""
        db.mark_success(DAY, ('cn:周K',))
        slot = mod.SLOT_BY_KEY['cn-weekly']
        kind, _ = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 18, 45), 600)
        assert kind == 'satisfied'

    def test_hk_weekly_missed_does_not_trigger_before_due(self, mod, db, alerts):
        """周五 19:00（早于 19:30 计划）不得补跑，避免数据源未产出即抢跑写假成功。"""
        friday = date(2026, 10, 30)
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 30, 19, 0),
                                       only=['hk-weekly'], grace_sec=600)
        runner.assert_not_called()
        assert all(r['kind'] in ('not_due', 'not_scheduled') for r in summary['results'])


# ===================== 服务中断 / 网络异常 容错 =====================

class TestFaultTolerance:

    def test_runner_failure_marks_failed_and_alerts(self, mod, db, alerts):
        """网络异常导致补执行失败 → 台账 failed + attempts=1 + CRITICAL 告警。"""
        with patch.object(mod, 'invoke_runner',
                          return_value=(False, "exit=1: requests.exceptions.ConnectionError")):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       only=['cn-stage1'], grace_sec=600,
                                       cooldown_sec=1800, max_attempts=3)

        row = db.rows[('cn-stage1', DAY)]
        assert row['status'] == 'failed'
        assert row['attempts'] == 1
        assert 'ConnectionError' in row['last_error']
        assert summary['failures'] == [f'cn-stage1@{DAY}']
        assert summary['exhausted'] == []
        assert [a['level'] for a in alerts] == ['WARNING', 'CRITICAL']

    def test_cooldown_blocks_immediate_retry(self, mod, db, alerts):
        db.rows[('cn-stage1', DAY)] = {'status': 'failed', 'attempts': 1,
                                       'last_attempt_at': datetime(2026, 10, 27, 15, 45),
                                       'last_error': 'boom'}
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 16, 0),
                                       only=['cn-stage1'], grace_sec=600, cooldown_sec=1800)
        runner.assert_not_called()
        assert any(r['kind'] == 'cooldown' for r in summary['results'])

    def test_retry_after_cooldown_succeeds(self, mod, db, alerts):
        """网络恢复后（超过冷却）自动重试并成功 → 数据未断档。"""
        slot = mod.SLOT_BY_KEY['cn-stage1']
        db.rows[('cn-stage1', DAY)] = {'status': 'failed', 'attempts': 1,
                                       'last_attempt_at': datetime(2026, 10, 27, 15, 45),
                                       'last_error': 'ConnectionError'}

        def fake_runner(_slot, _timeout):
            db.mark_success(DAY, mod.expected_task_names(_slot))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 16, 30),
                                       only=['cn-stage1'], grace_sec=600,
                                       cooldown_sec=1800, max_attempts=3)
        row = db.rows[('cn-stage1', DAY)]
        assert row['status'] == 'success'
        assert row['attempts'] == 2
        assert summary['failures'] == []

    def test_retry_limit_reached_becomes_exhausted(self, mod, db, alerts):
        db.rows[('cn-stage1', DAY)] = {'status': 'failed', 'attempts': 3,
                                       'last_attempt_at': datetime(2026, 10, 27, 15, 45),
                                       'last_error': 'boom'}
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 18, 0),
                                       only=['cn-stage1'], grace_sec=600,
                                       cooldown_sec=1800, max_attempts=3)
        runner.assert_not_called()
        assert db.rows[('cn-stage1', DAY)]['status'] == 'exhausted'
        assert summary['exhausted'] == [f'cn-stage1@{DAY}']
        assert [a['level'] for a in alerts] == ['CRITICAL']

    def test_exhausted_slot_is_not_retried_again(self, mod, db, alerts):
        db.rows[('cn-stage1', DAY)] = {'status': 'exhausted', 'attempts': 3,
                                       'last_attempt_at': datetime(2026, 10, 27, 15, 45),
                                       'last_error': 'boom'}
        with patch.object(mod, 'invoke_runner') as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 19, 0),
                                       only=['cn-stage1'], grace_sec=600, max_attempts=3)
        runner.assert_not_called()
        assert summary['exhausted'] == [f'cn-stage1@{DAY}']
        assert alerts == []                     # 不再重复告警

    def test_service_restart_before_slot_uses_runatload_semantics(self, mod, db, alerts):
        """服务中断后重启（凌晨）→ 当日更早的 us-job 槽位被检测并补执行。"""
        slot = mod.SLOT_BY_KEY['us-job']

        def fake_runner(_slot, _timeout):
            db.mark_success(DAY, mod.expected_task_names(_slot))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 9, 0),
                                       only=['us-job'], grace_sec=600,
                                       cooldown_sec=1800, max_attempts=3)
        assert db.rows[('us-job', DAY)]['status'] == 'success'
        assert summary['failures'] == []
        assert all(a['market'] == 'us' for a in alerts)

    def test_catchup_returns_ok_but_tasks_still_missing_is_failed(self, mod, db, alerts):
        """runner exit=0 但 task_run_log 仍缺任务 → 判定 failed（不放过假成功）。"""
        with patch.object(mod, 'invoke_runner', return_value=(True, "")):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       only=['cn-stage1'], grace_sec=600,
                                       cooldown_sec=0, max_attempts=3)
        assert db.rows[('cn-stage1', DAY)]['status'] == 'failed'
        assert summary['failures'] == [f'cn-stage1@{DAY}']

    def test_lookback_days_scans_previous_day(self, mod, db, alerts):
        slot = mod.SLOT_BY_KEY['cn-stage3']
        db.mark_success(DAY, mod.expected_task_names(slot))       # 今天已正常完成

        def fake_runner(_slot, _timeout):
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner) as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 19, 0),
                                       only=['cn-stage3'], grace_sec=600,
                                       cooldown_sec=0, max_attempts=3,
                                       lookback_days=1)
        # 昨天(10-26, 周一) 的 stage3 无记录 → 被补执行
        runner.assert_called_once()
        assert ('cn-stage3', PREV_DAY) in db.rows or ('cn-stage3', DAY) in db.rows
        biz_dates = {r['biz_date'] for r in summary['results']}
        assert str(PREV_DAY) in biz_dates and str(DAY) in biz_dates


# ===================== 台账读写 =====================

class TestSlotLedger:

    def test_insert_then_update(self, mod, db):
        slot = mod.SLOT_BY_KEY['cn-stage2']
        assert mod.upsert_slot_row(db, slot, DAY, mod.STATUS_DETECTED, 0,
                                   detail={'missing': ['daily_import']}, create=True) is True
        assert db.rows[('cn-stage2', DAY)]['status'] == mod.STATUS_DETECTED
        assert mod.upsert_slot_row(db, slot, DAY, mod.STATUS_SUCCESS, 1) is True
        assert db.rows[('cn-stage2', DAY)]['status'] == mod.STATUS_SUCCESS

    def test_insert_is_idempotent(self, mod, db):
        slot = mod.SLOT_BY_KEY['cn-stage2']
        mod.upsert_slot_row(db, slot, DAY, mod.STATUS_DETECTED, 0, create=True)
        mod.upsert_slot_row(db, slot, DAY, mod.STATUS_DETECTED, 0, create=True)
        assert len(db.rows) == 1

    def test_get_slot_row_roundtrip(self, mod, db):
        slot = mod.SLOT_BY_KEY['hk-job']
        db.rows[('hk-job', DAY)] = {'status': 'failed', 'attempts': 2,
                                    'last_attempt_at': datetime(2026, 10, 27, 19, 0),
                                    'last_error': 'boom'}
        row = mod.get_slot_row(db, 'hk-job', DAY)
        assert row['status'] == 'failed' and row['attempts'] == 2

    def test_get_slot_row_missing_returns_none(self, mod, db):
        assert mod.get_slot_row(db, 'hk-job', DAY) is None

    def test_write_failure_is_swallowed(self, mod):
        broken = MagicMock()
        broken.connect.side_effect = module_error(mod)
        slot = mod.SLOT_BY_KEY['cn-stage2']
        assert mod.upsert_slot_row(broken, slot, DAY, mod.STATUS_DETECTED, 0, create=True) is False


def module_error(mod):
    """构造能被 except OperationalError 捕获的异常。"""
    return mod.OperationalError('stmt', {}, Exception('boom'))


# ===================== 残留 running（进程被杀/断电） =====================

class TestZombieRunning:

    def test_stale_running_is_treated_as_missed(self, mod, db):
        """关机/断电残留 running 超过阈值 → 不再阻塞补执行，判 missed。"""
        slot = mod.SLOT_BY_KEY['cn-stage2']
        db.mark(DAY, 'daily_import', 'running')
        db.started[(DAY, 'daily_import')] = datetime(2026, 10, 27, 16, 32)
        db.mark(DAY, 'index_sync', 'running')
        db.started[(DAY, 'index_sync')] = datetime(2026, 10, 27, 16, 35)
        # 12 小时后巡检：远超 2 小时僵尸阈值
        kind, msg = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 28, 4, 0), 600)
        assert kind == 'missed'

    def test_fresh_running_blocks_catchup(self, mod, db):
        """正常调度正在跑 → in_progress，不重复触发。"""
        slot = mod.SLOT_BY_KEY['cn-stage2']
        db.mark(DAY, 'daily_import', 'running')
        db.started[(DAY, 'daily_import')] = datetime(2026, 10, 27, 16, 32)
        kind, _ = mod.evaluate_slot(db, slot, DAY, datetime(2026, 10, 27, 16, 45), 600)
        assert kind == 'in_progress'

    def test_zombie_running_then_catchup_recovers(self, mod, db, alerts):
        """进程在 16:32 被杀死（残留 running），当晚 22:00 巡检 → 按僵尸处理并补执行。"""
        slot = mod.SLOT_BY_KEY['cn-stage2']
        db.mark(DAY, 'daily_import', 'running')
        db.started[(DAY, 'daily_import')] = datetime(2026, 10, 27, 16, 32)

        def fake_runner(_slot, _timeout):
            db.mark_success(DAY, mod.expected_task_names(_slot))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner):
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 22, 0),
                                       only=['cn-stage2'], grace_sec=600, cooldown_sec=0)
        assert db.rows[('cn-stage2', DAY)]['status'] == 'success'
        assert summary['failures'] == []

    def test_cross_day_lookback_recovers_previous_day(self, mod, db, alerts):
        """跨天场景：次日巡检带上 lookback，补回前一日残留 running。"""
        db.mark(DAY, 'daily_import', 'running')
        db.started[(DAY, 'daily_import')] = datetime(2026, 10, 27, 16, 32)

        def fake_runner(_slot, _timeout):
            db.mark_success(DAY, mod.expected_task_names(_slot))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner) as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 28, 4, 0),
                                       only=['cn-stage2'], grace_sec=600,
                                       cooldown_sec=0, lookback_days=1)
        runner.assert_called_once()
        assert db.rows[('cn-stage2', DAY)]['status'] == 'success'
        assert summary['failures'] == []


# ===================== 台账不可用时的优雅降级 =====================

class TestLedgerUnavailable:

    def test_missing_table_degrades_gracefully(self, mod, db, alerts):
        """scheduler_slot_log 缺失/查询异常时：仍能在内存计数下于本轮上限内补执行。"""
        real_execute = db._execute

        def flaky(sql, params):
            if 'scheduler_slot_log' in sql:
                raise RuntimeError('relation "scheduler_slot_log" does not exist')
            return real_execute(sql, params)

        db._execute = flaky

        def fake_runner(_slot, _timeout):
            db.mark_success(DAY, mod.expected_task_names(_slot))
            return True, ""

        with patch.object(mod, 'invoke_runner', side_effect=fake_runner) as runner:
            summary = mod.run_watchdog(db, now=datetime(2026, 10, 27, 15, 45),
                                       only=['cn-stage1'], grace_sec=600, cooldown_sec=0)
        runner.assert_called_once()
        assert summary['failures'] == []


# ===================== 真实子进程调用（invoke_runner 管道） =====================

class TestInvokeRunner:

    def _slot(self, mod, script_rel):
        return mod.Slot('t-slot', 'cn', '测试槽位', ((1, 0, 0),), (),
                        script_rel, ())

    def test_success_exit_zero(self, mod, tmp_path, monkeypatch):
        (tmp_path / 'ok.py').write_text(
            'import sys\nprint("TASK_RESULT:{\\"rows_affected\\": 3}")\nsys.exit(0)\n',
            encoding='utf-8')
        monkeypatch.setattr(mod, 'BASE_DIR', str(tmp_path))
        ok, err = mod.invoke_runner(self._slot(mod, 'ok.py'), 60)
        assert ok is True and err == ''

    def test_failure_reports_exit_code(self, mod, tmp_path, monkeypatch):
        (tmp_path / 'bad.py').write_text(
            'import sys\nsys.stderr.write("ConnectionError: boom")\nsys.exit(3)\n',
            encoding='utf-8')
        monkeypatch.setattr(mod, 'BASE_DIR', str(tmp_path))
        ok, err = mod.invoke_runner(self._slot(mod, 'bad.py'), 60)
        assert ok is False
        assert 'exit=3' in err and 'ConnectionError' in err

    def test_timeout_is_reported(self, mod, tmp_path, monkeypatch):
        (tmp_path / 'slow.py').write_text('import time\ntime.sleep(30)\n', encoding='utf-8')
        monkeypatch.setattr(mod, 'BASE_DIR', str(tmp_path))
        ok, err = mod.invoke_runner(self._slot(mod, 'slow.py'), 1)
        assert ok is False and '超时' in err

    def test_missing_script_is_reported(self, mod, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, 'BASE_DIR', str(tmp_path))
        ok, err = mod.invoke_runner(self._slot(mod, 'nope.py'), 60)
        assert ok is False
        # Python 解释器可正常启动但脚本不存在 → 非零退出码
        assert 'exit=' in err

    def test_runner_args_are_forwarded(self, mod, tmp_path, monkeypatch):
        (tmp_path / 'args.py').write_text(
            'import sys\nsys.exit(0 if sys.argv[1:] == ["--stage", "2"] else 7)\n',
            encoding='utf-8')
        monkeypatch.setattr(mod, 'BASE_DIR', str(tmp_path))
        slot = mod.Slot('t', 'cn', 't', ((1, 0, 0),), (), 'args.py', ('--stage', '2'))
        ok, _ = mod.invoke_runner(slot, 60)
        assert ok is True


# ===================== 单实例锁 =====================

class TestSingleInstanceLock:

    def test_acquire_and_release(self, mod, tmp_path):
        lock = mod.SingleInstanceLock(str(tmp_path / 'w.lock'))
        assert lock.acquire() is True
        lock.release()

    def test_second_acquire_fails(self, mod, tmp_path):
        path = str(tmp_path / 'w.lock')
        l1 = mod.SingleInstanceLock(path)
        l2 = mod.SingleInstanceLock(path)
        assert l1.acquire() is True
        assert l2.acquire() is False
        l1.release()
        assert l2.acquire() is True
        l2.release()


# ===================== CLI / 状态输出 =====================

class TestCli:

    def test_print_status_runs(self, mod, db, capsys):
        mod.print_status(db, now=datetime(2026, 10, 27, 18, 0))
        out = capsys.readouterr().out
        for key in mod.SLOT_BY_KEY:
            assert key in out

    def test_unknown_only_slot_exits_nonzero(self, mod, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['scheduler_watchdog.py', '--only', 'nope'])
        assert mod.main() == 1