"""
dependencies.py - 依赖注入模块

FastAPI 依赖注入管理，提供全局单例服务实例。
所有 dep 函数均为同步，使用 lru_cache 实现单例。
"""

import re
import os
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Generator, Optional

import psycopg2
from psycopg2 import pool as pg_pool
from fastapi import Depends, HTTPException

from collector.db.loader import DataLoader
from core.service.screener_service import ScreenerService

# ====================================
# PostgreSQL 连接池（ThreadedConnectionPool）
# 初始化的 minconn=2/maxconn=10，可通过环境变量覆盖
# ====================================
_PG_POOL: pg_pool.ThreadedConnectionPool | None = None


def init_pg_pool() -> None:
    """在 FastAPI 启动时调用，初始化连接池。"""
    global _PG_POOL
    if _PG_POOL is not None:
        return  # 已初始化，跳过

    min_conn = int(os.environ.get("PG_POOL_MIN", "2"))
    max_conn = int(os.environ.get("PG_POOL_MAX", "10"))

    _PG_POOL = pg_pool.ThreadedConnectionPool(
        minconn=min_conn,
        maxconn=max_conn,
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        database=os.environ.get("PG_DATABASE", "quant_trading"),
        user=os.environ.get("PG_USER", "quant_user"),
        password=os.environ.get("PG_PASSWORD", ""),
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=10,
    )
    print(f"[db_pool] 连接池已初始化: min={min_conn}, max={max_conn}")


def close_pg_pool() -> None:
    """在 FastAPI 关闭时调用，关闭所有连接。"""
    global _PG_POOL
    if _PG_POOL:
        _PG_POOL.closeall()
        _PG_POOL = None
        print("[db_pool] 连接池已关闭")


@contextmanager
def get_db() -> Generator:
    """
    获取数据库连接的上下文管理器。

    用法（FastAPI 依赖注入）：
        @router.get("/")
        def get_items(db=Depends(get_db)):
            with db as conn:
                cur = conn.cursor()
                cur.execute("SELECT ...")
                ...

    用法（直接调用）：
        with get_db() as conn:
            ...

    每次从池中借出连接，用完自动归还，无需手动 close。
    """
    if _PG_POOL is None:
        raise RuntimeError("数据库连接池未初始化，请确保 FastAPI 已启动")
    conn = _PG_POOL.getconn()
    try:
        yield conn
        conn.commit()  # 自动提交，异常时自动回滚
    except Exception:
        conn.rollback()
        raise
    finally:
        _PG_POOL.putconn(conn)


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
    """
    stock_code = stock_code.strip().upper()
    if not STOCK_CODE_REGEX.match(stock_code):
        raise HTTPException(
            status_code=400,
            detail=f"无效的股票代码格式: {stock_code}，支持的格式：000001、000001.SZ、SH000001"
        )
    return stock_code


def validate_kline_period(period: str) -> str:
    """校验 K 线周期参数"""
    period = period.strip().lower()
    if period not in VALID_KLINE_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 K 线周期: {period}，支持的周期：{', '.join(VALID_KLINE_PERIODS)}"
        )
    return period


def validate_signal_type(signal_type: str) -> str:
    """校验信号类型参数"""
    signal_type = signal_type.strip().lower()
    if signal_type not in VALID_SIGNAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的信号类型: {signal_type}，支持的类型: {', '.join(VALID_SIGNAL_TYPES)}"
        )
    return signal_type


def validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> tuple:
    """校验日期范围（start_date <= end_date）

    输入: start_date, end_date (YYYY-MM-DD 或 YYYYMMDD)
    输出: (start_date, end_date) 元组
    异常: start_date > end_date 时抛 400
    """
    if not start_date or not end_date:
        return start_date, end_date
    # 统一格式 YYYYMMDD
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    try:
        datetime.strptime(s, "%Y%m%d")
        datetime.strptime(e, "%Y%m%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"日期格式错误: start_date={start_date}, end_date={end_date}"
        )
    if s > e:
        raise HTTPException(
            status_code=400,
            detail=f"start_date ({start_date}) 不能晚于 end_date ({end_date})"
        )
    return start_date, end_date
