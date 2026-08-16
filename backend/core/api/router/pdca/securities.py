"""
securities.py - 标的 ABC 分类 CRUD

对应《PDCA交付物三》PL-003 前置：C 类标的禁止创建交易计划。
security_tag 表每个 code 唯一（uq_security_tag_code）。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ABC分类"])


class SecurityTagCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    security_name: Optional[str] = None
    tag: str = Field(..., pattern="^(A|B|C)$")
    note: Optional[str] = None


class SecurityTagUpdate(BaseModel):
    security_name: Optional[str] = None
    tag: str = Field(..., pattern="^(A|B|C)$")
    note: Optional[str] = None


@router.get("", response_model=ApiResponse)
async def list_securities(tag: Optional[str] = Query(None, pattern="^(A|B|C)$")):
    """获取 ABC 分类列表"""
    with get_db() as conn:
        with conn.cursor() as cur:
            sql = "SELECT * FROM pdca.security_tag WHERE deleted_at IS NULL"
            params = []
            if tag:
                sql += " AND tag = %s"
                params.append(tag)
            sql += " ORDER BY code"
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("", response_model=ApiResponse, status_code=201)
async def create_security(body: SecurityTagCreate):
    """新增或更新 ABC 分类（code 已存在则 upsert，使用 ON CONFLICT 避免竞态）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pdca.security_tag (account_id, code, security_name, tag, note)
                VALUES (1, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET
                    security_name = EXCLUDED.security_name,
                    tag = EXCLUDED.tag,
                    note = EXCLUDED.note,
                    updated_at = NOW(),
                    deleted_at = NULL
                RETURNING id
                """,
                (body.code, body.security_name, body.tag, body.note),
            )
            new_id = cur.fetchone()[0]
            logger.info("新增/更新 ABC 分类 code=%s tag=%s", body.code, body.tag)
            conn.commit()
            return ApiResponse(code=200, message="success", data={"id": new_id})


@router.put("/{security_id}", response_model=ApiResponse)
async def update_security(security_id: int, body: SecurityTagUpdate):
    """更新 ABC 分类"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM pdca.security_tag WHERE id = %s AND deleted_at IS NULL",
                (security_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"ABC 分类 {security_id} 不存在")
            cur.execute(
                "UPDATE pdca.security_tag SET security_name = %s, tag = %s, note = %s, "
                "updated_at = NOW() WHERE id = %s",
                (body.security_name, body.tag, body.note, security_id),
            )
            logger.info("更新 ABC 分类 id=%s tag=%s", security_id, body.tag)
            return ApiResponse(code=200, message="success", data={"id": security_id})


@router.delete("/{security_id}", response_model=ApiResponse)
async def delete_security(security_id: int):
    """删除 ABC 分类（软删除）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pdca.security_tag SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL",
                (security_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"ABC 分类 {security_id} 不存在")
            logger.info("删除 ABC 分类 id=%s", security_id)
            return ApiResponse(code=200, message="success", data={"id": security_id})