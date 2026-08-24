"""
plans.py - 交易计划 CRUD + 风控校验

规则（对应《PDCA交付物三》PL-001~PL-008）：
- PL-001 必填字段校验（周线分析/日线分析/入场价/止损价/风险比例/数量）
- PL-003 C 类标的禁止创建交易计划
- PL-004 单笔风险比例不得超过 risk_per_trade（默认 2%）
- PL-006/007 止损价方向校验（多头止损 < 入场价，空头止损 > 入场价）

推荐索引（需在数据库端创建）：
- pdca.trading_plan: (code, deleted_at) WHERE deleted_at IS NULL
- pdca.trading_plan: (pdca_cycle_id, deleted_at) WHERE deleted_at IS NULL
- pdca.pdca_cycle: (id, deleted_at) WHERE deleted_at IS NULL
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.error_codes import PDCAError
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["交易计划"])


# ============================================================
# Pydantic 模型
# ============================================================

class PlanCreate(BaseModel):
    pdca_cycle_id: int
    template_id: Optional[int] = None
    code: str = Field(..., min_length=1, max_length=32)
    security_name: Optional[str] = None
    long_short: str = Field(..., pattern="^(long|short)$")
    weekly_view: str
    daily_view: str
    entry_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    target_price: Optional[float] = Field(None, gt=0)
    max_risk_rate: float = Field(..., gt=0, le=1.0)
    plan_quantity: int = Field(..., gt=0)
    abort_condition: Optional[str] = None


class PlanUpdate(BaseModel):
    template_id: Optional[int] = None
    long_short: Optional[str] = Field(None, pattern="^(long|short)$")
    weekly_view: Optional[str] = None
    daily_view: Optional[str] = None
    entry_price: Optional[float] = Field(None, gt=0)
    stop_loss_price: Optional[float] = Field(None, gt=0)
    target_price: Optional[float] = Field(None, gt=0)
    max_risk_rate: Optional[float] = Field(None, gt=0, le=1.0)
    plan_quantity: Optional[int] = Field(None, gt=0)
    abort_condition: Optional[str] = None


# ============================================================
# 辅助函数
# ============================================================

def _get_plan_or_404(conn, plan_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM pdca.trading_plan WHERE id = %s AND deleted_at IS NULL",
            (plan_id,),
        )
        columns = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"交易计划 {plan_id} 不存在")
        return dict(zip(columns, row))


def _get_cycle(conn, cycle_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM pdca.pdca_cycle WHERE id = %s",
            (cycle_id,),
        )
        columns = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())
        return dict(zip(columns, row))


def _check_c_class(conn, code: str):
    """PL-003: C 类标的禁止创建交易计划"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tag FROM pdca.security_tag "
            "WHERE code = %s AND deleted_at IS NULL",
            (code,),
        )
        row = cur.fetchone()
        if row and row[0] == "C":
            raise HTTPException(
                status_code=400,
                detail=f"C 类标的禁止创建交易计划（code={code}），请先调整 ABC 分类",
            )


def _check_stop_loss_direction(long_short: str, entry_price: float, stop_loss_price: float):
    """PL-006/007: 止损价方向校验"""
    if long_short == "long" and stop_loss_price >= entry_price:
        raise HTTPException(status_code=400, detail="多头止损价必须低于入场价")
    if long_short == "short" and stop_loss_price <= entry_price:
        raise HTTPException(status_code=400, detail="空头止损价必须高于入场价")


def _check_risk(conn, max_risk_rate: float):
    """PL-004: 单笔风险比例不得超过 risk_per_trade（默认 2%）"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT numeric_value FROM pdca.system_config "
            "WHERE config_key = 'risk_per_trade' "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
    limit = float(row[0]) if row and row[0] is not None else 0.02
    if max_risk_rate > limit:
        raise HTTPException(
            status_code=400,
            detail=f"单笔风险比例 {max_risk_rate:.2%} 超过上限 {limit:.2%}（risk_per_trade），请调整计划数量或止损价",
        )


def _validate_plan(conn, body):
    """计划创建/更新前的统一校验"""
    # 必填文本字段（PL-001）
    if not body.weekly_view or not body.weekly_view.strip():
        raise HTTPException(status_code=400, detail="周线分析（weekly_view）为必填项")
    if not body.daily_view or not body.daily_view.strip():
        raise HTTPException(status_code=400, detail="日线分析（daily_view）为必填项")
    if body.plan_quantity <= 0:
        raise HTTPException(status_code=400, detail="计划数量必须大于 0")
    if body.max_risk_rate <= 0:
        raise HTTPException(status_code=400, detail="风险比例必须大于 0")
    if body.entry_price <= 0:
        raise HTTPException(status_code=400, detail="入场价必须大于 0")
    if body.stop_loss_price <= 0:
        raise HTTPException(status_code=400, detail="止损价必须大于 0")

    # C 类拦截（PL-003）
    _check_c_class(conn, body.code)
    # 止损方向（PL-006/007）
    _check_stop_loss_direction(body.long_short, body.entry_price, body.stop_loss_price)
    # 单笔风险（PL-004）
    _check_risk(conn, body.max_risk_rate)


# ============================================================
# API 端点
# ============================================================

@router.get("/templates", response_model=ApiResponse)
async def list_templates():
    """获取交易计划模板列表（短线/中线/长线，FR-P07）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, template_name, template_type, required_fields, default_values, is_system "
                "FROM pdca.plan_template ORDER BY id"
            )
            columns = [desc[0] for desc in cur.description]
            items = []
            for row in cur.fetchall():
                item = dict(zip(columns, row))
                # 兼容默认值可能为 None
                item["default_values"] = item.get("default_values")
                items.append(item)
            return ApiResponse(code=200, message="success", data={"items": items})


@router.get("", response_model=ApiResponse)
async def list_plans(
    cycle_id: Optional[int] = Query(None),
    code: Optional[str] = Query(None),
):
    """获取交易计划列表（可按周期/股票筛选，JOIN 周期名称避免 N+1）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT p.*, c.cycle_name
                FROM pdca.trading_plan p
                LEFT JOIN pdca.pdca_cycle c ON c.id = p.pdca_cycle_id
                WHERE p.deleted_at IS NULL
            """
            params = []
            if cycle_id is not None:
                sql += " AND p.pdca_cycle_id = %s"
                params.append(cycle_id)
            if code:
                sql += " AND p.code = %s"
                params.append(code)
            sql += " ORDER BY p.created_at DESC"
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("", response_model=ApiResponse, status_code=201)
async def create_plan(body: PlanCreate):
    """新建交易计划"""
    with get_db() as conn:
        _get_cycle(conn, body.pdca_cycle_id)  # 校验周期存在
        _validate_plan(conn, body)

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pdca.trading_plan "
                "(account_id, pdca_cycle_id, template_id, code, security_name, long_short, "
                " weekly_view, daily_view, entry_price, stop_loss_price, target_price, "
                " max_risk_rate, plan_quantity, abort_condition) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    1, body.pdca_cycle_id, body.template_id, body.code, body.security_name,
                    body.long_short, body.weekly_view, body.daily_view, body.entry_price,
                    body.stop_loss_price, body.target_price, body.max_risk_rate,
                    body.plan_quantity, body.abort_condition,
                ),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            logger.info("创建交易计划 id=%s, code=%s, cycle=%s", new_id, body.code, body.pdca_cycle_id)
            return ApiResponse(code=200, message="success", data={"id": new_id})


@router.put("/{plan_id}", response_model=ApiResponse)
async def update_plan(plan_id: int, body: PlanUpdate):
    """更新交易计划（仅当关联周期处于 PLAN 状态）"""
    with get_db() as conn:
        plan = _get_plan_or_404(conn, plan_id)
        cycle = _get_cycle(conn, plan["pdca_cycle_id"])
        if cycle["status"] != "PLAN":
            raise HTTPException(
                status_code=400,
                detail=f"不允许修改交易计划：当前周期状态为 {cycle['status']}，仅 PLAN 状态可修改",
            )

        # 合并字段用于统一校验（使用 is not None 避免 or 吞掉 0 等假值）
        effective = {
            "code": plan["code"],
            "long_short": body.long_short if body.long_short is not None else plan["long_short"],
            "weekly_view": body.weekly_view if body.weekly_view is not None else plan["weekly_view"],
            "daily_view": body.daily_view if body.daily_view is not None else plan["daily_view"],
            "entry_price": float(body.entry_price) if body.entry_price is not None else float(plan["entry_price"]),
            "stop_loss_price": float(body.stop_loss_price) if body.stop_loss_price is not None else float(plan["stop_loss_price"]),
            "max_risk_rate": float(body.max_risk_rate) if body.max_risk_rate is not None else float(plan["max_risk_rate"]),
            "plan_quantity": body.plan_quantity if body.plan_quantity is not None else plan["plan_quantity"],
        }
        _check_c_class(conn, effective["code"])
        _check_stop_loss_direction(effective["long_short"], effective["entry_price"], effective["stop_loss_price"])
        # 更新时若修改了风险比例则校验
        if body.max_risk_rate is not None:
            _check_risk(conn, body.max_risk_rate)

        update_fields = []
        params = []
        for field in ("template_id", "long_short", "weekly_view", "daily_view",
                      "entry_price", "stop_loss_price", "target_price",
                      "max_risk_rate", "plan_quantity", "abort_condition"):
            val = getattr(body, field, None)
            if val is not None:
                update_fields.append(f"{field} = %s")
                params.append(val)
        if not update_fields:
            raise HTTPException(status_code=400, detail="没有需要更新的字段")
        update_fields.append("updated_at = NOW()")
        params.append(plan_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE pdca.trading_plan SET {', '.join(update_fields)} WHERE id = %s",
                params,
            )
            logger.info("更新交易计划 id=%s", plan_id)
            return ApiResponse(code=200, message="success", data={"id": plan_id})


@router.delete("/{plan_id}", response_model=ApiResponse)
async def delete_plan(plan_id: int):
    """删除交易计划（软删除，仅当关联周期处于 PLAN 状态）"""
    with get_db() as conn:
        plan = _get_plan_or_404(conn, plan_id)
        cycle = _get_cycle(conn, plan["pdca_cycle_id"])
        if cycle["status"] != "PLAN":
            raise HTTPException(
                status_code=400,
                detail=f"不允许删除交易计划：当前周期状态为 {cycle['status']}，仅 PLAN 状态可删除",
            )
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pdca.trading_plan SET deleted_at = NOW() WHERE id = %s",
                (plan_id,),
            )
            logger.info("删除交易计划 id=%s", plan_id)
            return ApiResponse(code=200, message="success", data={"id": plan_id})