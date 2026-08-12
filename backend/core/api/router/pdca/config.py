"""
config.py - 系统配置 API
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["系统配置"])


class ConfigUpdate(BaseModel):
    config_key: str
    config_value: Optional[str] = None
    numeric_value: Optional[float] = None
    bool_value: Optional[bool] = None
    modify_reason: str


# ============================================================
# 系统配置
# ============================================================

@router.get("", response_model=ApiResponse)
async def get_config():
    """获取所有系统配置"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (config_key) id, config_key, config_value, numeric_value, bool_value,
                       description, version, modified_at, modified_by, modify_reason
                FROM pdca.system_config
                ORDER BY config_key, id DESC
                """
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.put("", response_model=ApiResponse)
async def update_config(update: ConfigUpdate):
    """更新系统配置项"""
    with get_db() as conn:
        with conn.cursor() as cur:
            config_key = update.config_key

            # 获取当前配置（取最新版本，避免版本号冲突）
            cur.execute(
                "SELECT id, config_key, config_value, numeric_value, bool_value, version FROM pdca.system_config WHERE config_key = %s ORDER BY id DESC LIMIT 1",
                (config_key,),
            )
            current = cur.fetchone()
            if not current:
                raise HTTPException(status_code=404, detail="40011: 配置项不存在")

            current_id, _, current_value, current_numeric, current_bool, current_version = current

            # 计算新版本号
            parts = current_version.split(".")
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            new_version = f"{major}.{minor}.{patch + 1}"

            # 插入新版本记录
            new_value = update.config_value if update.config_value is not None else current_value
            new_numeric = update.numeric_value if update.numeric_value is not None else current_numeric
            new_bool = update.bool_value if update.bool_value is not None else current_bool

            try:
                cur.execute(
                    """
                    INSERT INTO pdca.system_config
                        (config_key, config_value, numeric_value, bool_value, description, version, modify_reason)
                    VALUES (%s, %s, %s, %s,
                        (SELECT description FROM pdca.system_config WHERE config_key = %s ORDER BY id DESC LIMIT 1),
                        %s, %s)
                    RETURNING id
                    """,
                    (config_key, new_value, new_numeric, new_bool, config_key, new_version, update.modify_reason),
                )
                new_id = cur.fetchone()[0]
                conn.commit()
                return ApiResponse(code=200, message="success", data={"id": new_id, "version": new_version})
            except Exception as e:
                logger.exception("更新配置失败")
                raise HTTPException(status_code=500, detail=f"50002: {str(e)}")


@router.get("/history/{config_key}", response_model=ApiResponse)
async def get_config_history(config_key: str):
    """获取配置变更历史"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, version, config_value, numeric_value, bool_value, modified_at, modified_by, modify_reason
                FROM pdca.system_config
                WHERE config_key = %s
                ORDER BY version DESC
                """,
                (config_key,),
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})