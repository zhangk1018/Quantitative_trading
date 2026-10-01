"""
test_snapshot_market_date.py - 快照按各市场"各自最新交易日"加载测试（协作单 43.0）

背景：此前 `_query_meta` 取 stock_daily_snapshot 全表单一 `MAX(trade_date)`，
`_load_from_db` / `_load_raw_data` 用「等值日期」过滤加载快照。于是「最新快照日
≠ 全局 latest」的市场被整市剔除——美股任务次日 08:30 才跑天然滞后一天、A 股遇
节假日休市亦滞后，其自编指标选股 / 回测筛 0 只（表现为
`GET /api/snapshot/all?market=us` → `total=0`）。

修复：`_query_meta` 按 market 分组取各自最新日，加载查询改 CTE join 各市场最新日，
并新增 `_market_latest` 状态贯通缓存 / meta / 刷新。

注意：活库三市场日期已对齐（cn/hk/us 均为 2026-09-28），现场症状暂不复现，
故本文件用假连接**构造**「各市场最新日不一致」场景来证明修复有效。

运行（无需真实数据库，全部使用内存缓存桩）：
    cd backend && ../venv/bin/python -m pytest tests/test_snapshot_market_date.py -v
"""

import json
import logging
import os
import threading
import time

import pytest

from core.service import snapshot_service as ss
from core.service.snapshot_service import SnapshotService

# 构造场景：cn/hk 最新 2026-09-28，us 滞后到 2026-09-25（美股次日 08:30 跑）
MKT_LATEST = {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-25'}


def _make_service() -> SnapshotService:
    """绕过 __init__（避免启动后台加载/定时线程），仅装配缓存与状态"""
    svc = SnapshotService.__new__(SnapshotService)
    svc._pool = None
    svc._ohlcv_cache = {}
    svc._snapshot_cache = {}
    svc._latest_trade_date = '2026-09-28'
    svc._market_latest = {}
    svc._cached_row_hash = 'stub'
    svc._ready = True
    svc._loading = False
    svc._load_error = None
    svc._last_check_time = time.time()
    svc._state_lock = threading.Lock()
    svc._reload_mutex = threading.Lock()
    # 隔离文件 IO：跳过 OHLCV 延迟加载
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


class FakeServerCursor:
    """服务端游标桩（OHLCV 流式读取）；本文件统一返回空集，只关心快照加载"""

    def __init__(self, rows):
        self._rows = list(rows)

    def execute(self, *args, **kwargs):
        pass

    def fetchmany(self, size):
        batch, self._rows = self._rows[:size], self._rows[size:]
        return batch

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeDictCursor:
    """RealDictCursor 桩：返回构造好的快照行（模拟 CTE join 各市场最新日的结果）"""

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
    def __init__(self, ohlcv_rows, snapshot_rows):
        self._ohlcv_rows = ohlcv_rows
        self._snapshot_rows = snapshot_rows

    def cursor(self, name=None, cursor_factory=None):
        if name:
            return FakeServerCursor(self._ohlcv_rows)
        return FakeDictCursor(self._snapshot_rows)


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        return self._conn

    def putconn(self, conn):
        pass


class TestDeriveMarketLatest:
    """_derive_market_latest：由已加载行反推各市场最新日"""

    def test_picks_max_per_market(self):
        rows = [
            _row('000001', 'cn', '2026-09-25'),
            _row('600000', 'cn', '2026-09-28'),
            _row('AAPL', 'us', '2026-09-25'),
        ]
        assert SnapshotService._derive_market_latest(rows) == {'cn': '2026-09-28', 'us': '2026-09-25'}

    def test_ignores_blank_market(self):
        """market 为 NULL/空的历史行不参与（与 _query_meta 的 WHERE market IS NOT NULL 一致）"""
        rows = [_row('000001', 'cn', '2026-09-28'), {'code': 'X', 'market': None, 'trade_date': '2026-09-28'}]
        assert SnapshotService._derive_market_latest(rows) == {'cn': '2026-09-28'}

    def test_empty_rows(self):
        assert SnapshotService._derive_market_latest([]) == {}


class TestLoadFromDbAllMarkets:
    """协作单 43.0 核心：各市场最新日不一致时，全部市场都要被加载（不整市剔除）"""

    def _load(self, monkeypatch, snapshot_rows):
        svc = _make_service()
        svc._pool = FakePool(FakeConn([], snapshot_rows))
        monkeypatch.setattr(svc, '_save_cache', lambda count: None)
        svc._load_from_db()
        return svc

    def test_lagging_market_is_still_loaded(self, monkeypatch):
        """us 滞后一天（9/25）仍被加载——旧实现用等值全局 latest 会整市剔除"""
        svc = self._load(monkeypatch, [
            _row('000001', 'cn', '2026-09-28'),
            _row('0700.HK', 'hk', '2026-09-28'),
            _row('AAPL', 'us', '2026-09-25'),
        ])
        assert set(svc._snapshot_cache.keys()) == {'000001', '0700.HK', 'AAPL'}
        assert svc._market_latest == MKT_LATEST

    def test_latest_trade_date_keeps_global_max(self, monkeypatch):
        """_latest_trade_date 语义保持全局最大值（供 OHLCV 窗口上界与 API 回显），不被滞后市场拉低"""
        svc = self._load(monkeypatch, [
            _row('000001', 'cn', '2026-09-28'),
            _row('AAPL', 'us', '2026-09-25'),
        ])
        assert svc._latest_trade_date == '2026-09-28'

    def test_holiday_regression_cn_still_loaded(self, monkeypatch):
        """节假日回归：A股休市滞后时，沪深标的仍被加载（对称场景）"""
        svc = self._load(monkeypatch, [
            _row('000001', 'cn', '2026-09-25'),
            _row('AAPL', 'us', '2026-09-28'),
        ])
        assert set(svc._snapshot_cache.keys()) == {'000001', 'AAPL'}
        assert svc._market_latest == {'cn': '2026-09-25', 'us': '2026-09-28'}


class TestGetAllSnapshotMarketFilter:
    """/api/snapshot/all?market=us 在缓存含美股行时不再返回 0"""

    def test_us_market_hits(self, monkeypatch):
        svc = _make_service()
        svc._snapshot_cache = {
            '000001': _row('000001', 'cn', '2026-09-28'),
            '0700.HK': _row('0700.HK', 'hk', '2026-09-28'),
            'AAPL': _row('AAPL', 'us', '2026-09-25'),
            'MU': _row('MU', 'us', '2026-09-25'),
        }
        svc._market_latest = MKT_LATEST
        ts = time.mktime(time.strptime('2026-09-25', '%Y-%m-%d'))
        svc._ohlcv_cache = {'AAPL': [[ts, 10.0, 10.5, 9.5, 10.2, 1000.0]],
                            'MU': [[ts, 10.0, 10.5, 9.5, 10.2, 1000.0]]}
        result = svc.get_all_snapshot(codes=['AAPL', 'MU'], market='us')
        assert result.total == 2
        assert {s.code for s in result.stocks} == {'AAPL', 'MU'}

    def test_warns_when_market_misses(self, caplog):
        """第 4 项防护：指定 market 且候选 codes 非空但命中 0 → WARN（异常显式化）"""
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001', 'cn', '2026-09-28')}
        svc._market_latest = {'cn': '2026-09-28'}
        with caplog.at_level(logging.WARNING):
            result = svc.get_all_snapshot(codes=['AAPL'], market='us')
        assert result.total == 0
        assert any('market=us' in r.getMessage() and '快照命中 0' in r.getMessage()
                   for r in caplog.records), caplog.text

    def test_no_warn_when_codes_absent(self, caplog):
        """未传 codes（全市场遍历）时不告警——全空是数据未就绪，不属该特征"""
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001', 'cn', '2026-09-28')}
        who = _make_service()
        who._snapshot_cache = {}
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            who.get_all_snapshot(market='us')
        assert not [r for r in caplog.records if '快照命中 0' in r.getMessage()]


class TestCacheMetaRoundTrip:
    """缓存 meta 往返一致：写入的 row_hash 与 _query_meta 计算的相同 → 不振荡重建"""

    def test_meta_hash_matches_query_meta(self, monkeypatch, tmp_path):
        # 重定向缓存文件到 tmp（避免污染 data/cache）
        monkeypatch.setattr(ss, 'CACHE_DIR', str(tmp_path))
        monkeypatch.setattr(ss, 'OHLCV_CACHE_FILE', str(tmp_path / 'ohlcv.pkl'))
        monkeypatch.setattr(ss, 'SNAPSHOT_CACHE_FILE', str(tmp_path / 'snapshot.pkl'))
        monkeypatch.setattr(ss, 'CACHE_META_FILE', str(tmp_path / 'cache_meta.json'))

        svc = _make_service()
        svc._snapshot_cache = {
            '000001': _row('000001', 'cn', '2026-09-28'),
            '0700.HK': _row('0700.HK', 'hk', '2026-09-28'),
            'AAPL': _row('AAPL', 'us', '2026-09-25'),
        }
        svc._market_latest = MKT_LATEST
        svc._latest_trade_date = '2026-09-28'
        svc._ohlcv_cache = {}
        count = 3

        # _save_cache 写入的 hash
        svc._save_cache(count)
        with open(ss.CACHE_META_FILE) as f:
            meta = json.load(f)
        assert meta['version'] == ss.CACHE_VERSION
        assert meta['market_latest'] == MKT_LATEST

        # 模拟 _query_meta 对同一批数据的结果（各市场最新日行数之和 = 3）
        expected_hash = SnapshotService._compute_row_hash(count, 3, MKT_LATEST)
        assert meta['row_count_hash'] == expected_hash
        # 缓存被判定有效（不振荡重建）
        assert svc._is_cache_valid('2026-09-28', expected_hash) is True
        # 任一行数 / 市场日期变化 → 立刻失效（下一轮刷新可触发）
        assert svc._is_cache_valid('2026-09-28', SnapshotService._compute_row_hash(count, 4, MKT_LATEST)) is False
        assert svc._is_cache_valid('2026-09-28', SnapshotService._compute_row_hash(
            count, 3, {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-28'})) is False

    def test_load_from_cache_restores_market_latest(self, monkeypatch, tmp_path):
        """_load_from_cache 回填 _market_latest，重启后按市场加载口径不丢失"""
        monkeypatch.setattr(ss, 'CACHE_DIR', str(tmp_path))
        monkeypatch.setattr(ss, 'OHLCV_CACHE_FILE', str(tmp_path / 'ohlcv.pkl'))
        monkeypatch.setattr(ss, 'SNAPSHOT_CACHE_FILE', str(tmp_path / 'snapshot.pkl'))
        monkeypatch.setattr(ss, 'CACHE_META_FILE', str(tmp_path / 'cache_meta.json'))

        writer = _make_service()
        writer._snapshot_cache = {'AAPL': _row('AAPL', 'us', '2026-09-25')}
        writer._market_latest = {'us': '2026-09-25'}
        writer._latest_trade_date = '2026-09-25'
        writer._save_cache(1)

        reader = _make_service()
        reader._load_from_cache()
        assert reader._market_latest == {'us': '2026-09-25'}
        assert reader._latest_trade_date == '2026-09-25'
        assert 'AAPL' in reader._snapshot_cache