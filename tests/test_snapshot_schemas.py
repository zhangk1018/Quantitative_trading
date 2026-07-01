"""
test_snapshot_schemas.py - 快照 API 数据模型单元测试

覆盖：
1. SnapshotIndicators：字段类型、默认值、序列化
2. SnapshotStock：必填字段、嵌套 indicators、数据序列化
3. SnapshotAllData / SnapshotIncrementalData：结构完整性
4. ApiResponse 信封封装
"""

import pytest
from datetime import date
from shared.schemas import (
    SnapshotIndicators,
    SnapshotStock,
    SnapshotAllData,
    SnapshotIncrementalData,
    ApiResponse,
)


class TestSnapshotIndicators:
    """SnapshotIndicators 模型测试"""

    def test_all_fields_provided(self):
        """全部指标字段传入"""
        data = SnapshotIndicators(
            ma5=10.5,
            ma10=10.3,
            ma20=9.8,
            ma60=9.5,
            rsi_6=65.2,
            rsi_12=55.0,
            rsi_24=50.1,
            macd_dif=1.2345,
            macd_dea=1.1000,
            macd=0.1345,
            boll_upper=11.5,
            boll_mid=10.0,
            boll_lower=8.5,
            is_macd_golden_cross=True,
            is_macd_dead_cross=False,
        )
        assert data.ma5 == 10.5
        assert data.ma10 == 10.3
        assert data.boll_upper == 11.5
        assert data.is_macd_golden_cross is True
        assert data.is_macd_dead_cross is False
        assert data.rsi_6 == 65.2
        assert data.macd_dif == 1.2345

    def test_optional_fields_default_to_none(self):
        """可选字段默认 None"""
        data = SnapshotIndicators()
        assert data.ma5 is None
        assert data.ma10 is None
        assert data.ma20 is None
        assert data.ma60 is None
        assert data.rsi_6 is None
        assert data.macd_dif is None

    def test_bool_fields_default_to_false(self):
        """布尔指标默认 False"""
        data = SnapshotIndicators()
        assert data.is_macd_golden_cross is False
        assert data.is_macd_dead_cross is False

    def test_serialize_to_json(self):
        """序列化为 JSON 时字段名正确"""
        data = SnapshotIndicators(ma5=10.5, macd_dif=0.5)
        d = data.model_dump()
        assert d['ma5'] == 10.5
        assert d['macd_dif'] == 0.5
        assert d['is_macd_golden_cross'] is False
        assert 'macd_dea' in d

    def test_partial_fields(self):
        """部分字段传入"""
        data = SnapshotIndicators(ma5=10.5, rsi_6=60.0)
        assert data.ma5 == 10.5
        assert data.rsi_6 == 60.0
        assert data.ma10 is None
        assert data.boll_mid is None


class TestSnapshotStock:
    """SnapshotStock 模型测试"""

    def test_minimal_stock(self):
        """最小必要字段"""
        stock = SnapshotStock(
            code='600519',
            name='贵州茅台',
            listed_board='上海主板',
            trade_date=date(2026, 6, 30),
            close=1500.0,
            indicators=SnapshotIndicators(ma5=1480.0),
            ohlcv=[[1719763200, 1490.0, 1510.0, 1480.0, 1500.0, 5000000.0]],
        )
        assert stock.code == '600519'
        assert stock.name == '贵州茅台'
        assert stock.close == 1500.0
        assert stock.indicators.ma5 == 1480.0
        assert len(stock.ohlcv) == 1
        assert stock.ohlcv[0][0] == 1719763200  # time
        assert stock.ohlcv[0][4] == 1500.0  # close

    def test_optional_fields_default(self):
        """可选字段默认空字符串或 None"""
        stock = SnapshotStock(
            code='000001',
            name='平安银行',
            listed_board='深圳主板',
            trade_date=date(2026, 6, 30),
            close=12.0,
            indicators=SnapshotIndicators(),
            ohlcv=[],
        )
        assert stock.industry == ''
        assert stock.change_pct is None
        assert stock.market_cap is None
        assert stock.pe_ttm is None

    def test_no_ohlcv(self):
        """OHLCV 为空列表"""
        stock = SnapshotStock(
            code='600000',
            name='浦发银行',
            listed_board='上海主板',
            trade_date=date(2026, 6, 30),
            close=8.0,
            indicators=SnapshotIndicators(),
            ohlcv=[],
        )
        assert stock.ohlcv == []

    def test_ohlcv_format(self):
        """OHLCV 列式格式验证"""
        ohlcv = [
            [1719763200, 10.0, 11.0, 9.5, 10.5, 1000000.0],
            [1719849600, 10.5, 11.5, 10.0, 11.0, 1200000.0],
        ]
        stock = SnapshotStock(
            code='000001',
            name='平安银行',
            listed_board='深圳主板',
            trade_date=date(2026, 6, 30),
            close=11.0,
            indicators=SnapshotIndicators(),
            ohlcv=ohlcv,
        )
        assert len(stock.ohlcv) == 2
        # 每行 6 列：[time, open, high, low, close, volume]
        for row in stock.ohlcv:
            assert len(row) == 6
            assert isinstance(row[0], float)  # time
            assert row[3] <= row[2]  # low <= high

    def test_serialize_to_json(self):
        """序列化为 JSON"""
        stock = SnapshotStock(
            code='600519',
            name='贵州茅台',
            listed_board='上海主板',
            trade_date=date(2026, 6, 30),
            close=1500.0,
            indicators=SnapshotIndicators(ma5=1480.0, macd_dif=1.5),
            ohlcv=[[1719763200, 1490.0, 1510.0, 1480.0, 1500.0, 5000000.0]],
        )
        d = stock.model_dump(mode='json')
        assert d['code'] == '600519'
        assert d['indicators']['ma5'] == 1480.0
        assert d['indicators']['macd_dif'] == 1.5
        assert d['ohlcv'][0][1] == 1490.0


class TestSnapshotAllData:
    """SnapshotAllData 模型测试"""

    def test_full_structure(self):
        """全量快照数据结构"""
        stocks = [
            SnapshotStock(
                code='600519', name='贵州茅台', listed_board='上海主板',
                trade_date=date(2026, 6, 30), close=1500.0,
                indicators=SnapshotIndicators(), ohlcv=[],
            ),
            SnapshotStock(
                code='000001', name='平安银行', listed_board='深圳主板',
                trade_date=date(2026, 6, 30), close=12.0,
                indicators=SnapshotIndicators(), ohlcv=[],
            ),
        ]
        data = SnapshotAllData(
            latest_trade_date='2026-06-30',
            total=len(stocks),
            stocks=stocks,
        )
        assert data.latest_trade_date == '2026-06-30'
        assert data.total == 2
        assert len(data.stocks) == 2
        assert data.stocks[0].code == '600519'

    def test_serialize_with_envelope(self):
        """ApiResponse 信封封装"""
        data = SnapshotAllData(
            latest_trade_date='2026-06-30',
            total=1,
            stocks=[
                SnapshotStock(
                    code='600519', name='贵州茅台', listed_board='上海主板',
                    trade_date=date(2026, 6, 30), close=1500.0,
                    indicators=SnapshotIndicators(), ohlcv=[],
                ),
            ],
        )
        resp = ApiResponse(code=200, message='success', data=data)
        d = resp.model_dump(mode='json')
        assert d['code'] == 200
        assert d['data']['latest_trade_date'] == '2026-06-30'
        assert d['data']['stocks'][0]['code'] == '600519'


class TestSnapshotIncrementalData:
    """SnapshotIncrementalData 模型测试"""

    def test_full_structure(self):
        """增量同步数据结构"""
        data = SnapshotIncrementalData(
            since='2026-06-20',
            latest_trade_date='2026-06-30',
            days=5,
            stocks=[
                SnapshotStock(
                    code='600519', name='贵州茅台', listed_board='上海主板',
                    trade_date=date(2026, 6, 30), close=1500.0,
                    indicators=SnapshotIndicators(), ohlcv=[],
                ),
            ],
        )
        assert data.since == '2026-06-20'
        assert data.days == 5
        assert len(data.stocks) == 1

    def test_empty_stocks(self):
        """无增量数据时 stocks 为空"""
        data = SnapshotIncrementalData(
            since='2099-01-01',
            latest_trade_date='2026-06-30',
            days=0,
            stocks=[],
        )
        assert data.days == 0
        assert data.stocks == []