"""分市场周/月K聚合（港/美股按各自数据源日历）测试。

背景：周/月K 聚合原本只有一条 A 股日历驱动的路径（`trade_calendar` 判「本周最后交易日」），
港/美股只是被顺带聚合，且周期区间也取自 A 股日历。后果：
1. A 股休市而港/美开市的交易日（国庆 10-01/10-02、中秋 09-25）既不会触发聚合，
   也落在任何周期区间之外 → 永久孤儿，其日线永不进入周线；
2. 美股 T 日数据 T+1 08:30 才落库，而旧触发点为周五 18:30 → 美股周线系统性缺最后一天收盘；
3. 港/美股周线打标沿用 A 股末交易日（如 09-30），与看板「最新交易日」新鲜度判定错位。

本次改造把港/美股拆为独立分支：按各自数据源交易日历（HSI / .IXIC，与 import_{hk,us}_daily
同源）划分 ISO 周 / 自然月，先删后插实现幂等自愈；沪深分支逻辑保持不变，仅加 market 过滤。

全部用例使用假连接/假日历，不访问网络与数据库。

2026-10-03 创建
"""
import sys
from argparse import Namespace
from datetime import date
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import pytest

# 保证 `collector.* / core.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import compute_bar_aggregation as mod  # noqa: E402


class _FakeCursor:
    """假游标：记录执行的 SQL/参数，fetchone/fetchall 按预置队列返回。"""

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
    """假连接：单一复用游标，便于断言执行顺序。"""

    def __init__(self, one_rows: Optional[Sequence[Any]] = None,
                 all_rows: Optional[Sequence[Any]] = None):
        self.cur = _FakeCursor(one_rows, all_rows)
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return self.cur

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass


def _args(**kw: Any) -> Namespace:
    base = dict(date='2026-10-03', rebuild=False, rebuild_from=None,
                rebuild_to=None, lookback_periods=None)
    base.update(kw)
    return Namespace(**base)


def _inserts(conn: _FakeConn) -> List[Tuple[str, Any]]:
    return [(s, p) for s, p in conn.cur.executed if 'INSERT INTO stock_quotes' in s]


def _deletes(conn: _FakeConn) -> List[Tuple[str, Any]]:
    return [(s, p) for s, p in conn.cur.executed if 'DELETE FROM stock_quotes' in s]


# ===================== 周期桶基础算法 =====================

def test_bucket_key_and_span_weekly():
    """周桶 = ISO 周（周一~周日）；周六属当期，标识取周一。"""
    assert mod._bucket_key('1w', date(2026, 10, 3)) == date(2026, 9, 28)
    assert mod._bucket_span('1w', date(2026, 9, 28)) == (date(2026, 9, 28), date(2026, 10, 4))


def test_bucket_key_and_span_monthly():
    """月桶 = 自然月。"""
    assert mod._bucket_key('1m', date(2026, 10, 2)) == date(2026, 10, 1)
    assert mod._bucket_span('1m', date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 10, 31))


def test_weekly_settleable_only_from_saturday():
    """周桶须等该 ISO 周的周六才可结算 —— 周五当天不可（当天数据未必已落库）。"""
    key = date(2026, 9, 28)
    assert not mod._bucket_settleable('1w', key, date(2026, 10, 2))
    assert mod._bucket_settleable('1w', key, date(2026, 10, 3))


def test_monthly_settleable_only_after_month_end():
    """月桶须等自然月末才可结算 —— 否则美股月末最后 1~2 天（T+1 才落库）会被漏掉。"""
    assert not mod._bucket_settleable('1m', date(2026, 10, 1), date(2026, 10, 3))
    assert mod._bucket_settleable('1m', date(2026, 9, 1), date(2026, 10, 3))


def test_bucket_keys_enumeration():
    assert mod._bucket_keys('1w', date(2026, 9, 10), date(2026, 10, 1)) == [
        date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28),
    ]
    assert mod._bucket_keys('1m', date(2026, 8, 15), date(2026, 10, 3)) == [
        date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1),
    ]


# ===================== 先删后插（幂等自愈的关键） =====================

def test_overseas_bucket_deletes_then_inserts_scoped_by_market():
    """必须「先删后插」且都按 market 限定：删除用桶的自然日跨度，避免残留旧口径错位行。"""
    conn = _FakeConn()
    mod.compute_overseas_bucket(conn, 'us', '1w',
                                date(2026, 9, 28), date(2026, 10, 2), date(2026, 10, 2))

    sqls = [s for s, _ in conn.cur.executed]
    assert 'DELETE FROM stock_quotes' in sqls[0]
    assert 'INSERT INTO stock_quotes' in sqls[1]

    _, del_params = conn.cur.executed[0]
    assert del_params == ('1w', 'us', date(2026, 9, 28), date(2026, 10, 4))

    _, ins_params = conn.cur.executed[1]
    # (cycle, trade_date, trade_datetime基准, market, market过滤, start, end)
    assert ins_params[0] == '1w'
    assert ins_params[1] == date(2026, 10, 2)
    assert ins_params[3] == 'us' and ins_params[4] == 'us'
    assert ins_params[5] == date(2026, 9, 28) and ins_params[6] == date(2026, 10, 2)


# ===================== 国庆窗口端到端（核心回归） =====================

def test_national_day_window_labels_hk_weekly_as_1002(monkeypatch):
    """国庆窗口：A 股 10-01~10-07 休市、港股 10-02 开市 → 港股周线必须打标 10-02。

    同时验证 09-25（A 股休市、港股开市）不再成为孤儿：它归入 09-21 周并打标 09-25。
    """
    hk_cal = {
        date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23),
        date(2026, 9, 24), date(2026, 9, 25),
        date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 2),
    }
    monkeypatch.setattr(mod, '_overseas_calendar', lambda m, s, e: set(hk_cal))
    monkeypatch.setattr(mod, '_load_market_daily_dates', lambda c, m, s, e: set(hk_cal))

    conn = _FakeConn()
    res = mod.run_overseas(conn, 'hk', '1w', _args())

    labels = [p[1] for _, p in _inserts(conn)]
    assert labels == [date(2026, 9, 25), date(2026, 10, 2)]
    assert res['rows_affected'] == 2 and res['buckets_written'] == 2

    # 10-02 那根的聚合区间必须覆盖 09-28 ~ 10-02（含 A 股休市的那两天）
    last_params = _inserts(conn)[-1][1]
    assert last_params[5] == date(2026, 9, 28) and last_params[6] == date(2026, 10, 2)


def test_national_day_window_labels_us_weekly_as_1002(monkeypatch):
    """美股同窗口：10-01、10-02 均开市 → 周线打标 10-02，区间 09-28~10-02。"""
    us_cal = {
        date(2026, 9, 25),
        date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),
        date(2026, 10, 1), date(2026, 10, 2),
    }
    monkeypatch.setattr(mod, '_overseas_calendar', lambda m, s, e: set(us_cal))
    monkeypatch.setattr(mod, '_load_market_daily_dates', lambda c, m, s, e: set(us_cal))

    conn = _FakeConn()
    mod.run_overseas(conn, 'us', '1w', _args())

    labels = [p[1] for _, p in _inserts(conn)]
    assert labels == [date(2026, 9, 25), date(2026, 10, 2)]


def test_overseas_skips_bucket_missing_a_trading_day(monkeypatch):
    """完整度门禁：周期内该市场任一交易日未落库 → 整个桶跳过，不写残周期。"""
    cal = {date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),
           date(2026, 10, 1), date(2026, 10, 2)}
    have = cal - {date(2026, 9, 30)}  # 缺 09-30
    monkeypatch.setattr(mod, '_overseas_calendar', lambda m, s, e: set(cal))
    monkeypatch.setattr(mod, '_load_market_daily_dates', lambda c, m, s, e: set(have))

    conn = _FakeConn()
    res = mod.run_overseas(conn, 'us', '1w', _args())

    assert res['rows_affected'] == 0
    assert res['buckets_written'] == 0
    assert res['buckets_skipped'] == 1
    assert _inserts(conn) == [] and _deletes(conn) == []


def test_overseas_skips_when_calendar_unavailable(monkeypatch):
    """交易日历不可用（数据源返回 None）→ 只跳过，绝不猜测、不写入。"""
    monkeypatch.setattr(mod, '_overseas_calendar', lambda m, s, e: None)

    conn = _FakeConn()
    res = mod.run_overseas(conn, 'us', '1w', _args())

    assert res['rows_affected'] == 0
    assert conn.cur.executed == []


def test_overseas_skips_unsettled_month_bucket(monkeypatch):
    """10 月桶在 10-03 尚未到结算时点（月末未到）→ 不写，避免产出残缺月线。"""
    cal = {date(2026, 10, 1), date(2026, 10, 2)}
    monkeypatch.setattr(mod, '_overseas_calendar', lambda m, s, e: set(cal))
    monkeypatch.setattr(mod, '_load_market_daily_dates', lambda c, m, s, e: set(cal))

    conn = _FakeConn()
    res = mod.run_overseas(conn, 'us', '1m', _args(lookback_periods=1))

    assert res['rows_affected'] == 0 and res['buckets_written'] == 0
    assert _inserts(conn) == []


def test_overseas_rebuild_does_not_touch_unfinished_bucket(monkeypatch):
    """回填模式遍历区间内全部桶，但仍不结算未结束的桶（当前周/月留待正常运行写入）。"""
    cal = {date(2026, 9, 25), date(2026, 9, 28), date(2026, 10, 1), date(2026, 10, 2)}
    monkeypatch.setattr(mod, '_overseas_calendar', lambda m, s, e: set(cal))
    monkeypatch.setattr(mod, '_load_market_daily_dates', lambda c, m, s, e: set(cal))

    conn = _FakeConn()
    res = mod.run_overseas(conn, 'us', '1m',
                           _args(rebuild=True, rebuild_from='2026-09-01'))

    # 9 月桶可结算（月末已过）→ 按桶内最后交易日打标；10 月桶不可结算 → 不写
    labels = [p[1] for _, p in _inserts(conn)]
    assert labels == [date(2026, 9, 28)]
    assert res['buckets_written'] == 1


# ===================== 沪深分支不被越界改动 =====================

def test_cn_aggregation_scoped_to_cn_and_index():
    """沪深聚合必须显式限定 market IN ('cn','index')，不能再顺带写港/美股。"""
    assert "q.market IN ('cn', 'index')" in mod.CN_AGG_SQL
    assert "q.market = %s" in mod.OVERSEAS_AGG_SQL


def test_check_should_run_counts_cn_only():
    """沪深门禁的日线覆盖分子须带 market='cn'（旧版未带，港/美股混入导致比例失真）。"""
    conn = _FakeConn(one_rows=[
        (1,),                      # is_open
        (date(2026, 9, 30),),      # 该月最后一个交易日
        (5213,),                   # 沪深当日日线去重数
        (5000,),                   # 沪深股票总数
    ])
    should_run, reason = mod.check_should_run(conn, date(2026, 9, 30), '1m')

    assert should_run is True and '条件满足' in reason
    count_sql = [s for s, _ in conn.cur.executed if 'COUNT(DISTINCT code)' in s][0]
    assert "market = 'cn'" in count_sql


def test_overseas_rejects_cn_rebuild():
    """--rebuild 仅限港/美股（沪深历史不重建），由 main 参数校验拦截。"""
    with pytest.raises(SystemExit):
        sys.argv = ['compute_bar_aggregation.py', '--cycle', '1w',
                    '--market', 'cn', '--rebuild', '--from', '2025-01-01']
        mod.main()