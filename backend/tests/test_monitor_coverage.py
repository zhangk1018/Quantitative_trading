"""分市场监控看板「日线覆盖度残日检测」测试。

背景：港股增量在缺失一天后走进逐只路径（`stock_hk_daily`），新浪逐只历史序列会省略
无成交日，当日覆盖标的数从快照路径的 ~2650 骤降至 ~2100（约 80%），但任务链每一步仍
写入 success，肉眼无从察觉（实测 2026-09-25=2093、2026-09-28=2184，正常日 2648~2664）。

为此在 `/api/monitor/market-chain/` 增加 `coverage` 字段：当日 `stock_quotes`
覆盖标的数 vs 近 20 个交易日中位数，比值跌破 90% 即告警，供看板汇总横条显式展示。

全部用例使用假连接/假游标，不访问网络与数据库。

2026-09-29 创建
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import pytest

# 保证 `core.* / shared.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.api.router import monitor as mod  # noqa: E402


class _FakeCursor:
    """假游标：预置结果集，支持 `with` 上下文（psycopg2 风格）。"""

    def __init__(self, rows: Sequence[Tuple[Any, ...]], error: Optional[Exception] = None):
        self._rows = list(rows)
        self._error = error
        self.executed: List[Tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        if self._error is not None:
            raise self._error

    def fetchall(self) -> List[Tuple[Any, ...]]:
        return self._rows

    def close(self) -> None:
        pass

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False


class _FakeConn:
    """假连接：按 cursor() 调用顺序依次返回各结果集。"""

    def __init__(self, result_sets: List[Sequence[Tuple[Any, ...]]],
                 error: Optional[Exception] = None):
        self._result_sets = list(result_sets)
        self._error = error
        self.cursors: List[_FakeCursor] = []

    def cursor(self) -> _FakeCursor:
        rows = self._result_sets.pop(0) if self._result_sets else []
        cur = _FakeCursor(rows, error=self._error if not self.cursors else None)
        self.cursors.append(cur)
        return cur


def _rows(counts: List[int], start_day: int = 28) -> List[Tuple[Any, ...]]:
    """按「日期倒序」构造 (trade_date, cnt) 序列，日期仅为占位字符串。"""
    return [(f"2026-09-{start_day:02d}", c) for c in counts]


class TestMarketQuotesCoverage:
    """`_market_quotes_coverage` 单元测试。"""

    def test_normal_day_no_alert(self):
        """覆盖数与中位数持平 → 不告警、绿色。"""
        conn = _FakeConn([_rows([2650] + [2650] * 20)])

        r = mod._market_quotes_coverage(conn, 'hk')

        assert r['count'] == 2650
        assert r['baseline_median'] == 2650.0
        assert r['baseline_days'] == 20
        assert r['ratio'] == 100.0
        assert r['alert'] is False
        assert r['level'] == 'green'
        assert '正常' in r['message']

    def test_residual_day_alerts(self):
        """逐只路径残日（2184 vs 中位数 2650 ≈ 82.4%）→ 告警、红色。"""
        conn = _FakeConn([_rows([2184] + [2650] * 20)])

        r = mod._market_quotes_coverage(conn, 'hk')

        assert r['count'] == 2184
        assert r['ratio'] == 82.4
        assert r['alert'] is True
        assert r['level'] == 'red'
        assert '疑似残缺' in r['message']
        assert '2184' in r['message']

    def test_threshold_boundary_not_alert(self):
        """恰好等于阈值（90%）不告警（判据为严格小于）。"""
        conn = _FakeConn([_rows([1800] + [2000] * 20)])

        r = mod._market_quotes_coverage(conn, 'us')

        assert r['ratio'] == 90.0
        assert r['alert'] is False

    def test_just_below_threshold_alerts(self):
        """略低于阈值（89.9%）即告警。"""
        conn = _FakeConn([_rows([1798] + [2000] * 20)])

        r = mod._market_quotes_coverage(conn, 'us')

        assert r['ratio'] == 89.9
        assert r['alert'] is True

    def test_insufficient_history_no_alert(self):
        """可比历史不足 5 天 → 不判定残日，仅回显当日覆盖数。"""
        conn = _FakeConn([_rows([2184, 2650, 2650])])

        r = mod._market_quotes_coverage(conn, 'hk')

        assert r['count'] == 2184
        assert r['baseline_median'] is None
        assert r['ratio'] is None
        assert r['alert'] is False
        assert '不足以判定' in r['message']

    def test_empty_rows_returns_placeholder(self):
        """无日线数据 → 占位返回，不抛异常。"""
        conn = _FakeConn([[]])

        r = mod._market_quotes_coverage(conn, 'us')

        assert r['count'] is None
        assert r['alert'] is False, '无数据不应误报告警'
        assert r['message'] == '暂无日线数据'

    def test_query_error_swallowed(self):
        """查询异常 → 降级为占位返回（监控端点不应整体 500）。"""
        conn = _FakeConn([[]], error=RuntimeError('db down'))

        r = mod._market_quotes_coverage(conn, 'hk')

        assert r['count'] is None
        assert r['alert'] is False

    def test_lookback_passed_to_sql(self):
        """LIMIT 取 lookback + 1（多取一行用于排除当日再算中位数）。"""
        conn = _FakeConn([_rows([2650] * 6)])

        mod._market_quotes_coverage(conn, 'hk', lookback=5)

        sql, params = conn.cursors[0].executed[0]
        assert params == ('hk', 'hk', 10, 6), '窗口取 lookback×2 自然日，LIMIT 取 lookback+1'

    def test_threshold_override_reported(self):
        """自定义阈值应回显在 threshold 字段（百分比）。"""
        conn = _FakeConn([_rows([1800] + [2000] * 20)])

        r = mod._market_quotes_coverage(conn, 'hk', threshold=0.95)

        assert r['threshold'] == 95.0
        assert r['alert'] is True

    def test_in_progress_suppresses_alert(self):
        """导入运行中：覆盖数正从 0 逐只增长，低覆盖属过程态，不告警（否则每日跑批必假报）。"""
        conn = _FakeConn([_rows([71] + [205] * 20)])

        r = mod._market_quotes_coverage(conn, 'us', in_progress=True)

        assert r['count'] == 71
        assert r['ratio'] == 34.6
        assert r['alert'] is False
        assert '导入进行中' in r['message']

    def test_in_progress_keeps_normal_message(self):
        """导入运行中但覆盖已正常 → 仍显示正常文案，不误加「进行中」。"""
        conn = _FakeConn([_rows([205] + [205] * 20)])

        r = mod._market_quotes_coverage(conn, 'us', in_progress=True)

        assert r['alert'] is False
        assert '正常' in r['message']
        assert '导入进行中' not in r['message']


class TestMarketChainIncludesCoverage:
    """`get_market_chain` 需把覆盖度连同任务链一并返回。"""

    def test_coverage_field_present(self, monkeypatch: pytest.MonkeyPatch):
        conn = _FakeConn([
            [('hk:股票列表', 'success', None, '2026-09-28', '2026-09-28 18:30:00')],
            _rows([2184] + [2650] * 20),
        ])
        monkeypatch.setattr(mod, '_get_db_conn', lambda: conn)
        monkeypatch.setattr(mod, '_put_db_conn', lambda c: None)
        monkeypatch.setattr(mod, '_check_task_from_db',
                            lambda *a, **k: {'status': 'success', 'message': 'ok',
                                             'data_count': 1, 'data_date': '2026-09-28'})

        resp = mod.get_market_chain(market='hk')

        assert resp.code == 200
        cov = resp.data['coverage']
        assert cov['count'] == 2184
        assert cov['alert'] is True
        assert resp.data['market'] == 'hk'
        assert resp.data['tasks'], '任务链不应因新增覆盖度字段而丢失'

    def test_running_chain_suppresses_alert(self, monkeypatch: pytest.MonkeyPatch):
        """任务链运行中（日线导入尚未跑完）→ 覆盖度只展示不告警，避免跑批期间天天假报。"""
        conn = _FakeConn([
            [('us:日线清洗', 'running', None, '2026-09-28', datetime.now())],
            _rows([71] + [205] * 20),
        ])
        monkeypatch.setattr(mod, '_get_db_conn', lambda: conn)
        monkeypatch.setattr(mod, '_put_db_conn', lambda c: None)
        monkeypatch.setattr(mod, '_check_task_from_db',
                            lambda *a, **k: {'status': 'pending', 'message': '',
                                             'data_count': None, 'data_date': None})

        resp = mod.get_market_chain(market='us')

        assert resp.data['overall'] == 'running'
        cov = resp.data['coverage']
        assert cov['alert'] is False
        assert '导入进行中' in cov['message']
