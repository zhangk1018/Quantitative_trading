# -*- coding: utf-8 -*-
"""stock_basic 陈旧/已退市条目清理测试（协作单 63.0）。

背景（2026-10-28）：美股核心池 211 只中有 5 只长期拉不到行情
（PX/K/FI 从未有行情，MMC 停在 2026-01-13，EA 停在 2026-08-06）。
它们每天仍被逐只请求（必然「拉取为空」，噪声化失败清单）且仍计入覆盖率分母。

本文件覆盖：
- 清理器 `find_stale_codes` / `mark_delisted` 的 SQL 与参数、幂等性；
- CLI 安全闸：`--apply` 必须带 `--codes`、退市日格式校验、dry-run 不写库；
- 下载侧 `_list_us_codes` 只取 `delist_date IS NULL`（退市标的不再被请求）；
- 覆盖度门禁 `coverage_gaps` 分母只计在市标的（退市条目不再压低覆盖率）。

全部用例使用假连接，不访问网络与数据库。
"""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))


def _load_cleaner():
    path = BACKEND_DIR / 'scripts' / 'clean_stale_stock_basic.py'
    spec = importlib.util.spec_from_file_location('clean_stale_stock_basic', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def cleaner():
    return _load_cleaner()


# ==================== 假连接 ====================

class _FakeCursor:
    def __init__(self, one: Optional[List[Any]] = None, many: Optional[List[Any]] = None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.executed: List[Tuple[str, Any]] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []


class _FakeConn:
    def __init__(self, one=None, many=None, rowcount=1):
        self.cur = _FakeCursor(one=one, many=many)
        self.cur.rowcount = rowcount
        self.commits = 0
        self.closed = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed += 1


# ==================== 候选检测 ====================

class TestFindStale:

    def test_lists_candidates_with_last_date_and_rows(self, cleaner):
        conn = _FakeConn(many=[[
            ('PX', None, 0),
            ('MMC', date(2026, 1, 13), 258),
            ('EA', date(2026, 8, 6), 399),
        ]])
        got = cleaner.find_stale_codes(conn, 'us', 60)
        assert [c['code'] for c in got] == ['PX', 'MMC', 'EA']
        assert got[0]['last_dt'] is None and got[0]['rows'] == 0
        assert got[1]['last_dt'] == date(2026, 1, 13) and got[1]['rows'] == 258

    def test_sql_filters_active_only_and_threshold(self, cleaner):
        conn = _FakeConn(many=[[]])
        cleaner.find_stale_codes(conn, 'us', 60)
        sql, params = conn.cur.executed[0]
        assert 'delist_date IS NULL' in sql          # 已标记的不重复进候选
        assert params[0] == 'us'
        assert params[1] < date.today()              # 截止日 = today - stale_days

    def test_empty_candidates(self, cleaner):
        assert cleaner.find_stale_codes(_FakeConn(many=[[]]), 'us', 60) == []


# ==================== 标记退市 ====================

class TestMarkDelisted:

    def test_updates_only_active_rows_of_market(self, cleaner):
        conn = _FakeConn(rowcount=2)
        n = cleaner.mark_delisted(conn, 'us', ['K', 'EA'], date(2026, 8, 6))
        assert n == 2 and conn.commits == 1
        sql, params = conn.cur.executed[0]
        assert 'UPDATE stock_basic' in sql
        assert 'delist_date IS NULL' in sql          # 幂等：已标记的跳过
        assert params[0] == date(2026, 8, 6)
        assert params[1] == 'us' and params[2] == ['K', 'EA']

    def test_default_date_falls_back_to_last_quote(self, cleaner):
        """未显式给日期时取该股最后行情日，无行情再取今天（SQL COALESCE 语义）。"""
        conn = _FakeConn(rowcount=1)
        cleaner.mark_delisted(conn, 'us', ['EA'], None)
        sql, params = conn.cur.executed[0]
        assert params[0] is None
        assert 'COALESCE' in sql and 'MAX(q.trade_date)' in sql and 'CURRENT_DATE' in sql

    def test_no_codes_is_noop(self, cleaner):
        conn = _FakeConn()
        assert cleaner.mark_delisted(conn, 'us', [], None) == 0
        assert conn.cur.executed == []


# ==================== CLI 安全闸 ====================

class TestCliSafety:

    def test_apply_without_codes_is_rejected(self, cleaner, monkeypatch, capsys):
        monkeypatch.setattr(sys, 'argv', ['x', '--market', 'us', '--apply'])
        assert cleaner.main() == 1
        assert '--codes' in capsys.readouterr().out

    def test_bad_delist_date_is_rejected(self, cleaner, monkeypatch, capsys):
        monkeypatch.setattr(sys, 'argv', ['x', '--apply', '--codes', 'PX',
                                          '--delist-date', '2026/02/10'])
        assert cleaner.main() == 1
        assert 'YYYY-MM-DD' in capsys.readouterr().out

    def test_dry_run_never_writes(self, cleaner, monkeypatch, capsys):
        conn = _FakeConn(many=[[('PX', None, 0)]])
        monkeypatch.setattr(cleaner, '_connect', lambda: conn)
        monkeypatch.setattr(sys, 'argv', ['x', '--market', 'us'])
        assert cleaner.main() == 0
        assert conn.commits == 0
        out = capsys.readouterr().out
        assert 'PX' in out and 'dry-run' in out

    def test_apply_marks_and_alerts(self, cleaner, monkeypatch, capsys):
        conn = _FakeConn(many=[[('EA', date(2026, 8, 6), 399)]], rowcount=1)
        sent = []
        monkeypatch.setattr(cleaner, '_connect', lambda: conn)
        monkeypatch.setattr(cleaner, 'append_alerts',
                            lambda items: sent.extend(items) or len(items))
        monkeypatch.setattr(sys, 'argv', ['x', '--market', 'us', '--apply',
                                          '--codes', 'EA', '--delist-date', '2026-08-06'])
        assert cleaner.main() == 0
        assert conn.commits == 1
        assert sent and sent[0]['market'] == 'us' and 'EA' in sent[0]['message']


# ==================== 下载侧：退市标的不再被请求 ====================

class TestListUsCodesExcludesDelisted:

    def test_query_filters_delist_date(self):
        from collector.etl import import_us_daily as us
        conn = _FakeConn(many=[[('AAPL',), ('MSFT',)]])
        codes = us._list_us_codes(conn)
        assert codes == ['AAPL', 'MSFT']
        sql, params = conn.cur.executed[0]
        assert 'delist_date IS NULL' in sql
        assert params == ('us',)

    def test_empty_active_list_falls_back_to_source(self):
        """在市列表为空（如全部被标记）才回退数据源清单，避免静默断流。"""
        from collector.etl import import_us_daily as us

        class _Src:
            def get_stock_list(self):
                import pandas as pd
                return pd.DataFrame({'code': ['AAPL']})

        conn = _FakeConn(many=[[]])
        assert us._list_us_codes(conn, _Src()) == ['AAPL']


# ==================== 覆盖度分母：退市标的不再压低覆盖率 ====================

class TestCoverageBaselineExcludesDelisted:

    def test_baseline_sql_filters_delist_date(self):
        from collector.etl.market_download_common import coverage_gaps

        conn = _FakeConn(one=[(208,), (205,)])       # 基线 208（在市），当日覆盖 205
        coverage_gaps(conn, 'us', {date(2026, 10, 27)}, 0.90)
        baseline_sql, params = conn.cur.executed[0]
        assert 'delist_date IS NULL' in baseline_sql
        assert params == ('us',)

    def test_ratio_uses_active_count(self):
        """205/208 ≈ 98.6% ≥ 90% → 无缺口（分母若仍含 3 只退市条目也只是 205/211=97.2%，
        区别体现在「退市条目再多一些」时才误报；此处锁定基线与当日计数对接正确）。"""
        from collector.etl.market_download_common import coverage_gaps

        conn = _FakeConn(one=[(208,), (205,)])
        assert coverage_gaps(conn, 'us', {date(2026, 10, 27)}, 0.90) == []

    def test_gap_reported_when_below_threshold(self):
        from collector.etl.market_download_common import coverage_gaps

        conn = _FakeConn(one=[(208,), (175,)])
        gaps = coverage_gaps(conn, 'us', {date(2026, 10, 27)}, 0.90)
        assert len(gaps) == 1
        d, n, ratio, total = gaps[0]
        assert n == 175 and total == 208 and ratio < 0.90


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
