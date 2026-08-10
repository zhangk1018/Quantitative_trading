"""
stocks.py - 股票搜索 API（从现有 stock_basic 表查询）
"""
import logging

from fastapi import APIRouter, Query

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["股票搜索"])


@router.get("/search", response_model=ApiResponse)
async def search_stocks(q: str = Query(..., min_length=1)):
    """股票代码搜索（查询现有 stock_basic 表，自动补全）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            keyword = f"%{q}%"
            cur.execute(
                """
                SELECT code, name, exchange, area
                FROM public.stock_basic
                WHERE code LIKE %s OR name LIKE %s
                ORDER BY code
                LIMIT 20
                """,
                (keyword, keyword),
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})