"""
router/fx.py - 汇率查询接口路由（M4.5）

提供外汇中间价查询，数据来自 fx_rates 表（由 sync_fx.py 每日同步）。
- GET /api/fx/rate?pair=HKDCNY=X             → 该货币对最新一条汇率
- GET /api/fx/rate?pair=HKDCNY=X&date=2026-08-20 → 该日期及之前最近有效汇率（AS OF）
"""
import os
import logging
from typing import Dict, Optional

import psycopg2
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["汇率"])

BASE_CURRENCY_DEFAULT = "CNY"


def _connect() -> psycopg2.extensions.connection:
    """建立 PostgreSQL 连接（读取环境变量 PG_*，后端启动时已由 main 加载 .env）。"""
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        database=os.environ.get("PG_DATABASE", "quant_trading"),
        user=os.environ.get("PG_USER", "quant_user"),
        password=os.environ.get("PG_PASSWORD", ""),
        connect_timeout=5,
    )


def _query_rate(pair: str, date: Optional[str] = None) -> Optional[Dict]:
    """从 fx_rates 查询汇率。

    Args:
        pair: 货币对代码（如 HKDCNY=X）
        date: 可选，YYYY-MM-DD；提供时返回该日期及之前最近有效一条（AS OF）

    Returns:
        命中返回 dict（含 pair/date/rate/base_currency），无数据返回 None。
    """
    if date:
        sql = """
            SELECT pair, trade_date, rate, base_currency
            FROM fx_rates
            WHERE pair = %s AND trade_date <= %s
            ORDER BY trade_date DESC
            LIMIT 1
        """
        params = (pair, date)
    else:
        sql = """
            SELECT pair, trade_date, rate, base_currency
            FROM fx_rates
            WHERE pair = %s
            ORDER BY trade_date DESC
            LIMIT 1
        """
        params = (pair,)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "pair": row[0],
                "date": row[1].isoformat(),
                "rate": float(row[2]),
                "base_currency": row[3] or BASE_CURRENCY_DEFAULT,
            }
    finally:
        conn.close()


@router.get("/rate", summary="查询汇率")
def get_fx_rate(pair: str, date: Optional[str] = None) -> Dict:
    """按货币对（及可选日期）查询汇率。

    Args:
        pair: 货币对代码，必填，如 HKDCNY=X / USDCNY=X
        date: 可选日期 YYYY-MM-DD；不传返回该 pair 最新一条，传则返回该日及之前最近有效一条。

    Returns:
        {pair, date, rate, base_currency}
    """
    pair = pair.strip().upper()
    if not pair:
        raise HTTPException(status_code=400, detail="pair 不能为空，例如 HKDCNY=X")
    try:
        row = _query_rate(pair, date)
    except psycopg2.DatabaseError as e:
        logger.exception("查询汇率失败")
        raise HTTPException(status_code=500, detail=f"数据库查询异常: {e}")
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到汇率数据: pair={pair}" + (f", date={date}" if date else ""),
        )
    return row