"""
dependencies.py - 依赖注入模块

FastAPI 依赖注入管理，提供全局单例服务实例。
所有 dep 函数均为同步，使用 lru_cache 实现单例。
"""

from functools import lru_cache
from typing import Annotated
from fastapi import Depends

from collector.db.loader import DataLoader
from core.service.screener_service import ScreenerService

# ============================================
# 数据加载器依赖
# ============================================

@lru_cache(maxsize=1)
def get_loader() -> DataLoader:
    """获取数据加载器单例（懒加载）"""
    return DataLoader().load()


LoaderDep = Annotated[DataLoader, Depends(get_loader)]

# ============================================
# 服务层依赖
# ============================================

@lru_cache(maxsize=1)
def get_screener_service() -> ScreenerService:
    loader = get_loader()
    return ScreenerService(loader)


ScreenerServiceDep = Annotated[ScreenerService, Depends(get_screener_service)]

# ============================================
# KlineService / SignalService（由方舟在 Day 2 实现）
# ============================================

# from core.service.kline_service import KlineService
# from core.service.signal_service import SignalService

# @lru_cache(maxsize=1)
# def get_kline_service(loader: DataLoader = Depends(get_loader)) -> KlineService:
#     return KlineService(loader)
# KlineServiceDep = Annotated[KlineService, Depends(get_kline_service)]

# @lru_cache(maxsize=1)
# def get_signal_service(loader: DataLoader = Depends(get_loader)) -> SignalService:
#     return SignalService(loader)
# SignalServiceDep = Annotated[SignalService, Depends(get_signal_service)]

# ============================================
# 通用参数依赖
# ============================================

def get_pagination_params(page: int = 1, page_size: int = 50, max_page_size: int = 200):
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    if page_size > max_page_size:
        page_size = max_page_size
    return {"page": page, "page_size": page_size, "offset": (page - 1) * page_size, "limit": page_size}


PaginationDep = Annotated[dict, Depends(get_pagination_params)]


ALLOWED_SORT_FIELDS = {
    'change_pct', 'close', 'volume', 'amount',
    'turnover_rate', 'pe', 'pb', 'market_cap',
    'circ_mv', 'ma5', 'ma10', 'ma20', 'rsi_6', 'macd',
    'boll_upper', 'boll_mid', 'boll_lower',
    'high', 'low', 'change',
}


def get_sort_params(sort_by: str = "change_pct", sort_order: str = "desc"):
    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "change_pct"
    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"
    return {"sort_by": sort_by, "sort_order": sort_order, "is_desc": sort_order == "desc"}


SortDep = Annotated[dict, Depends(get_sort_params)]

# ============================================
# 参数校验依赖
# ============================================

def validate_stock_code(stock_code: str) -> str:
    if not stock_code:
        raise ValueError("股票代码不能为空")
    stock_code = stock_code.strip().upper()
    if not stock_code:
        raise ValueError("无效的股票代码")
    return stock_code


StockCodeDep = Annotated[str, Depends(validate_stock_code)]


def validate_date_param(date_str: str) -> str:
    if not date_str:
        raise ValueError("日期参数不能为空")
    if len(date_str) != 8 or not date_str.isdigit():
        raise ValueError(f"无效的日期格式: {date_str}，应为 YYYYMMDD 格式")
    return date_str


DateDep = Annotated[str, Depends(validate_date_param)]