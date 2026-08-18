"""
act_record.py - 迭代处理记录 CRUD API

Act 模块：问题清单+改进措施管理
- 支持 pdca_cycle_id 查询（一个周期可有多条记录）
- 问题清单以 TEXT[] 数组存储
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["迭代处理记录"])


# ============================================================
# Pydantic 请求模型
# ============================================================

class ActRecordCreate(BaseModel):
    pdca_cycle_id: int
    problem_list: Optional[list[str]] = None
    rectify_plan: str = Field(..., min_length=1)
    bind_next_cycle_goal: Optional[str] = None
    is_freeze_experience: bool = False
    new_config_version: Optional[str] = None


class ActRecordUpdate(BaseModel):
    problem_list: Optional[list[str]] = None
    rectify_plan: Optional[str] = None
    bind_next_cycle_goal: Optional[str] = None
    is_freeze_experience: Optional[bool] = None
    new_config_version: Optional[str] = None


# ============================================================
# API 端点
# ============================================================

@router.get("/act-records/{cycle_id}", response_model=ApiResponse)
async def list_act_records(cycle_id: int):
    """获取指定周期的所有迭代处理记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pdca.pdca_act_record WHERE pdca_cycle_id = %s ORDER BY created_at DESC",
                (cycle_id,),
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("/act-records", response_model=ApiResponse, status_code=201)
async def create_act_record(body: ActRecordCreate):
    """创建迭代处理记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 检查周期存在
            cur.execute("SELECT id, status FROM pdca.pdca_cycle WHERE id = %s", (body.pdca_cycle_id,))
            cycle = cur.fetchone()
            if not cycle:
                raise HTTPException(status_code=404, detail=f"周期 {body.pdca_cycle_id} 不存在")

            cur.execute(
                """
                INSERT INTO pdca.pdca_act_record
                    (account_id, pdca_cycle_id, problem_list, rectify_plan,
                     bind_next_cycle_goal, is_freeze_experience, new_config_version)
                VALUES (1, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    body.pdca_cycle_id,
                    body.problem_list, body.rectify_plan,
                    body.bind_next_cycle_goal, body.is_freeze_experience, body.new_config_version,
                ),
            )
            record_id = cur.fetchone()[0]
            conn.commit()
            logger.info("创建迭代处理记录 id=%s, cycle=%s", record_id, body.pdca_cycle_id)
            return ApiResponse(code=200, message="success", data={"id": record_id})


@router.put("/act-records/{record_id}", response_model=ApiResponse)
async def update_act_record(record_id: int, body: ActRecordUpdate):
    """更新迭代处理记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pdca.pdca_act_record WHERE id = %s", (record_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"迭代处理记录 {record_id} 不存在")

            update_fields = []
            params = []
            for field in ("problem_list", "rectify_plan", "bind_next_cycle_goal",
                          "is_freeze_experience", "new_config_version"):
                val = getattr(body, field, None)
                if val is not None:
                    update_fields.append(f"{field} = %s")
                    params.append(val)

            if not update_fields:
                return ApiResponse(code=200, message="success", data={"id": record_id})

            update_fields.append("updated_at = NOW()")
            params.append(record_id)
            cur.execute(
                f"UPDATE pdca.pdca_act_record SET {', '.join(update_fields)} WHERE id = %s",
                params,
            )
            conn.commit()
            logger.info("更新迭代处理记录 id=%s", record_id)
            return ApiResponse(code=200, message="success", data={"id": record_id})


@router.delete("/act-records/{record_id}", response_model=ApiResponse)
async def delete_act_record(record_id: int):
    """删除迭代处理记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pdca.pdca_act_record WHERE id = %s", (record_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"迭代处理记录 {record_id} 不存在")

            cur.execute("DELETE FROM pdca.pdca_act_record WHERE id = %s", (record_id,))
            conn.commit()
            logger.info("删除迭代处理记录 id=%s", record_id)
            return ApiResponse(code=200, message="success", data={"id": record_id})