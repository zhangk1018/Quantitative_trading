"""
behavior_log.py - 行为 & 违规日志 API

Do 模块增强：记录和查询交易行为日志（违规记录、正常行为日志）
- 支持按 pdca_cycle_id 查询（一个周期可有多条日志）
- 支持按 log_type/violation_type 过滤
- 支持时间范围过滤
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.error_codes import PDCAError
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["行为日志"])


# ============================================================
# Pydantic 请求模型
# ============================================================

class BehaviorLogCreate(BaseModel):
    pdca_cycle_id: int
    trading_record_id: Optional[int] = None
    log_type: str = Field(..., pattern="^(normal|violation)$")
    violation_type: Optional[str] = Field(None, pattern="^(C_class_trade|over_position|no_plan_trade|cancel_stop_loss)$")
    severity: str = Field("medium", pattern="^(low|medium|high|critical)$")
    log_content: str = Field(..., min_length=1)
    happened_at: Optional[str] = None  # 可选，默认当前时间


class BehaviorLogUpdate(BaseModel):
    log_content: Optional[str] = None
    violation_type: Optional[str] = Field(None, pattern="^(C_class_trade|over_position|no_plan_trade|cancel_stop_loss)$")
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")


# ============================================================
# API 端点 — 注意：静态路径必须在参数化路径之前定义
# ============================================================

@router.get("/behavior-logs/types", response_model=ApiResponse)
async def list_behavior_log_types():
    """获取行为日志支持的枚举类型值"""
    return ApiResponse(code=200, message="success", data={
        "log_types": ["normal", "violation"],
        "violation_types": ["C_class_trade", "over_position", "no_plan_trade", "cancel_stop_loss"],
        "severities": ["low", "medium", "high", "critical"],
    })


@router.get("/behavior-logs/{cycle_id}", response_model=ApiResponse)
async def list_behavior_logs(
    cycle_id: int,
    log_type: Optional[str] = Query(None, pattern="^(normal|violation)$"),
    violation_type: Optional[str] = Query(None, pattern="^(C_class_trade|over_position|no_plan_trade|cancel_stop_loss)$"),
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    """获取指定周期的行为日志，支持按类型/时间过滤"""
    with get_db() as conn:
        with conn.cursor() as cur:
            where_clauses = ["pdca_cycle_id = %s"]
            params = [cycle_id]

            if log_type:
                where_clauses.append("log_type = %s")
                params.append(log_type)
            if violation_type:
                where_clauses.append("violation_type = %s")
                params.append(violation_type)
            if date_from:
                where_clauses.append("happened_at >= %s::timestamp")
                params.append(date_from)
            if date_to:
                where_clauses.append("happened_at <= %s::timestamp + interval '1 day'")
                params.append(date_to)

            cur.execute(
                f"SELECT * FROM pdca.behavior_log WHERE {' AND '.join(where_clauses)} ORDER BY happened_at DESC",
                params,
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("/behavior-logs", response_model=ApiResponse, status_code=201)
async def create_behavior_log(body: BehaviorLogCreate):
    """创建行为/违规日志"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 检查周期存在
            cur.execute("SELECT id, status FROM pdca.pdca_cycle WHERE id = %s", (body.pdca_cycle_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())

            # 如果有 trading_record_id，检查记录存在
            if body.trading_record_id:
                cur.execute("SELECT id FROM pdca.trading_record WHERE id = %s", (body.trading_record_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail=f"交易记录 {body.trading_record_id} 不存在")

            happened_at = body.happened_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                """
                INSERT INTO pdca.behavior_log
                    (account_id, pdca_cycle_id, trading_record_id, log_type,
                     violation_type, severity, log_content, happened_at)
                VALUES (1, %s, %s, %s, %s, %s, %s, %s::timestamp)
                RETURNING id
                """,
                (
                    body.pdca_cycle_id, body.trading_record_id, body.log_type,
                    body.violation_type, body.severity, body.log_content, happened_at,
                ),
            )
            log_id = cur.fetchone()[0]
            conn.commit()
            logger.info("创建行为日志 id=%s, cycle=%s, type=%s", log_id, body.pdca_cycle_id, body.log_type)
            return ApiResponse(code=200, message="success", data={"id": log_id})


@router.put("/behavior-logs/{log_id}", response_model=ApiResponse)
async def update_behavior_log(log_id: int, body: BehaviorLogUpdate):
    """更新行为日志内容"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pdca.behavior_log WHERE id = %s", (log_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"行为日志 {log_id} 不存在")

            update_fields = []
            params = []
            for field in ("log_content", "violation_type", "severity"):
                val = getattr(body, field, None)
                if val is not None:
                    update_fields.append(f"{field} = %s")
                    params.append(val)

            if not update_fields:
                return ApiResponse(code=200, message="success", data={"id": log_id})

            params.append(log_id)
            cur.execute(
                f"UPDATE pdca.behavior_log SET {', '.join(update_fields)} WHERE id = %s",
                params,
            )
            conn.commit()
            logger.info("更新行为日志 id=%s", log_id)
            return ApiResponse(code=200, message="success", data={"id": log_id})


@router.delete("/behavior-logs/{log_id}", response_model=ApiResponse)
async def delete_behavior_log(log_id: int):
    """删除行为日志"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pdca.behavior_log WHERE id = %s", (log_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"行为日志 {log_id} 不存在")

            cur.execute("DELETE FROM pdca.behavior_log WHERE id = %s", (log_id,))
            conn.commit()
            logger.info("删除行为日志 id=%s", log_id)
            return ApiResponse(code=200, message="success", data={"id": log_id})