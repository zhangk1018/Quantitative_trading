"""
brokers.py - 券商适配器 API
"""
import logging

from fastapi import APIRouter

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["券商适配器"])


@router.get("", response_model=ApiResponse)
async def list_brokers():
    """获取可用券商适配器列表"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                    "SELECT id, broker_name, display_name, is_active FROM pdca.broker_adapter ORDER BY broker_name"
                )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})