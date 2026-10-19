"""监控看板「周K/月K 期望打标日」判据测试。

背景：看板新鲜度门禁原对 cycle 任务一律比较「最近交易日」（`latest < expected → pending`），
但周K/月K 的数据行以「周期最后一个交易日」打标（见 compute_bar_aggregation.py），
周期未结束时该行天然不存在：
- 月K 在当月月末才结算 → 每月 1 号到月末，cn/hk/us 三市场月K 恒报「数据未更新」；
- 周K（港/美股）要到该周周六才结算 → 每周一~四周K 恒报 pending。
修复后：周期已到结算时点 → 期望取该周期最后交易日；未到 → 回退上一周期。

全部用例使用受控日历（monkeypatch `_load_trade_days`），不访问网络与数据库。

2026-10-03 创建
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.api.router import monitor as mod  # noqa: E402

BEIJING = timezone(timedelta(hours=8))


def _days(*ds: date) -> frozenset:
    return frozenset(d.isoformat() for d in ds)


# 受控交易日历（沪深口径：国庆 10-01~10-07 休市、周末休市），覆盖 2026-09-14 ~ 2026-11-06
SSE_DAYS = _days(
    date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18),
    date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24),
    date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),
    date(2026, 10, 8), date(2026, 10, 9),
    date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16),
    date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23),
    date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30),
    date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6),
)


def _bj(y: int, m: int, d: int, hour: int = 12) -> datetime:
    return datetime(y, m, d, hour, 0, tzinfo=BEIJING)


def _patch_cal(monkeypatch, days):
    monkeypatch.setattr(mod, "_load_trade_days", lambda cal_code: days)


# ===================== _last_trade_day_on_or_before =====================

def test_last_trade_day_walks_back_over_holiday(monkeypatch):
    """国庆假期中查「<= 10-05 的最近交易日」应回退到 09-30（跨 7 天长假）。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._last_trade_day_on_or_before("cn", date(2026, 10, 5)) == "2026-09-30"


# ===================== 月K 期望日 =====================

def test_monthly_expected_is_previous_month_while_current_month_unsettled(monkeypatch):
    """10 月 3 日：本月月末未到 → 期望应为 9 月最后交易日 09-30（而非最近交易日 09-30/10-02）。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1m", "cn", _bj(2026, 10, 3)) == "2026-09-30"
    assert mod._expected_period_label("1m", "hk", _bj(2026, 10, 3)) == "2026-09-30"


def test_monthly_expected_no_false_pending_mid_month(monkeypatch):
    """回归核心：月内任意一天，月K 数据打标 09-30 都不应再被判为 pending。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    cfg = {"cycle_col": "cycle", "cycle_val": "1m"}
    for day in (3, 15, 29, 30):   # 10-31 为自然月末，已到结算时点，故不在本用例内
        exp = mod._expected_date_for_task(cfg, "cn", _bj(2026, 10, day))
        assert exp == "2026-09-30", f"10-{day} 期望日应回退到 9 月末交易日"
        assert not ("2026-09-30" < exp), f"10-{day} 不应把 09-30 的月K 判为 pending"


def test_monthly_expected_settles_after_month_end(monkeypatch):
    """跨月后（11-02）：期望变为 10 月最后交易日 10-30。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1m", "cn", _bj(2026, 11, 2)) == "2026-10-30"


def test_monthly_hk_us_settles_after_next_day_production(monkeypatch):
    """协作单 58.0 遗留：海外月K 任务「每日 10:00」产出 → 结算点 = 月末次日 10:30（北京时）。

    旧口径月末 00:00 即期望新周期，而任务要到次日 10:00 才产出 → 1.4~3.4 天假 pending；本改后消除。
    """
    _patch_cal(monkeypatch, SSE_DAYS)
    # hk（与北京同时区）：10-31 与 11-01 上午仍未到结算点 → 期望回退上一周期 09-30（而非 10-30）
    assert mod._expected_period_label("1m", "hk", _bj(2026, 10, 31, 9)) == "2026-09-30"
    assert mod._expected_period_label("1m", "hk", _bj(2026, 11, 1, 9)) == "2026-09-30"
    # 11-01 10:30 后 → 期望本月（10 月）最后交易日 10-30（任务已于 11-01 10:00 产出）
    assert mod._expected_period_label("1m", "hk", _bj(2026, 11, 1, 12)) == "2026-10-30"
    # 月中照常期望上一月末 10-30
    assert mod._expected_period_label("1m", "hk", _bj(2026, 11, 15)) == "2026-10-30"
    # us（北京 -12h）：北京 11-01 09:00 时美东仍为 10-31 → 同样回退上一周期；12:00 后结算
    assert mod._expected_period_label("1m", "us", _bj(2026, 11, 1, 9)) == "2026-09-30"
    assert mod._expected_period_label("1m", "us", _bj(2026, 11, 1, 12)) == "2026-10-30"


def test_monthly_cn_unchanged(monkeypatch):
    """回归：cn 月K 结算点保持「自然月末已到」（cn 链在月末最后交易日 18:45 已产出），本次未改。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1m", "cn", _bj(2026, 10, 31, 9)) == "2026-10-30"
    assert mod._expected_period_label("1m", "cn", _bj(2026, 11, 1, 9)) == "2026-10-30"


# ===================== 周K 期望日 =====================

def test_weekly_expected_falls_back_before_week_settlement(monkeypatch):
    """周五（该 ISO 周周六未到）：期望仍为上一周最后交易日（<= 09-27 → 09-24）。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1w", "cn", _bj(2026, 10, 2, 18)) == "2026-09-24"


def test_weekly_expected_settles_from_saturday(monkeypatch):
    """周六（该 ISO 周已过结算时点）：期望变为本周最后交易日（<= 10-04 → 09-30）。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1w", "cn", _bj(2026, 10, 3)) == "2026-09-30"


def test_weekly_hk_settles_at_friday_evening(monkeypatch):
    """协作单 58.0：hk 周K 任务周五 19:30 产出 → hk 结算点同步改「周五 19:30」。

    周五 19:30 前仍回退上一周（任务未跑，不应期望本周）；19:30 后期望变本周最后交易日。
    这消除了旧实现「周六 00:00 即期望本周、任务却周六 09:30 才产出」的 ~9.5h 假 pending。
    """
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1w", "hk", _bj(2026, 10, 16, 9)) == "2026-10-09"    # 周五 09:00
    assert mod._expected_period_label("1w", "hk", _bj(2026, 10, 16, 19)) == "2026-10-09"   # 周五 19:00（未到 19:30）
    assert mod._expected_period_label("1w", "hk", _bj(2026, 10, 16, 20)) == "2026-10-16"   # 周五 20:00（已产出）
    assert mod._expected_period_label("1w", "hk", _bj(2026, 10, 17, 8)) == "2026-10-16"    # 周六上午（无假 pending）


def test_weekly_cn_still_settles_from_saturday(monkeypatch):
    """回归：cn 周K 结算点保持「周六已到」（cn 链周五盘后 ~18:50 已产出），本次未改。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._expected_period_label("1w", "cn", _bj(2026, 10, 16, 18)) == "2026-10-09"   # 周五
    assert mod._expected_period_label("1w", "cn", _bj(2026, 10, 17, 0)) == "2026-10-16"    # 周六


def test_weekly_expected_no_false_pending_monday_to_thursday(monkeypatch):
    """回归：周一~周四，周K 数据打标上周最后交易日不应被判为 pending。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    cfg = {"cycle_col": "cycle", "cycle_val": "1w"}
    for day in (5, 6, 7, 8):   # 10-05 ~ 10-08（周一~周四）
        exp = mod._expected_date_for_task(cfg, "cn", _bj(2026, 10, day))
        assert exp == "2026-09-30"
        assert not ("2026-09-30" < exp), f"10-{day} 不应把 09-30 的周K 判为 pending"


# ===================== 非 cycle 任务保持原判据 =====================

def test_non_cycle_task_still_uses_last_trade_date(monkeypatch):
    """非 cycle 任务（如宽表同步）仍用最近已收盘交易日，不受本次改动影响。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    cfg = {"table": "stock_daily_snapshot", "date_col": "trade_date"}
    assert mod._expected_date_for_task(cfg, "cn", _bj(2026, 10, 15, 16)) == "2026-10-15"
    # 未到收盘钟点（cn 15:00）→ 回退上一交易日
    assert mod._expected_date_for_task(cfg, "cn", _bj(2026, 10, 15, 14)) == "2026-10-14"


def test_get_last_trade_date_behaviour_unchanged(monkeypatch):
    """_get_last_trade_date 抽取公共 walk-back 后行为不变。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    assert mod._get_last_trade_date("cn", _bj(2026, 9, 30, 16)) == "2026-09-30"
    assert mod._get_last_trade_date("cn", _bj(2026, 10, 3)) == "2026-09-30"   # 假期内回退


# ===================== 日历不可用时的降级 =====================

def test_fallback_weekend_only_when_calendar_unavailable(monkeypatch):
    """日历不可用：cn/hk 降级为仅周末判定，仍能算出周K 期望日（周六 → 上一交易日周五）。"""
    _patch_cal(monkeypatch, None)
    assert mod._expected_period_label("1w", "cn", _bj(2026, 10, 3)) == "2026-10-02"
    assert mod._expected_period_label("1m", "cn", _bj(2026, 10, 3)) == "2026-09-30"


def test_us_uses_local_date_offset(monkeypatch):
    """美股按当地日期（北京 -12h）推算周期：北京周六 09:00 时美东仍为周五。"""
    _patch_cal(monkeypatch, SSE_DAYS)
    # 北京 10-03 09:00 → 美东 10-02：本周未到结算时点，期望回退上一周
    assert mod._expected_period_label("1w", "us", _bj(2026, 10, 3, 9)) == "2026-09-24"
    # 北京 10-03 12:00 → 美东 10-03（周六）：本周已结算
    assert mod._expected_period_label("1w", "us", _bj(2026, 10, 3, 12)) == "2026-09-30"