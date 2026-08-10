"""
cycles.py - PDCA 周期 API
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["PDCA周期"])


@router.get("", response_model=ApiResponse)
async def list_cycles(status: Optional[str] = Query(None)):
    """获取 PDCA 周期列表"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM pdca.pdca_cycle WHERE status = %s ORDER BY start_date DESC",
                    (status,),
                )
            else:
                cur.execute("SELECT * FROM pdca.pdca_cycle ORDER BY start_date DESC")

            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})