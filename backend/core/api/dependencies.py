"""
dependencies.py - 依赖注入模块
FastAPI 依赖注入管理，所有 dep 同步，lru_cache 单例
"""
import re
import os
import logging
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Generator, Optional
import psycopg2
from psycopg2 import pool as pg_pool
from fastapi import Depends, HTTPException
from collector.db.loader import DataLoader
from core.service.snapshot_service import SnapshotService
from core.service.screener_service import ScreenerService

logger = logging.getLogger(__name__)

# ====================================
# PostgreSQL 连接池
# ====================================
_PG_POOL: pg_pool.ThreadedConnectionPool | None = None

def init_pg_pool() -> None:
    global _PG_POOL
    if _PG_POOL is not None:
        return
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
    logger.info(f"[db_pool] 连接池初始化完成 min={min_conn}, max={max_conn}")

def close_pg_pool() -> None:
    global _PG_POOL
    if _PG_POOL:
        _PG_POOL.closeall()
        _PG_POOL = None
        # 清理所有lru_cache单例，断开旧连接池引用，防止连接泄漏
        get_snapshot_service.cache_clear()
        get_screener_service.cache_clear()
        get_loader.cache_clear()
        logger.info("[db_pool] 连接池已全部关闭，服务单例缓存已清理")

@contextmanager
def get_db() -> Generator:
    if _PG_POOL is None:
        raise RuntimeError("数据库连接池未初始化")
    conn = _PG_POOL.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _PG_POOL.putconn(conn)

# ============================================
# 公共校验常量
# ============================================
STOCK_CODE_PATTERN = r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'
STOCK_CODE_REGEX = re.compile(STOCK_CODE_PATTERN)
VALID_KLINE_PERIODS = {'daily', 'weekly', 'monthly'}
VALID_SIGNAL_TYPES = {'macd_cross', 'rsi_oversold', 'rsi_overbought', 'bollinger_breakout', 'all'}
VALID_BOARDS = {"main_board", "gem", "beijing"}

# ============================================
# 分页/排序数据类
# ============================================
@dataclass
class PaginationParams:
    page: int
    page_size: int
    offset: int
    limit: int

@dataclass
class SortParams:
    sort_by: str
    sort_order: str
    is_desc: bool

# ============================================
# 单例依赖
# ============================================
@lru_cache(maxsize=1)
def get_loader() -> DataLoader:
    return DataLoader().load()
LoaderDep = Annotated[DataLoader, Depends(get_loader)]

@lru_cache(maxsize=1)
def get_screener_service() -> ScreenerService:
    loader = get_loader()
    return ScreenerService(loader)
ScreenerServiceDep = Annotated[ScreenerService, Depends(get_screener_service)]

@lru_cache(maxsize=1)
def get_snapshot_service() -> SnapshotService:
    """
    获取快照服务单例
    测试/热重载场景可调用 get_snapshot_service.cache_clear() 释放旧实例
    """
    if _PG_POOL is None:
        raise RuntimeError("数据库连接池未初始化，无法创建快照服务")
    return SnapshotService(_PG_POOL)
SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]

# ============================================
# 分页、排序依赖
# ============================================
def get_pagination_params(page: int = 1, page_size: int = 50, max_page_size: int = 200) -> PaginationParams:
    page = max(page, 1)
    page_size = min(max(page_size, 1), max_page_size)
    offset = (page - 1) * page_size
    return PaginationParams(page=page, page_size=page_size, offset=offset, limit=page_size)
PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]

from core.api.models.schemas import ALLOWED_SORT_FIELDS  # noqa: E402
def get_sort_params(sort_by: str = "change_pct", sort_order: str = "desc") -> SortParams:
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "change_pct"
    sort_order = sort_order if sort_order in ["asc", "desc"] else "desc"
    return SortParams(sort_by=sort_by, sort_order=sort_order, is_desc=(sort_order == "desc"))
SortDep = Annotated[SortParams, Depends(get_sort_params)]

# ============================================
# 参数校验工具：拆分必填/可选日期消除歧义
# ============================================
def validate_optional_date(date_str: Optional[str], label: str = "日期") -> Optional[str]:
    if not date_str:
        return None
    s = date_str.strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise HTTPException(400, f"{label}格式错误，需 YYYY-MM-DD")

def validate_required_date(date_str: str, label: str = "日期") -> str:
    if not date_str or not date_str.strip():
        raise HTTPException(400, f"{label}不能为空")
    return validate_optional_date(date_str, label)

def validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> tuple:
    if not start_date or not end_date:
        return start_date, end_date
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    try:
        datetime.strptime(s, "%Y%m%d")
        datetime.strptime(e, "%Y%m%d")
    except ValueError:
        raise HTTPException(400, "起止日期格式错误")
    if s > e:
        raise HTTPException(400, "start_date 不能晚于 end_date")
    return start_date, end_date

def validate_stock_code(stock_code: str) -> str:
    if not stock_code:
        raise ValueError("股票代码不能为空")
    code = stock_code.strip().upper()
    if not code:
        raise ValueError("无效股票代码")
    return code

def validate_stock_code_format(stock_code: str) -> str:
    code = stock_code.strip().upper()
    if not STOCK_CODE_REGEX.match(code):
        raise HTTPException(400, f"股票代码格式错误：{code}，支持000001 / 000001.SZ / SH000001")
    return code

def validate_kline_period(period: str) -> str:
    p = period.strip().lower()
    if p not in VALID_KLINE_PERIODS:
        raise HTTPException(400, f"无效周期，可选：{','.join(VALID_KLINE_PERIODS)}")
    return p

def validate_signal_type(signal_type: str) -> str:
    t = signal_type.strip().lower()
    if t not in VALID_SIGNAL_TYPES:
        raise HTTPException(400, f"无效信号类型，可选：{','.join(VALID_SIGNAL_TYPES)}")
    return t

def validate_board(board: Optional[str]) -> Optional[str]:
    if board is None:
        return None
    b = board.strip().lower()
    if b not in VALID_BOARDS:
        raise HTTPException(400, f"板块仅支持：{','.join(VALID_BOARDS)}")
    return b