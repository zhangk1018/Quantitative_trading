"""
test_snapshot_range.py - /api/snapshot/all 范围模式测试（协作单 40.0：回测按日期区间直查 OHLCV）

覆盖：
- start_date/end_date 传入时走范围模式（_load_ohlcv_range 直查 stock_quotes），trade_dates 覆盖区间
- 缺省（均未传）保持 300 天缓存路径，无回归
- 参数校验：无 codes / 日期格式错 / start>end / 区间超限
- 口径一致：无区间 K 线 / 无最新快照行的 code 跳过；market 过滤生效

运行（无需真实数据库，全部使用内存缓存桩）：
    cd backend && ../venv/bin/python -m pytest tests/test_snapshot_range.py -v
"""

import threading
import time
from datetime import date, datetime, timedelta

import pytest

from core.service.snapshot_service import SnapshotService


def _make_service() -> SnapshotService:
    """绕过 __init__（避免启动后台加载/定时线程），仅装配缓存与状态"""
    svc = SnapshotService.__new__(SnapshotService)
    svc._pool = None
    svc._ohlcv_cache = {}
    svc._snapshot_cache = {}
    svc._latest_trade_date = '2026-09-18'
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
        'trade_date': '2026-09-18', 'close': 10.0, 'change_pct': 1.0, 'market_cap': 1e9,
        'turnover_rate': 1.0, 'pe_ttm': 5.0, 'pb': 0.5,
        'ma5': 10.0, 'ma10': 10.0, 'ma20': 10.0, 'ma60': 10.0,
        'rsi_6': 50.0, 'rsi_12': 50.0, 'rsi_24': 50.0,
        'dif': 0.1, 'dea': 0.05, 'macd': 0.05,
        'boll_upper': 11.0, 'boll_mid': 10.0, 'boll_lower': 9.0,
        'is_macd_golden_cross': True, 'is_macd_dead_cross': False,
    }


def _bars(start: date, end: date, base_ts: float) -> list:
    """构造 [start, end] 区间逐日 K 线（bar 格式 [ts,o,h,l,c,v]）"""
    bars = []
    d = start
    ts = base_ts
    while d <= end:
        bars.append([ts, 10.0, 10.5, 9.5, 10.2, 1000.0])
        ts += 86400.0
        d += timedelta(days=1)
    return bars


class TestRangeMode:
    """协作单 40.0：start_date/end_date 传入时按区间直查 OHLCV"""

    def test_range_returns_ohlcv_and_trade_dates(self, monkeypatch):
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001'), '600000': _row('600000')}
        start = date(2025, 1, 1)
        end = date(2025, 1, 5)
        base_ts = datetime(2025, 1, 1).timestamp()
        monkeypatch.setattr(
            svc, '_load_ohlcv_range',
            lambda codes, s, e: {'000001': _bars(start, end, base_ts)},
        )
        result = svc.get_all_snapshot(codes=['000001'], start_date='2025-01-01', end_date='2025-01-05')
        assert result.total == 1
        assert result.stocks[0].code == '000001'
        # trade_dates 覆盖区间（5 个自然日 K 线）
        assert result.trade_dates == ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04', '2025-01-05']
        assert result.latest_trade_date == '2026-09-18'

    def test_range_only_start_date_ends_at_latest(self, monkeypatch):
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001')}
        start = date(2025, 1, 1)
        end = date(2026, 9, 18)
        base_ts = datetime(2025, 1, 1).timestamp()
        captured = {}
        def fake_load(codes, s, e):
            captured['start'], captured['end'] = s, e
            return {'000001': _bars(start, end, base_ts)}
        monkeypatch.setattr(svc, '_load_ohlcv_range', fake_load)
        svc.get_all_snapshot(codes=['000001'], start_date='2025-01-01')
        # end 缺省 = 最新交易日
        assert captured['end'] == date(2026, 9, 18)

    def test_default_path_no_range(self, monkeypatch):
        """缺省（不传日期）走 300 天缓存路径，不触发 _load_ohlcv_range"""
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001')}
        ts = datetime(2026, 9, 18).timestamp()
        svc._ohlcv_cache = {'000001': [[ts, 10.0, 10.5, 9.5, 10.2, 1000.0]]}
        called = []
        monkeypatch.setattr(svc, '_load_ohlcv_range', lambda *a, **kw: called.append(1) or {})
        result = svc.get_all_snapshot(codes=['000001'])
        assert called == []
        assert result.total == 1
        assert result.trade_dates == ['2026-09-18']

    def test_range_skips_no_ohlcv_code(self, monkeypatch):
        """区间内无 K 线的 code 跳过"""
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001'), '600000': _row('600000')}
        monkeypatch.setattr(
            svc, '_load_ohlcv_range',
            lambda codes, s, e: {'000001': _bars(date(2025, 1, 1), date(2025, 1, 2), datetime(2025, 1, 1).timestamp())},
        )
        result = svc.get_all_snapshot(codes=['000001', '600000'], start_date='2025-01-01', end_date='2025-01-05')
        assert result.total == 1
        assert result.stocks[0].code == '000001'

    def test_range_skips_no_snapshot_row(self, monkeypatch):
        """无最新快照行的 code 跳过（与缺省路径口径一致）"""
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001')}
        monkeypatch.setattr(
            svc, '_load_ohlcv_range',
            lambda codes, s, e: {
                '000001': _bars(date(2025, 1, 1), date(2025, 1, 2), datetime(2025, 1, 1).timestamp()),
                '999999': _bars(date(2025, 1, 1), date(2025, 1, 2), datetime(2025, 1, 1).timestamp()),
            },
        )
        result = svc.get_all_snapshot(codes=['000001', '999999'], start_date='2025-01-01', end_date='2025-01-05')
        assert result.total == 1

    def test_range_market_filter(self, monkeypatch):
        svc = _make_service()
        svc._snapshot_cache = {'000001': _row('000001')}
        monkeypatch.setattr(
            svc, '_load_ohlcv_range',
            lambda codes, s, e: {'000001': _bars(date(2025, 1, 1), date(2025, 1, 2), datetime(2025, 1, 1).timestamp())},
        )
        result = svc.get_all_snapshot(codes=['000001'], start_date='2025-01-01', end_date='2025-01-02', market='us')
        assert result.total == 0


class TestRangeValidation:
    """范围模式参数校验"""

    def test_range_requires_codes(self):
        svc = _make_service()
        with pytest.raises(ValueError, match='codes'):
            svc.get_all_snapshot(start_date='2025-01-01', end_date='2025-01-05')

    def test_range_invalid_date_format(self):
        svc = _make_service()
        with pytest.raises(ValueError, match='格式必须为 YYYY-MM-DD'):
            svc.get_all_snapshot(codes=['000001'], start_date='2025/01/01')

    def test_range_start_after_end(self):
        svc = _make_service()
        with pytest.raises(ValueError, match='不能晚于'):
            svc.get_all_snapshot(codes=['000001'], start_date='2025-02-01', end_date='2025-01-01')

    def test_range_exceeds_max_days(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(svc, '_load_ohlcv_range', lambda *a, **kw: {})
        with pytest.raises(ValueError, match='超过上限'):
            svc.get_all_snapshot(codes=['000001'], start_date='2020-01-01', end_date='2026-09-18')
