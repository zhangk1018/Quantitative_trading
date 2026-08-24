"""
check_report.py - 复盘报告 CRUD API

Check 模块：复盘报告生成/查询/发布
- pdca_check_report 表与 pdca_cycle 为 1:1 关系（pdca_cycle_id 唯一约束）
- 支持 upsert（自动创建/更新）
- 支持 report_status 切换（draft → published）
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.error_codes import PDCAError
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["复盘报告"])


# ============================================================
# Pydantic 请求模型
# ============================================================

class CheckReportCreate(BaseModel):
    """创建/更新复盘报告"""
    pdca_cycle_id: int
    total_trade_count: Optional[int] = None
    complete_by_plan_count: Optional[int] = None
    execution_rate: Optional[float] = Field(None, ge=0, le=100)
    win_rate: Optional[float] = Field(None, ge=0, le=100)
    profit_loss_ratio: Optional[float] = None
    avg_entry_score: Optional[float] = Field(None, ge=0, le=100)
    avg_exit_score: Optional[float] = Field(None, ge=0, le=100)
    avg_trade_score: Optional[float] = Field(None, ge=0, le=100)
    max_drawdown: Optional[float] = None
    violation_total: Optional[int] = Field(None, ge=0)
    report_content: Optional[str] = None


class CheckReportUpdate(BaseModel):
    """更新复盘报告（部分字段）"""
    report_status: Optional[str] = Field(None, pattern="^(draft|published)$")
    total_trade_count: Optional[int] = None
    complete_by_plan_count: Optional[int] = None
    execution_rate: Optional[float] = Field(None, ge=0, le=100)
    win_rate: Optional[float] = Field(None, ge=0, le=100)
    profit_loss_ratio: Optional[float] = None
    avg_entry_score: Optional[float] = Field(None, ge=0, le=100)
    avg_exit_score: Optional[float] = Field(None, ge=0, le=100)
    avg_trade_score: Optional[float] = Field(None, ge=0, le=100)
    max_drawdown: Optional[float] = None
    violation_total: Optional[int] = Field(None, ge=0)
    report_content: Optional[str] = None


# ============================================================
# API 端点
# ============================================================

@router.get("/check-reports/{cycle_id}", response_model=ApiResponse)
async def get_check_report(cycle_id: int):
    """获取指定周期的复盘报告（1:1 关系）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pdca.pdca_check_report WHERE pdca_cycle_id = %s",
                (cycle_id,),
            )
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            if not row:
                # 返回空数据而非 404，前端可据此显示"未生成报告"状态
                return ApiResponse(code=200, message="success", data=None)
            return ApiResponse(code=200, message="success", data=dict(zip(columns, row)))


@router.post("/check-reports", response_model=ApiResponse, status_code=201)
async def create_check_report(body: CheckReportCreate):
    """创建复盘报告（pdca_cycle_id 唯一，重复创建自动覆盖）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 检查周期存在
            cur.execute("SELECT id, status FROM pdca.pdca_cycle WHERE id = %s", (body.pdca_cycle_id,))
            cycle = cur.fetchone()
            if not cycle:
                raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())
            if cycle[1] not in ("DO", "CHECK"):
                logger.warning("周期 %s 当前状态为 %s，非 DO/CHECK 阶段创建复盘报告", body.pdca_cycle_id, cycle[1])

            # 使用 INSERT ON CONFLICT 实现 upsert（pdca_cycle_id 有 UNIQUE 约束）
            cur.execute(
                """
                INSERT INTO pdca.pdca_check_report
                    (account_id, pdca_cycle_id, total_trade_count, complete_by_plan_count,
                     execution_rate, win_rate, profit_loss_ratio,
                     avg_entry_score, avg_exit_score, avg_trade_score,
                     max_drawdown, violation_total, report_content)
                VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pdca_cycle_id)
                DO UPDATE SET
                    total_trade_count = EXCLUDED.total_trade_count,
                    complete_by_plan_count = EXCLUDED.complete_by_plan_count,
                    execution_rate = EXCLUDED.execution_rate,
                    win_rate = EXCLUDED.win_rate,
                    profit_loss_ratio = EXCLUDED.profit_loss_ratio,
                    avg_entry_score = EXCLUDED.avg_entry_score,
                    avg_exit_score = EXCLUDED.avg_exit_score,
                    avg_trade_score = EXCLUDED.avg_trade_score,
                    max_drawdown = EXCLUDED.max_drawdown,
                    violation_total = EXCLUDED.violation_total,
                    report_content = EXCLUDED.report_content,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    body.pdca_cycle_id,
                    body.total_trade_count, body.complete_by_plan_count,
                    body.execution_rate, body.win_rate, body.profit_loss_ratio,
                    body.avg_entry_score, body.avg_exit_score, body.avg_trade_score,
                    body.max_drawdown, body.violation_total, body.report_content,
                ),
            )
            report_id = cur.fetchone()[0]
            conn.commit()
            logger.info("创建/更新复盘报告 id=%s, cycle=%s", report_id, body.pdca_cycle_id)
            return ApiResponse(code=200, message="success", data={"id": report_id, "pdca_cycle_id": body.pdca_cycle_id})


@router.put("/check-reports/{report_id}", response_model=ApiResponse)
async def update_check_report(report_id: int, body: CheckReportUpdate):
    """更新复盘报告（增量更新）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pdca.pdca_check_report WHERE id = %s", (report_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"复盘报告 {report_id} 不存在")

            update_fields = []
            params = []
            for field in (
                "report_status", "total_trade_count", "complete_by_plan_count",
                "execution_rate", "win_rate", "profit_loss_ratio",
                "avg_entry_score", "avg_exit_score", "avg_trade_score",
                "max_drawdown", "violation_total", "report_content",
            ):
                val = getattr(body, field, None)
                if val is not None:
                    update_fields.append(f"{field} = %s")
                    params.append(val)

            if not update_fields:
                return ApiResponse(code=200, message="success", data={"id": report_id})

            update_fields.append("updated_at = NOW()")
            params.append(report_id)
            cur.execute(
                f"UPDATE pdca.pdca_check_report SET {', '.join(update_fields)} WHERE id = %s",
                params,
            )
            conn.commit()
            logger.info("更新复盘报告 id=%s", report_id)
            return ApiResponse(code=200, message="success", data={"id": report_id})