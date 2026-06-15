"""
test_schemas.py - Pydantic 模型单元测试

测试目标：
1. 验证字段类型正确性
2. 验证必填字段校验
3. 验证枚举值约束
4. 验证数值范围约束
5. 验证序列化/反序列化
"""

import pytest
from datetime import date
from decimal import Decimal
from src.api.models.schemas import (
    StockResponse, 
    StocksRequest, 
    ApiResponse,
    ListedBoard,
    KLineItem,
    SignalItem
)


class TestStockResponse:
    """股票响应模型测试"""
    
    def test_valid_stock_response(self):
        """测试有效的股票数据"""
        data = {
            "stock_code": "000001.SZ",
            "stock_name": "平安银行",
            "listed_board": ListedBoard.SH_MAIN,
            "industry": "银行",
            "trade_date": date(2026, 5, 29),
            "pre_close": Decimal("10.50"),
            "close": Decimal("10.93"),
            "change_pct": Decimal("4.09"),
            "is_st": False
        }
        
        stock = StockResponse(**data)
        assert stock.stock_code == "000001.SZ"
        assert stock.pre_close == Decimal("10.50")
        assert stock.close == Decimal("10.93")
        assert stock.is_st is False
    
    def test_optional_fields_can_be_none(self):
        """测试可选字段可以为 None"""
        data = {
            "stock_code": "000001.SZ",
            "stock_name": "平安银行",
            "listed_board": ListedBoard.SH_MAIN,
            "trade_date": date(2026, 5, 29)
        }
        
        stock = StockResponse(**data)
        assert stock.pe is None
        assert stock.pb is None
        assert stock.ma5 is None
    
    def test_invalid_listed_board(self):
        """测试无效的上市板块"""
        with pytest.raises(ValueError):
            StockResponse(
                stock_code="000001.SZ",
                stock_name="平安银行",
                listed_board="无效板块",  # type: ignore
                trade_date=date(2026, 5, 29)
            )
    
    def test_negative_price_rejected(self):
        """测试负价格被拒绝"""
        with pytest.raises(ValueError):
            StockResponse(
                stock_code="000001.SZ",
                stock_name="平安银行",
                listed_board=ListedBoard.SH_MAIN,
                trade_date=date(2026, 5, 29),
                close=Decimal("-10.00")  # 负价格
            )
    
    def test_rsi_range_validation(self):
        """测试 RSI 范围校验（0-100）"""
        # 有效值
        stock = StockResponse(
            stock_code="000001.SZ",
            stock_name="平安银行",
            listed_board=ListedBoard.SH_MAIN,
            trade_date=date(2026, 5, 29),
            rsi_6=Decimal("65.5")
        )
        assert stock.rsi_6 == Decimal("65.5")
        
        # 超出范围
        with pytest.raises(ValueError):
            StockResponse(
                stock_code="000001.SZ",
                stock_name="平安银行",
                listed_board=ListedBoard.SH_MAIN,
                trade_date=date(2026, 5, 29),
                rsi_6=Decimal("150.0")  # > 100
            )


class TestStocksRequest:
    """股票请求模型测试"""
    
    def test_valid_request(self):
        """测试有效的请求"""
        req = StocksRequest(
            filters="pattern_bull_candle",
            industry="银行",
            sort_by="change_pct",
            offset=0,
            limit=100,
            as_of_date=date(2026, 5, 29)
        )
        
        assert req.sort_by == "change_pct"
        assert req.limit == 100
        assert req.as_of_date == date(2026, 5, 29)
    
    def test_as_of_date_required(self):
        """测试 as_of_date 必填"""
        with pytest.raises(ValueError):
            StocksRequest(
                sort_by="change_pct",
                limit=100
                # 缺少 as_of_date
            )
    
    def test_limit_max_200(self):
        """测试 limit 最大值 200"""
        # 有效
        req = StocksRequest(
            sort_by="change_pct",
            limit=200,
            as_of_date=date(2026, 5, 29)
        )
        assert req.limit == 200
        
        # 超限
        with pytest.raises(ValueError):
            StocksRequest(
                sort_by="change_pct",
                limit=201,  # > 200
                as_of_date=date(2026, 5, 29)
            )
    
    def test_invalid_sort_by(self):
        """测试无效的排序字段"""
        with pytest.raises(ValueError):
            StocksRequest(
                sort_by="invalid_field",
                limit=100,
                as_of_date=date(2026, 5, 29)
            )
    
    def test_valid_sort_by_fields(self):
        """测试所有允许的排序字段"""
        from src.api.models.schemas import ALLOWED_SORT_FIELDS
        
        for field in ALLOWED_SORT_FIELDS:
            req = StocksRequest(
                sort_by=field,
                limit=100,
                as_of_date=date(2026, 5, 29)
            )
            assert req.sort_by == field
    
    def test_listed_board_filter(self):
        """测试上市板块筛选"""
        req = StocksRequest(
            listed_board=ListedBoard.SH_MAIN,
            sort_by="change_pct",
            limit=100,
            as_of_date=date(2026, 5, 29)
        )
        assert req.listed_board == ListedBoard.SH_MAIN


class TestApiResponse:
    """统一响应信封测试"""
    
    def test_success_response(self):
        """测试成功响应"""
        resp = ApiResponse(
            code=200,
            message="success",
            data={"stock_code": "000001.SZ"}
        )
        
        assert resp.code == 200
        assert resp.message == "success"
    
    def test_error_response(self):
        """测试错误响应"""
        resp = ApiResponse(
            code=400,
            message="参数错误",
            data=None
        )
        
        assert resp.code == 400
        assert resp.data is None
    
    def test_default_values(self):
        """测试默认值"""
        resp = ApiResponse()
        
        assert resp.code == 200
        assert resp.message == "success"
        assert resp.data is None


class TestKLineItem:
    """K线数据测试"""
    
    def test_valid_kline(self):
        """测试有效的K线数据"""
        kline = KLineItem(
            trade_date=date(2026, 5, 29),
            open=Decimal("10.50"),
            high=Decimal("11.00"),
            low=Decimal("10.45"),
            close=Decimal("10.93"),
            volume=1000000,
            amount=Decimal("10930000.00")
        )
        
        assert kline.close == Decimal("10.93")
        assert kline.volume == 1000000


class TestSignalItem:
    """买卖信号测试"""
    
    def test_buy_signal(self):
        """测试买入信号"""
        signal = SignalItem(
            trade_date=date(2026, 5, 29),
            signal_type="buy",
            price=Decimal("10.93"),
            reason="MACD金叉"
        )
        
        assert signal.signal_type == "buy"
        assert signal.reason == "MACD金叉"
    
    def test_sell_signal(self):
        """测试卖出信号"""
        signal = SignalItem(
            trade_date=date(2026, 5, 28),
            signal_type="sell",
            price=Decimal("11.50"),
            reason="MACD死叉"
        )
        
        assert signal.signal_type == "sell"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
