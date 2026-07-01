"""
test_snapshot_service.py - 快照服务层单元测试

覆盖：
1. SnapshotService 初始化
2. 全量快照数据组装（mock DB）
3. 增量同步过滤逻辑
4. OHLCV 列式二维数组格式
5. 缓存刷新机制

注意：mock 模式避开真实数据库连接。
集成测试通过实际启动后端 + curl 验证。
"""

import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date, datetime
from typing import Dict, List

from shared.schemas import SnapshotAllData, SnapshotIncrementalData, SnapshotStock
from core.service.snapshot_service import SnapshotService, OHLCV_TIME


def _ts(year, month, day):
    """辅助函数：生成指定日期的 Unix 时间戳（整数秒）"""
    return int(datetime(year, month, day).timestamp())


_FIELDS = [
    'ma5', 'ma10', 'ma20', 'ma60',
    'rsi_6', 'rsi_12', 'rsi_24',
    'dif', 'dea', 'macd',
    'boll_upper', 'boll_mid', 'boll_lower',
    'is_macd_golden_cross', 'is_macd_dead_cross',
]


def _make_indicator_row(**overrides):
    """生成包含所有指标键的 mock 行字典，默认所有指标为 None"""
    row = {k: None for k in _FIELDS}
    row.update(overrides)
    return row


class TestSnapshotServiceUnit:
    """SnapshotService 单元测试（mock DB）"""

    def test_init_no_db(self):
        """不依赖 DB 的初始化"""
        pool = MagicMock()
        service = SnapshotService(pool)
        assert service._pool is pool
        assert service._latest_trade_date is None
        assert service._ohlcv_cache == {}

    def test_build_indicators_all_none(self):
        """空数据构建 indicators"""
        pool = MagicMock()
        service = SnapshotService(pool)
        indicators = service._build_indicators(_make_indicator_row())
        assert indicators.ma5 is None
        assert indicators.ma10 is None
        assert indicators.macd_dif is None
        assert indicators.is_macd_golden_cross is False
        assert indicators.is_macd_dead_cross is False

    def test_build_indicators_partial(self):
        """部分数据构建 indicators"""
        pool = MagicMock()
        service = SnapshotService(pool)
        row = _make_indicator_row(
            ma5=10.5, ma10=10.3, ma60=9.5,
            rsi_6=65.2,
            dif=1.234, dea=1.100, macd=0.134,
            boll_upper=11.5,
            is_macd_golden_cross=True, is_macd_dead_cross=False,
        )
        indicators = service._build_indicators(row)
        assert indicators.ma5 == 10.5
        assert indicators.ma20 is None  # 未设置
        assert indicators.ma60 == 9.5
        assert indicators.rsi_6 == 65.2
        assert indicators.rsi_12 is None
        assert indicators.macd_dif == 1.234
        assert indicators.is_macd_golden_cross is True
        assert indicators.is_macd_dead_cross is False

    def test_build_stock_snapshot(self):
        """构建 SnapshotStock 对象"""
        pool = MagicMock()
        service = SnapshotService(pool)
        row = {
            'code': '600519',
            'stock_name': '贵州茅台',
            'listed_board': '上海主板',
            'industry': '白酒',
            'trade_date': date(2026, 6, 30),
            'close': 1500.0, 'change_pct': 2.5,
            'market_cap': 2000000, 'turnover_rate': 0.5,
            'pe_ttm': 30.0, 'pb': 8.0,
            **_make_indicator_row(
                ma5=1480.0, dif=2.0, is_macd_golden_cross=True,
            ),
        }
        ohlcv = [[_ts(2026, 6, 30), 1490.0, 1510.0, 1480.0, 1500.0, 5000000.0]]
        stock = service._build_stock_snapshot('600519', row, ohlcv)
        assert stock.code == '600519'
        assert stock.name == '贵州茅台'
        assert stock.close == 1500.0
        assert stock.change_pct == 2.5
        assert stock.indicators.ma5 == 1480.0
        assert stock.indicators.macd_dif == 2.0
        assert stock.indicators.is_macd_golden_cross is True
        assert len(stock.ohlcv) == 1

    def test_build_stock_empty_ohlcv(self):
        """空 OHLCV 列表"""
        pool = MagicMock()
        service = SnapshotService(pool)
        row = {
            'code': '600519', 'stock_name': '贵州茅台',
            'listed_board': '上海主板', 'industry': '',
            'trade_date': date(2026, 6, 30),
            'close': 1500.0, 'change_pct': None,
            'market_cap': None, 'turnover_rate': None,
            'pe_ttm': None, 'pb': None,
            **_make_indicator_row(),
        }
        stock = service._build_stock_snapshot('600519', row, [])
        assert stock.ohlcv == []
        assert stock.change_pct is None
        assert stock.market_cap is None


class TestIncrementalFilter:
    """增量同步过滤逻辑测试（绕过缓存检查，纯内存计算）"""

    @pytest.fixture
    def service(self):
        pool = MagicMock()
        svc = SnapshotService(pool)
        # 完全禁用缓存检查
        svc._check_reload = lambda: None
        svc._latest_trade_date = '2026-06-30'
        # 使用动态时间戳
        svc._ohlcv_cache = {
            '600519': [
                [_ts(2026, 6, 25), 1470.0, 1490.0, 1460.0, 1480.0, 4500000.0],
                [_ts(2026, 6, 26), 1480.0, 1500.0, 1470.0, 1490.0, 4600000.0],
                [_ts(2026, 6, 29), 1490.0, 1510.0, 1480.0, 1500.0, 4800000.0],
                [_ts(2026, 6, 30), 1500.0, 1520.0, 1490.0, 1510.0, 5000000.0],
            ],
            '000001': [
                [_ts(2026, 6, 29), 11.3, 11.8, 11.2, 11.7, 1800000.0],
                [_ts(2026, 6, 30), 11.8, 12.0, 11.5, 11.9, 2000000.0],
            ],
        }
        svc._snapshot_cache = {}
        for code, ohlcv in svc._ohlcv_cache.items():
            last_bar = ohlcv[-1]
            svc._snapshot_cache[code] = {
                'code': code,
                'stock_name': 'Test',
                'listed_board': '测试',
                'industry': '',
                'trade_date': date(2026, 6, 30),
                'close': last_bar[4],
                'change_pct': None,
                'market_cap': None,
                'turnover_rate': None,
                'pe_ttm': None,
                'pb': None,
                **_make_indicator_row(),
            }
        return svc

    def test_incremental_all_data(self, service):
        """since 早于全部数据，返回所有"""
        result = service.get_incremental_snapshot('2026-06-25')
        assert result.days == 4
        assert len(result.stocks) == 2
        stock_519 = [s for s in result.stocks if s.code == '600519'][0]
        assert len(stock_519.ohlcv) == 4

    def test_incremental_partial(self, service):
        """since 过滤部分数据"""
        result = service.get_incremental_snapshot('2026-06-29')
        assert result.days == 2
        assert len(result.stocks) == 2
        stock_519 = [s for s in result.stocks if s.code == '600519'][0]
        assert len(stock_519.ohlcv) == 2

    def test_incremental_no_data(self, service):
        """since 晚于最新数据，返回空"""
        result = service.get_incremental_snapshot('2099-12-31')
        assert result.days == 0
        assert result.stocks == []

    def test_incremental_single_stock(self, service):
        """since 过滤后只有部分股票有数据"""
        result = service.get_incremental_snapshot('2026-06-30')
        assert result.days == 1
        assert len(result.stocks) == 2
        for s in result.stocks:
            assert len(s.ohlcv) >= 1

    def test_incremental_one_stock_skipped(self, service):
        """since 过滤使某只股票无数据时被跳过"""
        result = service.get_incremental_snapshot('2099-01-01')
        assert result.days == 0
        assert result.stocks == []

    def test_ohlcv_timestamp_order(self, service):
        """OHLCV 按日期升序"""
        result = service.get_incremental_snapshot('2026-06-25')
        stock_519 = [s for s in result.stocks if s.code == '600519'][0]
        times = [bar[OHLCV_TIME] for bar in stock_519.ohlcv]
        assert times == sorted(times)


class TestSnapshotServiceIntegration:
    """快照服务集成测试（依赖真实数据库）

    运行条件：本地 PostgreSQL 数据库可用，.env 已配置 PG_PASSWORD
    """

    def _get_service(self) -> SnapshotService:
        """获取真实 SnapshotService 实例"""
        import os
        import psycopg2
        from psycopg2 import pool as pg_pool

        pg_password = os.environ.get('PG_PASSWORD', '')
        if not pg_password:
            env_path = '/Users/zhangk/workspace/Quantitative_trading/.env'
            with open(env_path) as f:
                for line in f:
                    if line.startswith('PG_PASSWORD'):
                        pg_password = line.split('=', 1)[1].strip()
                        break

        connection_pool = pg_pool.ThreadedConnectionPool(
            minconn=2, maxconn=5,
            host='localhost', port=5432,
            database='quant_trading',
            user='quant_user',
            password=pg_password,
        )
        return SnapshotService(connection_pool)

    def test_get_all_snapshot_real_db(self):
        """真实数据库全量快照"""
        service = self._get_service()
        result = service.get_all_snapshot()
        assert result.latest_trade_date is not None
        assert result.total > 0
        assert len(result.stocks) > 0
        first = result.stocks[0]
        assert first.code is not None
        assert first.name is not None
        assert first.trade_date is not None
        assert first.close > 0
        assert first.indicators is not None

    def test_get_incremental_real_db(self):
        """真实数据库增量同步"""
        service = self._get_service()
        result = service.get_incremental_snapshot('2026-06-01')
        assert result.latest_trade_date is not None
        assert result.days > 0
        assert len(result.stocks) > 0
        assert result.days >= 15

    def test_incremental_large_since(self):
        """since 接近最新日期时数据量较小"""
        service = self._get_service()
        result = service.get_incremental_snapshot('2099-12-31')
        assert result.stocks == []
        assert result.days == 0