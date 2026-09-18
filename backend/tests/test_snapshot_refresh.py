"""
test_snapshot_refresh.py - 快照服务热切换/独立定时刷新/codes 索引测试（协作单 39.0）

覆盖：
- 修复① 刷新期间 _ready 保持 True（双缓存热切换，旧缓存持续服务，不再 503）
- 修复② 请求路径不再触发 _refresh_if_needed（独立后台定时刷新替代）
- 修复③ get_all_snapshot / get_incremental_snapshot 按 codes 哈希索引只返回指定股票（O(K)）

运行（无需真实数据库，全部使用内存缓存桩）：
    cd backend && ../venv/bin/python -m pytest tests/test_snapshot_refresh.py -v
"""

import threading
import time
from datetime import datetime

from core.service.snapshot_service import SnapshotService


def _make_service() -> SnapshotService:
    """绕过 __init__（避免启动后台加载/定时线程），仅装配缓存与状态"""
    svc = SnapshotService.__new__(SnapshotService)
    svc._pool = None
    svc._ohlcv_cache = {}
    svc._snapshot_cache = {}
    svc._latest_trade_date = '2026-09-11'
    svc._cached_row_hash = 'stub'
    svc._ready = True
    svc._loading = False
    svc._load_error = None
    svc._last_check_time = time.time()
    svc._state_lock = threading.Lock()
    svc._reload_mutex = threading.Lock()
    return svc


def _row(code: str) -> dict:
    return {
        'stock_name': f'股票{code}', 'listed_board': 'main_board', 'industry': '银行',
        'trade_date': '2026-09-11', 'close': 10.0, 'change_pct': 1.0, 'market_cap': 1e9,
        'turnover_rate': 1.0, 'pe_ttm': 5.0, 'pb': 0.5,
        'ma5': 10.0, 'ma10': 10.0, 'ma20': 10.0, 'ma60': 10.0,
        'rsi_6': 50.0, 'rsi_12': 50.0, 'rsi_24': 50.0,
        'dif': 0.1, 'dea': 0.05, 'macd': 0.05,
        'boll_upper': 11.0, 'boll_mid': 10.0, 'boll_lower': 9.0,
        'is_macd_golden_cross': True, 'is_macd_dead_cross': False,
    }


def _ohlcv(code: str) -> list:
    ts = datetime(2026, 9, 11).timestamp()
    return [[ts, 10.0, 10.5, 9.5, 10.2, 1000.0]]


def _seed(svc: SnapshotService) -> None:
    svc._snapshot_cache = {'000001': _row('000001'), '600000': _row('600000')}
    svc._ohlcv_cache = {'000001': _ohlcv('000001'), '600000': _ohlcv('600000')}


class TestRefreshHotSwitch:
    """修复①：刷新期间 _ready 保持 True，旧缓存持续服务（不再 503）"""

    def test_refresh_keeps_ready_true(self, monkeypatch):
        svc = _make_service()
        svc._last_check_time = 0  # 强制进入检查
        monkeypatch.setattr(svc, '_is_etl_window', lambda: False)
        monkeypatch.setattr(svc, '_query_meta', lambda: ('2026-09-12', 'new_hash', 100))
        # 打桩异步刷新入口（不真正加载数据），验证线程被调度
        reloaded = []
        monkeypatch.setattr(svc, '_reload_async', lambda: reloaded.append(1))

        svc._refresh_if_needed()

        time.sleep(0.2)  # 等待后台线程执行
        assert reloaded == [1]     # 刷新线程已启动
        assert svc._loading is True
        # 关键断言：刷新期间 _ready 保持 True，_ensure_ready 不再抛 503
        assert svc._ready is True

    def test_no_change_keeps_state(self, monkeypatch):
        svc = _make_service()
        svc._last_check_time = 0
        monkeypatch.setattr(svc, '_is_etl_window', lambda: False)
        monkeypatch.setattr(
            svc, '_query_meta',
            lambda: (svc._latest_trade_date, svc._cached_row_hash, 100),
        )
        svc._refresh_if_needed()
        assert svc._ready is True
        assert svc._loading is False

    def test_etl_window_skips_check(self, monkeypatch):
        """ETL 窗口避让：不检查不刷新"""
        svc = _make_service()
        svc._last_check_time = 0
        monkeypatch.setattr(svc, '_is_etl_window', lambda: True)
        monkeypatch.setattr(svc, '_query_meta', lambda: ('2026-09-12', 'new_hash', 100))
        svc._refresh_if_needed()
        assert svc._loading is False


class TestRequestPathNoRefresh:
    """修复②：请求路径只读缓存，不再触发 _refresh_if_needed（独立定时刷新替代）"""

    def test_get_all_does_not_trigger_refresh(self, monkeypatch):
        svc = _make_service()
        _seed(svc)
        called = []
        monkeypatch.setattr(svc, '_refresh_if_needed', lambda: called.append(1))
        svc.get_all_snapshot(codes=['000001'])
        assert called == []

    def test_incremental_does_not_trigger_refresh(self, monkeypatch):
        svc = _make_service()
        _seed(svc)
        called = []
        monkeypatch.setattr(svc, '_refresh_if_needed', lambda: called.append(1))
        svc.get_incremental_snapshot(since='2026-09-10', codes=['000001'])
        assert called == []

    def test_latest_trade_date_does_not_trigger_refresh(self, monkeypatch):
        svc = _make_service()
        called = []
        monkeypatch.setattr(svc, '_refresh_if_needed', lambda: called.append(1))
        _ = svc.latest_trade_date
        assert called == []


class TestCodesIndex:
    """修复③：按 codes 哈希索引直接读取（O(K)），只返回指定股票"""

    def test_get_all_codes_filter(self):
        svc = _make_service()
        _seed(svc)
        result = svc.get_all_snapshot(codes=['000001'])
        assert result.total == 1
        assert result.stocks[0].code == '000001'

    def test_get_all_codes_unknown_ignored(self):
        svc = _make_service()
        _seed(svc)
        result = svc.get_all_snapshot(codes=['999999'])
        assert result.total == 0

    def test_get_all_market_filter_applied(self):
        svc = _make_service()
        _seed(svc)
        # 000001 推断为 cn，传 market=cn 命中；600000 同为 cn
        result = svc.get_all_snapshot(codes=['000001', '600000'], market='cn')
        assert result.total == 2

    def test_get_incremental_codes_filter(self):
        svc = _make_service()
        _seed(svc)
        result = svc.get_incremental_snapshot(since='2026-09-10', codes=['600000'])
        assert len(result.stocks) == 1
        assert result.stocks[0].code == '600000'
