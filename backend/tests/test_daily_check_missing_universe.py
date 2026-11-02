# -*- coding: utf-8 -*-
"""晨检「缺失股票」分母口径与任务台账口径测试。

背景（2026-11-02 实测）：
- 港股 `stock_basic` 中 `delist_date IS NULL` 共 2861 行，但最新列表同步只写入 2810 行，
  其余 51 条为「旧代码 / 股权 / －T / 长期停牌」等陈旧条目；它们本来就不产生日线，
  却被 `missing_stocks_hk` 当作活跃分母 → 长期误报「缺失 70+ 只」。
- 修复：仅对有 `missing_lookback_days` 配置的市场（当前为 hk=30 天），
  活跃分母只统计「近 N 个日历日内有过日线」的标的；A股口径保持不变。
- 同时锁定 `task_run_log` 只统计 `status='failed'`，不把 `running/skipped` 误报为失败。

全部用例使用假连接，不访问数据库、不访问网络。
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / 'scripts'))

import daily_check as dc  # noqa: E402


class _FakeCursor:
    """按序返回预置行，并记录执行过的 SQL。"""

    def __init__(self, rows):
        self._rows = list(rows)
        self._current = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._current = self._rows.pop(0) if self._rows else None

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current or []

    def close(self):
        pass


class _FakeConn:
    def __init__(self, rows):
        self.cur = _FakeCursor(rows)

    def cursor(self):
        return self.cur

    def close(self):
        pass


def _run_missing(market, latest, total_active, have_data):
    result = dc.CheckResult()
    result.use_color = False
    conn = _FakeConn([(latest,), (total_active,), (have_data,)])
    with patch.object(dc, 'get_db_conn', return_value=conn):
        dc.check_missing_stocks(result, market)
    return result, conn


class TestHkMissingDenominator:

    def test_hk_uses_recency_filter_and_no_false_warn(self):
        """港股分母用近 30 日有行情的标的（2824），缺失 39 只 → OK，不再误报。"""
        latest = date(2026, 10, 30)
        result, conn = _run_missing('hk', latest, 2824, 2785)

        assert result.checks['missing_stocks_hk'][0] == dc.CheckResult.OK
        sql, params = conn.cur.executed[1]
        assert 'EXISTS' in sql and 'q.trade_date' in sql
        assert params == ('hk', latest, latest - timedelta(days=30))
        assert '活跃(近30日)' in result.checks['missing_stocks_hk'][1]

    def test_hk_still_warns_when_recent_universe_really_missing(self):
        """近期活跃标的中缺口超过阈值时仍需 WARN（不能把真实缺口也放过）。"""
        latest = date(2026, 10, 30)
        result, _ = _run_missing('hk', latest, 2835, 2770)

        assert result.checks['missing_stocks_hk'][0] == dc.CheckResult.WARN
        assert '缺失 65 只' in result.checks['missing_stocks_hk'][1]

    def test_cn_denominator_unchanged(self):
        """A股仍按 delist_date 口径（含北交所排除），不引入近 N 日过滤。"""
        latest = date(2026, 11, 2)
        result, conn = _run_missing('cn', latest, 5247, 5217)

        assert result.checks['missing_stocks'][0] == dc.CheckResult.OK
        sql, params = conn.cur.executed[1]
        assert 'EXISTS' not in sql
        assert params == (latest,)
        assert '活跃(近' not in result.checks['missing_stocks'][1]


class TestTaskRunLogStatusFilter:

    def test_only_failed_rows_count(self):
        """SQL 只取 status='failed'，running/skipped 不得计为失败。"""
        result = dc.CheckResult()
        result.use_color = False
        conn = _FakeConn([[]])
        with patch.object(dc, 'get_db_conn', return_value=conn):
            dc.check_task_run_log(result)

        sql, _ = conn.cur.executed[0]
        assert "status = 'failed'" in sql
        assert "!=" not in sql
        assert result.checks['task_run_log'][0] == dc.CheckResult.OK

    def test_failed_row_reports_warn(self):
        """真实 failed 行仍要 WARN，并带出任务名/状态。"""
        result = dc.CheckResult()
        result.use_color = False
        conn = _FakeConn([[
            ('daily_import', 'failed', 'boom', date(2026, 11, 2))
        ]])
        with patch.object(dc, 'get_db_conn', return_value=conn):
            dc.check_task_run_log(result)

        assert result.checks['task_run_log'][0] == dc.CheckResult.WARN
        assert 'daily_import' in result.checks['task_run_log'][2]
