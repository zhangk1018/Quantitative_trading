"""
dependencies.py - 依赖注入模块

FastAPI 依赖注入管理，提供全局单例服务实例。
所有 dep 函数均为同步，使用 lru_cache 实现单例。
"""

import re
from functools import lru_cache
from typing import Annotated
from fastapi import Depends, HTTPException

from collector.db.loader import DataLoader
from core.service.screener_service import ScreenerService

# ============================================
# 公共验证常量
# ============================================

# 股票代码校验正则 - 支持 000001.SZ、SH.000001、SZ.000001、000001 等多种格式
STOCK_CODE_PATTERN = r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'
STOCK_CODE_REGEX = re.compile(STOCK_CODE_PATTERN)

# 有效 K线周期
VALID_KLINE_PERIODS = {'daily', 'weekly', 'monthly'}

# 有效信号类型（与 signal_service.signal_config 对齐）
VALID_SIGNAL_TYPES = {'macd_cross', 'rsi_oversold', 'rsi_overbought', 'bollinger_breakout', 'all'}

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


# ALLOWED_SORT_FIELDS 单一来源：core.api.models.schemas
# 引入到本模块仅为向后兼容，新代码请使用 from core.api.models.schemas import ALLOWED_SORT_FIELDS
from core.api.models.schemas import ALLOWED_SORT_FIELDS  # noqa: E402


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
    """
    校验并规范化股票代码（轻量版，仅做 strip/upper）

    适用场景：作为 FastAPI 依赖项，基础校验
    如需严格格式校验，请使用 validate_stock_code_format
    """
    if not stock_code:
        raise ValueError("股票代码不能为空")
    stock_code = stock_code.strip().upper()
    if not stock_code:
        raise ValueError("无效的股票代码")
    return stock_code


def validate_stock_code_format(stock_code: str) -> str:
    """
    校验并规范化股票代码（严格版，包含正则格式校验）

    支持格式：
    - 000001（纯6位数字）
    - 000001.SZ / 000001.SH / 000001.BJ（带后缀）
    - SH000001 / SZ000001（带前缀）

    Returns:
        规范化后的股票代码（strip + upper）

    Raises:
        HTTPException: 格式错误时返回 400
    """
    if not stock_code:
        raise HTTPException(
            status_code=400,
            detail="股票代码不能为空"
        )

    raw = stock_code
    code = stock_code.strip().upper()

    if not STOCK_CODE_REGEX.match(code):
        raise HTTPException(
            status_code=400,
            detail=f"股票代码格式错误: '{raw}'，应为6位数字或带 SH/SZ/BJ 前缀（如 000001、000001.SZ、SZ000001）"
        )
    return code


StockCodeDep = Annotated[str, Depends(validate_stock_code)]
StockCodeFormatDep = Annotated[str, Depends(validate_stock_code_format)]


def validate_date_param(date_str: str) -> str:
    """
    校验日期参数

    支持格式：
    - YYYYMMDD（推荐，与后端统一）
    - YYYY-MM-DD（自动转换为 YYYYMMDD）
    """
    if not date_str:
        raise ValueError("日期参数不能为空")

    # 尝试匹配 YYYY-MM-DD 格式
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
    if match:
        # 转换为 YYYYMMDD 格式
        return f"{match.group(1)}{match.group(2)}{match.group(3)}"

    # 验证 YYYYMMDD 格式
    if len(date_str) != 8 or not date_str.isdigit():
        raise ValueError(f"无效的日期格式: {date_str}，应为 YYYYMMDD 或 YYYY-MM-DD 格式")

    return date_str


def validate_date_param_strict(date_str: str) -> str:
    """
    校验日期参数（严格版，直接返回 HTTPException 而非 ValueError）

    适用场景：路由层直接调用
    """
    if not date_str:
        raise HTTPException(status_code=400, detail="日期参数不能为空")

    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
    if match:
        return f"{match.group(1)}{match.group(2)}{match.group(3)}"

    if len(date_str) != 8 or not date_str.isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"日期格式错误: {date_str}，应为 YYYYMMDD 或 YYYY-MM-DD 格式"
        )

    return date_str


DateDep = Annotated[str, Depends(validate_date_param)]


def validate_date_range(start: str, end: str) -> None:
    """
    校验日期范围：如果 start 和 end 均提供，必须 start <= end
    """
    if start and end and start > end:
        raise HTTPException(
            status_code=400,
            detail=f"日期范围无效: start_date({start}) 不能晚于 end_date({end})"
        )