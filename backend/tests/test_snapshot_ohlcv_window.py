"""
test_snapshot_ohlcv_window.py - 缺省路径 OHLCV 缓存窗口测试（协作单 44.0）

背景：`/api/snapshot/all` 缺省路径的 OHLCV 窗口原为「全局 latest 倒推 300 自然日」，
各市场实际只覆盖 cn 196 / hk 201 / us 205 个交易日，导致含 `ema(close,200)` /
`if n >= 200:` 的长周期自编指标在沪深永不生效（196 < 200）而港美股生效 →
同一指标跨市场结果不可比。

修复：
1. `OHLCV_HISTORY_DAYS` 300→450 自然日（实测 cn 298 / hk 306 / us 311 个交易日，均 ≥250）；
2. 窗口下界基准改用各市场最新日的**最小值**（`_ohlcv_window_bounds`），
   滞后市场（美股 T+1 08:30 才落库、A 股节假日休市）不再被领先市场截短；
3. `_query_meta` 的计数与 `_load_from_db` / `_load_raw_data` 的加载查询同参数，
   保证 `row_hash` 与缓存内容口径一致（不振荡重建）。

覆盖：
- `_ohlcv_window_bounds`：下界基准 = min(各市场 latest)，上界 = latest；空映射回退
- `_query_meta` / `_load_from_db` / `_load_raw_data` 三处查询参数一致（下界基准 + 窗口长度）
- 窗口长度回归护栏：不得低于单内要求的 450 自然日

运行（无需真实数据库，全部使用游标桩）：
    cd backend && ../venv/bin/python -m pytest tests/test_snapshot_ohlcv_window.py -v
"""

import threading
import time

import pytest

from core.service import snapshot_service as ss
from core.service.snapshot_service import SnapshotService

# 构造「各市场最新日不一致」场景（美股 T+1 滞后一天）
MKT_LATEST = {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-25'}
EXPECTED_PARAMS = ('2026-09-25', f'{ss.OHLCV_HISTORY_DAYS} days', '2026-09-28')


def _make_service(market_latest=None) -> SnapshotService:
    """绕过 __init__（避免启动后台加载/定时线程），仅装配缓存与状态"""
    svc = SnapshotService.__new__(SnapshotService)
    svc._pool = None
    svc._ohlcv_cache = {}
    svc._snapshot_cache = {}
    svc._latest_trade_date = '2026-09-28'
    svc._market_latest = dict(market_latest if market_latest is not None else MKT_LATEST)
    svc._cached_row_hash = 'stub'
    svc._ready = True
    svc._loading = False
    svc._load_error = None
    svc._last_check_time = time.time()
    svc._state_lock = threading.Lock()
    svc._reload_mutex = threading.Lock()
    svc._ensure_ohlcv_loaded = lambda: None
    return svc


def _row(code: str, market: str, trade_date: str) -> dict:
    return {
        'code': code, 'market': market, 'trade_date': trade_date,
        'stock_name': f'股票{code}', 'listed_board': 'main_board', 'industry': '银行',
        'close': 10.0, 'change_pct': 1.0, 'market_cap': 1e9, 'turnover_rate': 1.0,
        'pe_ttm': 5.0, 'pb': 0.5,
        'ma5': 10.0, 'ma10': 10.0, 'ma20': 10.0, 'ma60': 10.0,
        'rsi_6': 50.0, 'rsi_12': 50.0, 'rsi_24': 50.0,
        'dif': 0.1, 'dea': 0.05, 'macd': 0.05,
        'boll_upper': 11.0, 'boll_mid': 10.0, 'boll_lower': 9.0,
        'is_macd_golden_cross': True, 'is_macd_dead_cross': False,
    }


class TestWindowBounds:
    """`_ohlcv_window_bounds`：下界基准取各市场最新日的最小值"""

    def test_lower_base_is_min_of_markets(self):
        assert SnapshotService._ohlcv_window_bounds('2026-09-28', MKT_LATEST) == \
            ('2026-09-25', '2026-09-28')

    def test_aligned_markets(self):
        """各市场日期已对齐时，下界基准 = 上界 = 最新日"""
        aligned = {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-28'}
        assert SnapshotService._ohlcv_window_bounds('2026-09-28', aligned) == \
            ('2026-09-28', '2026-09-28')

    def test_holiday_cn_lagging(self):
        """对称场景：A 股节假日休市滞后（cn 9/25、us 9/28）→ 下界基准取 cn"""
        lag = {'cn': '2026-09-25', 'hk': '2026-09-25', 'us': '2026-09-28'}
        assert SnapshotService._ohlcv_window_bounds('2026-09-28', lag) == \
            ('2026-09-25', '2026-09-28')

    @pytest.mark.parametrize('market_latest', [None, {}, {'cn': None}])
    def test_empty_market_latest_falls_back_to_latest(self, market_latest):
        """`_market_latest` 缺失（旧 meta 回退 / 加载早期）时退化为原全局 latest 口径"""
        assert SnapshotService._ohlcv_window_bounds('2026-09-28', market_latest) == \
            ('2026-09-28', '2026-09-28')

    def test_strips_time_component(self):
        """值带时间部分时取前 10 位（SQL 侧统一 CAST AS DATE）"""
        ml = {'cn': '2026-09-28 00:00:00', 'us': '2026-09-25 00:00:00'}
        assert SnapshotService._ohlcv_window_bounds('2026-09-28 00:00:00', ml) == \
            ('2026-09-25', '2026-09-28 00:00:00')


class TestWindowConstant:
    """窗口长度回归护栏：不得低于单内要求的 450 自然日（≈≥250 个交易日）"""

    def test_window_covers_at_least_250_trading_days(self):
        assert ss.OHLCV_HISTORY_DAYS >= 450

    def test_range_mode_default_days_unchanged(self):
        """范围模式（协作单 40.0）缺省回看自然天保持 300，不受本单影响"""
        assert ss.HISTORY_DAYS == 300


class RecordingCursor:
    """普通游标桩：记录 (sql, params)，按 `_query_meta` 顺序返回快照 CTE / OHLCV 计数"""

    def __init__(self, market_rows, ohlcv_count):
        self._market_rows = market_rows
        self._ohlcv_count = ohlcv_count
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self._market_rows

    def fetchone(self):
        return (self._ohlcv_count,)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RecordingServerCursor:
    """服务端游标桩：记录 OHLCV 流式查询的 (sql, params)，返回空集"""

    def __init__(self, rows=()):
        self._rows = list(rows)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchmany(self, size):
        batch, self._rows = self._rows[:size], self._rows[size:]
        return batch

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DictCursorStub:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, server_cursor=None, snapshot_rows=(), plain_cursor=None):
        self._server_cursor = server_cursor
        self._snapshot_rows = list(snapshot_rows)
        self._plain_cursor = plain_cursor

    def cursor(self, name=None, cursor_factory=None):
        if name:
            return self._server_cursor
        if self._plain_cursor is not None:
            return self._plain_cursor
        return DictCursorStub(self._snapshot_rows)


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        return self._conn

    def putconn(self, conn):
        pass


def _ohlcv_sql_call(calls):
    """从记录中挑出 OHLCV 查询（含 ORDER BY code, trade_date 的 stock_quotes 流式查询）"""
    matched = [(sql, params) for sql, params in calls if 'EXTRACT(EPOCH FROM trade_date)' in sql]
    assert len(matched) == 1, calls
    return matched[0]


class TestQueryWindowParams:
    """三处查询点使用同一窗口参数（下界基准 + OHLCV_HISTORY_DAYS + 上界）"""

    def test_query_meta_count_uses_same_window(self):
        cursor = RecordingCursor(
            [('cn', '2026-09-28', 5210), ('hk', '2026-09-28', 2184), ('us', '2026-09-25', 205)],
            12345,
        )
        svc = _make_service()
        svc._pool = FakePool(FakeConn(plain_cursor=cursor))
        latest, row_hash, count, market_latest = svc._query_meta()
        assert latest == '2026-09-28'
        assert count == 12345
        # calls[0] = 快照 CTE；calls[1] = OHLCV 计数
        sql, params = cursor.calls[1]
        assert 'COUNT(*)' in sql and 'stock_quotes' in sql
        assert params == EXPECTED_PARAMS
        # 与加载侧 save_cache 口径一致
        assert row_hash == SnapshotService._compute_row_hash(
            12345, 5210 + 2184 + 205, market_latest)

    def test_load_from_db_uses_same_window(self):
        ohlcv_cursor = RecordingServerCursor()
        svc = _make_service()
        svc._pool = FakePool(FakeConn(
            server_cursor=ohlcv_cursor,
            snapshot_rows=[_row('000001', 'cn', '2026-09-28'), _row('AAPL', 'us', '2026-09-25')],
        ))
        svc._save_cache = lambda count: None
        svc._load_from_db()
        _, params = _ohlcv_sql_call(ohlcv_cursor.calls)
        assert params == EXPECTED_PARAMS

    def test_load_raw_data_uses_same_window(self):
        ohlcv_cursor = RecordingServerCursor()
        svc = _make_service()
        svc._pool = FakePool(FakeConn(
            server_cursor=ohlcv_cursor,
            snapshot_rows=[
                _row('000001', 'cn', '2026-09-28'),
                _row('0700.HK', 'hk', '2026-09-28'),
                _row('AAPL', 'us', '2026-09-25'),
            ],
        ))
        ohlcv, snapshot, market_latest = svc._load_raw_data('2026-09-28', MKT_LATEST)
        _, params = _ohlcv_sql_call(ohlcv_cursor.calls)
        assert params == EXPECTED_PARAMS
        assert market_latest == MKT_LATEST

    def test_load_raw_data_without_market_latest_falls_back(self):
        """未传 `_market_latest`（旧调用）时退化为全局 latest 口径，不抛错"""
        ohlcv_cursor = RecordingServerCursor()
        svc = _make_service()
        svc._pool = FakePool(FakeConn(
            server_cursor=ohlcv_cursor,
            snapshot_rows=[_row('000001', 'cn', '2026-09-28')],
        ))
        svc._load_raw_data('2026-09-28')
        _, params = _ohlcv_sql_call(ohlcv_cursor.calls)
        assert params == ('2026-09-28', f'{ss.OHLCV_HISTORY_DAYS} days', '2026-09-28')
