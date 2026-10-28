# -*- coding: utf-8 -*-
"""美股增量「拉取为空」补拉与分类股 symbol 映射测试（协作单 62.0）。

事故背景（2026-10-28 实测，看板「⚠️ 疑似残日 · 日线覆盖 175/205 · 85.4%」）：
- 新浪源限流时 `stock_us_daily` 返回空报文 → `_fetch_us` 返回 None → `import_one` 记一条
  INFO「拉取为空（可能限流或停牌）」即计入失败、**完全不重试**。当日 211 只中 36 只命中
  （IBM/WMT/PEP/MA/C/F… 全为流动性最好的大盘股，事后立刻重拉即成功），当日只入库 175 只
  （82.9%）→ 残日告警；下游指标/宽表/Parquet 也基于残缺数据计算。
- `BRK-B` 则始终失败（`IndexError`）：新浪用**点号**分隔分类股类别（`BRK.B`），
  传连字符会拿到非预期报文。

本文件覆盖：
- `_to_ak_symbol` 美股分类股 'BRK-B' → 'BRK.B'，普通代码不变、港股行为不变；
- `pull_one_with_retry` 的空拉重试、异常重试、有界性、重试计数；
- `run_incremental` 的行内补拉、补漏轮、`fail` 按「最终仍缺标的数」统计、
  覆盖度达标后不再补漏、以及补漏失败时仍不推进进度。

全部用例使用假数据源/假连接，不访问网络与数据库。
"""
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pytest
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import import_us_daily as us  # noqa: E402
from collector.datasource.akshare import _to_ak_symbol  # noqa: E402


# ==================== 假对象 ====================

class _FakeCursor:
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
    """无任何休眠（含重试退避），使测试零等待。"""
    batch_interval_min_sleep = 0.0
    batch_interval_max_sleep = 0.0
    batch_retry_min_sleep = 0.0
    batch_retry_max_sleep = 0.0
    incremental_lookback_days = 7


class _FakeSrc:
    def __init__(self, calendar: Optional[Set[date]] = None):
        self._calendar = calendar
        self.cfg = _FakeCfg()

    def download_us_trade_dates(self, start=None, end=None):
        return self._calendar


US_CALENDAR = {date(2026, 10, 26), date(2026, 10, 27)}


def _seq_import_one(responses: Dict[str, List[tuple]]):
    """按代码返回**预置响应序列**（逐次弹出），并记录调用次数。

    响应项为 (q, a, max_date) 或 Exception 实例。
    """
    calls: Dict[str, int] = {}

    def _fn(_src, _conn, code, start=None, end=None, dry_run=False):
        n = calls.get(code, 0) + 1
        calls[code] = n
        seq = responses.get(code, [(1, 0, '2026-10-27')])
        item = seq[min(n - 1, len(seq) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item

    _fn.calls = calls          # type: ignore[attr-defined]
    return _fn


# ==================== 分类股 symbol 映射 ====================

class TestToAkSymbol:

    def test_us_class_share_uses_dot(self):
        """'BRK-B' → 'BRK.B'（新浪分类股用点号；连字符会导致 IndexError/空报文）。"""
        assert _to_ak_symbol('BRK-B', 'us') == 'BRK.B'
        assert _to_ak_symbol('BF-B', 'us') == 'BF.B'

    def test_us_plain_ticker_unchanged(self):
        assert _to_ak_symbol('AAPL', 'us') == 'AAPL'
        assert _to_ak_symbol('aapl', 'us') == 'AAPL'
        assert _to_ak_symbol('  MSFT ', 'us') == 'MSFT'

    def test_hk_symbol_unchanged(self):
        """港股行为不得被连带改动（0700.HK → 00700，5 位补零）。"""
        assert _to_ak_symbol('0700.HK', 'hk') == '00700'
        assert _to_ak_symbol('700', 'hk') == '00700'


# ==================== 单只补拉 ====================

class TestPullOneWithRetry:

    def test_recovers_after_transient_empty(self):
        """首次空拉、第二次成功 → 返回数据，并记 1 次补拉。"""
        src, stats = _FakeSrc(), {'retried': 0}
        fake = _seq_import_one({'IBM': [(0, 0, None), (1, 0, '2026-10-27')]})
        with patch.object(us, 'import_one', side_effect=fake):
            q, a, max_date, err = us.pull_one_with_retry(
                src, _FakeConn(), 'IBM', start='2026-10-27', end_excl='2026-10-28',
                stats=stats)
        assert (q, a, max_date, err) == (1, 0, '2026-10-27', None)
        assert fake.calls['IBM'] == 2 and stats['retried'] == 1

    def test_persistent_empty_stays_empty(self):
        """持续空拉（真停牌）→ 最终仍为空且 err 为 None，重试次数有界。"""
        src, stats = _FakeSrc(), {'retried': 0}
        fake = _seq_import_one({'XXXX': [(0, 0, None)]})
        with patch.object(us, 'import_one', side_effect=fake):
            q, a, _md, err = us.pull_one_with_retry(
                src, _FakeConn(), 'XXXX', start='2026-10-27', end_excl='2026-10-28',
                inline_retries=2, stats=stats)
        assert (q, a, err) == (0, 0, None)
        assert fake.calls['XXXX'] == 3          # 1 次 + 2 次补拉，绝不无限重试
        assert stats['retried'] == 2

    def test_transient_exception_is_retried(self):
        """网络异常（瞬时可恢复）→ 重试后成功。"""
        src = _FakeSrc()
        fake = _seq_import_one({'WMT': [ConnectionError('boom'), (1, 0, '2026-10-27')]})
        with patch.object(us, 'import_one', side_effect=fake):
            q, _a, _md, err = us.pull_one_with_retry(
                src, _FakeConn(), 'WMT', start='2026-10-27', end_excl='2026-10-28')
        assert (q, err) == (1, None) and fake.calls['WMT'] == 2

    def test_persistent_exception_returns_error(self):
        """确定性异常（如 symbol 写错）→ 重试后仍失败，并把异常回传给调用方。"""
        src = _FakeSrc()
        fake = _seq_import_one({'BAD': [IndexError('list index out of range')]})
        with patch.object(us, 'import_one', side_effect=fake):
            q, _a, _md, err = us.pull_one_with_retry(
                src, _FakeConn(), 'BAD', start='2026-10-27', end_excl='2026-10-28',
                inline_retries=1)
        assert q == 0 and isinstance(err, IndexError)

    def test_no_retry_when_disabled(self):
        src = _FakeSrc()
        fake = _seq_import_one({'IBM': [(0, 0, None), (1, 0, '2026-10-27')]})
        with patch.object(us, 'import_one', side_effect=fake):
            q, _a, _md, _e = us.pull_one_with_retry(
                src, _FakeConn(), 'IBM', start='2026-10-27', end_excl='2026-10-28',
                inline_retries=0)
        assert q == 0 and fake.calls['IBM'] == 1


# ==================== 增量主流程 ====================

class TestIncrementalBackfill:

    def _run(self, conn, monkeypatch, responses, coverage: List[bool],
             codes=('AAPL', 'IBM', 'WMT')):
        """驱动 run_incremental；coverage 为 `_window_coverage_ok` 的逐次返回序列。

        序列耗尽后**沿用最后一个值**（覆盖度查询会出现在每个补漏轮之前 + 回写前各一次，
        调用次数随场景变化，用「末值复用」避免测试与内部轮次强耦合）。
        """
        state = {'i': 0}

        def _cov(*_a, **_k):
            i = min(state['i'], len(coverage) - 1)
            state['i'] += 1
            return coverage[i]

        fake = _seq_import_one(responses)
        with patch.object(us, 'import_one', side_effect=fake), \
                patch.object(us, '_list_us_codes', return_value=list(codes)), \
                patch.object(us, '_probe_src_latest', return_value='2026-10-27'), \
                patch.object(us, '_window_coverage_ok', side_effect=_cov), \
                patch.object(us, '_us_trading_days_between', return_value=US_CALENDAR), \
                patch.object(us, 'set_last_sync_date') as mock_write:
            stats = us.run_incremental(_FakeSrc(US_CALENDAR), conn)
        return stats, mock_write, fake

    def test_residual_day_recovered_by_backfill(self, monkeypatch):
        """残日场景：2 只首轮空拉 → 补漏轮全部拉回 → 覆盖达标 → 推进进度。

        这是 2026-10-28「175/205 残日」的回归用例：修复前 `fail` 恒等于首轮失败数，
        且不补漏 → 残日 + 进度不推进；修复后应全部补齐并正常推进。
        """
        conn = _FakeConn([('2026-10-26',), (None, None)])
        # 首轮：AAPL 成功，IBM/WMT 空拉（行内补拉 1 次仍空）
        # 补漏轮：IBM/WMT 均恢复
        responses = {
            'AAPL': [(1, 0, '2026-10-27')],
            'IBM': [(0, 0, None), (0, 0, None), (1, 0, '2026-10-27')],
            'WMT': [(0, 0, None), (0, 0, None), (1, 0, '2026-10-27')],
        }
        # 覆盖度查询：补漏第 1 轮前不达标，回写前达标
        stats, mock_write, fake = self._run(conn, monkeypatch, responses, [False, True])

        assert stats['success'] == 3 and stats['quotes'] == 3
        assert stats['fail'] == 0
        assert stats['backfilled'] == 2
        mock_write.assert_called_once_with(conn, '2026-10-27')
        # 每只 3 次请求 = 首轮 1 次 + 行内补拉 1 次 + 补漏 1 次
        assert fake.calls == {'AAPL': 1, 'IBM': 3, 'WMT': 3}

    def test_no_backfill_when_coverage_already_ok(self, monkeypatch):
        """首轮即全部成功时不得发起补漏轮（零额外请求）。"""
        conn = _FakeConn([('2026-10-26',), (None, None)])
        responses = {c: [(1, 0, '2026-10-27')] for c in ('AAPL', 'IBM', 'WMT')}
        stats, mock_write, fake = self._run(conn, monkeypatch, responses, [True])

        assert stats['success'] == 3 and stats['backfilled'] == 0
        assert fake.calls == {'AAPL': 1, 'IBM': 1, 'WMT': 1}
        mock_write.assert_called_once()

    def test_backfill_stops_when_coverage_reached(self, monkeypatch):
        """补漏第 1 轮后覆盖已达标 → 不再进入第 2 轮。"""
        conn = _FakeConn([('2026-10-26',), (None, None)])
        responses = {
            'AAPL': [(1, 0, '2026-10-27')],
            'IBM': [(0, 0, None), (0, 0, None), (1, 0, '2026-10-27')],
            'WMT': [(0, 0, None), (0, 0, None), (0, 0, None)],   # 始终空 → 留存
        }
        # 第1轮前不达标；第2轮前达标 → 终止（WMT 不再被额外请求）
        stats, mock_write, fake = self._run(conn, monkeypatch, responses, [False, True])

        assert fake.calls['WMT'] == 3        # 首轮 2 + 补漏 1，未进入第 2 轮补漏
        assert stats['fail'] == 1            # 最终仍缺 1 只
        assert stats['success'] == 2
        mock_write.assert_called_once()      # 覆盖度由门禁决定（本例返回 True）

    def test_unresolved_still_blocks_writeback(self, monkeypatch):
        """补漏后仍缺 → 覆盖度门禁不通过 → 不得推进 last_sync_date。"""
        conn = _FakeConn([('2026-10-26',), (None, None)])
        responses = {c: [(0, 0, None)] for c in ('AAPL', 'IBM', 'WMT')}
        stats, mock_write, fake = self._run(conn, monkeypatch, responses, [False, False])

        assert stats['fail'] == 3 and stats['success'] == 0
        mock_write.assert_not_called()
        # 每只：首轮 2 次（含行内补拉）+ 2 轮补漏 = 4
        assert fake.calls == {'AAPL': 4, 'IBM': 4, 'WMT': 4}

    def test_fail_counts_codes_not_attempts(self, monkeypatch):
        """`fail` 必须是「最终仍缺的标的数」，而非重试次数（旧实现会重复计数）。"""
        conn = _FakeConn([('2026-10-26',), (None, None)])
        responses = {
            'AAPL': [(1, 0, '2026-10-27')],
            'IBM': [(0, 0, None), (0, 0, None), (1, 0, '2026-10-27')],
            'WMT': [(0, 0, None)],
        }
        stats, _w, _f = self._run(conn, monkeypatch, responses, [False, False])
        assert stats['fail'] == 1            # 只有 WMT
        assert stats['retried'] >= 2

    def test_backfill_skipped_in_dry_run(self, monkeypatch):
        """dry-run 不落库、不清游标、不补漏（保持试运行语义）。"""
        conn = _FakeConn([])
        fake = _seq_import_one({'AAPL': [(0, 0, None)]})
        with patch.object(us, 'import_one', side_effect=fake), \
                patch.object(us, '_list_us_codes', return_value=['AAPL']), \
                patch.object(us, '_probe_src_latest', return_value='2026-10-27'):
            stats = us.run_incremental(_FakeSrc(US_CALENDAR), conn, dry_run=True)
        assert stats['fail'] == 1
        assert conn.cur.executed == []       # 未写游标
