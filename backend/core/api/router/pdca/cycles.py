"""
cycles.py - PDCA 周期 CRUD + 状态机引擎
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["PDCA周期"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================

class CycleCreate(BaseModel):
    cycle_name: str = Field(..., min_length=1, max_length=64)
    cycle_type: str = Field(..., pattern="^(day|week|month|quarter|year)$")
    start_date: date
    end_date: date
    goal_text: Optional[str] = None


class CycleUpdate(BaseModel):
    cycle_name: Optional[str] = Field(None, min_length=1, max_length=64)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    goal_text: Optional[str] = None


class CycleTransition(BaseModel):
    target_status: str = Field(..., pattern="^(PLAN|DO|CHECK|ACT)$")


# 有效状态流转映射
VALID_TRANSITIONS = {
    "PLAN": "DO",
    "DO": "CHECK",
    "CHECK": "ACT",
    "ACT": "PLAN",
}

# 每个流转对应的边界条件检查函数名
TRANSITION_CHECKS = {
    "PLAN": "DO",     # PLAN→DO: 检查交易计划
    "DO": "CHECK",    # DO→CHECK: 检查所有交易已平仓
    "CHECK": "ACT",   # CHECK→ACT: 检查复盘报告
    "ACT": "PLAN",    # ACT→PLAN: 自动创建下一周期
}


# ============================================================
# 辅助函数
# ============================================================

def _get_cycle_or_404(conn, cycle_id: int) -> dict:
    """获取周期，不存在则抛 404"""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM pdca.pdca_cycle WHERE id = %s", (cycle_id,))
        columns = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"周期 {cycle_id} 不存在")
        return dict(zip(columns, row))


def _check_plan_to_do(conn, cycle_id: int):
    """PLAN→DO: 检查周期内是否有交易计划"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pdca.trading_plan WHERE pdca_cycle_id = %s AND deleted_at IS NULL",
            (cycle_id,),
        )
        count = cur.fetchone()[0]
        if count == 0:
            raise HTTPException(
                status_code=400,
                detail="不允许从 PLAN 流转到 DO：周期内没有交易计划（pdca.trading_plan 至少一条）",
            )


def _check_do_to_check(conn, cycle_id: int):
    """DO→CHECK: 检查周期内所有交易是否已平仓"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pdca.trading_record "
            "WHERE pdca_cycle_id = %s AND deleted_at IS NULL AND exit_date IS NULL",
            (cycle_id,),
        )
        count = cur.fetchone()[0]
        if count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"不允许从 DO 流转到 CHECK：还有 {count} 笔交易未平仓（exit_date IS NULL）",
            )


def _check_check_to_act(conn, cycle_id: int):
    """CHECK→ACT: 检查复盘报告是否已填写"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pdca.pdca_check_report WHERE pdca_cycle_id = %s",
            (cycle_id,),
        )
        count = cur.fetchone()[0]
        if count == 0:
            raise HTTPException(
                status_code=400,
                detail="不允许从 CHECK 流转到 ACT：未填写复盘报告（pdca.pdca_check_report 不存在）",
            )


def _check_act_to_plan(conn, cycle_id: int):
    """ACT→PLAN: 自动创建下一个周期的草稿，链接 prev_cycle_id"""
    with conn.cursor() as cur:
        # 获取当前周期信息
        cur.execute(
            "SELECT * FROM pdca.pdca_cycle WHERE id = %s",
            (cycle_id,),
        )
        columns = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"周期 {cycle_id} 不存在")
        cycle = dict(zip(columns, row))

        # 计算下一个周期的起止日期（按周期类型自动推算）
        from datetime import timedelta

        next_start = cycle["end_date"] + timedelta(days=1)
        cycle_type = cycle["cycle_type"]
        if cycle_type == "day":
            next_end = next_start
        elif cycle_type == "week":
            next_end = next_start + timedelta(days=6)
        elif cycle_type == "month":
            # 下个月的同一天减1天
            month = next_start.month + 1
            year = next_start.year
            if month > 12:
                month = 1
                year += 1
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            try:
                next_end = next_start.replace(year=year, month=month, day=min(next_start.day, last_day))
            except ValueError:
                next_end = next_start.replace(year=year, month=month, day=last_day)
        elif cycle_type == "quarter":
            next_end = next_start + timedelta(days=89)
        else:  # year
            next_end = next_start.replace(year=next_start.year + 1) - timedelta(days=1)

        # 自动生成周期名称
        next_name = f"{cycle['cycle_name']}-续"

        cur.execute(
            "INSERT INTO pdca.pdca_cycle "
            "(account_id, prev_cycle_id, cycle_type, cycle_name, status, start_date, end_date, goal_text) "
            "VALUES (%s, %s, %s, %s, 'PLAN', %s, %s, %s) RETURNING id",
            (
                cycle.get("account_id", 1),
                cycle_id,
                cycle_type,
                next_name,
                next_start,
                next_end,
                cycle.get("goal_text", ""),
            ),
        )
        new_id = cur.fetchone()[0]
        logger.info("ACT→PLAN 自动创建下一周期 id=%s, name=%s, %s~%s", new_id, next_name, next_start, next_end)


# 边界条件检查映射
TRANSITION_CHECK_FUNCS = {
    ("PLAN", "DO"): _check_plan_to_do,
    ("DO", "CHECK"): _check_do_to_check,
    ("CHECK", "ACT"): _check_check_to_act,
    ("ACT", "PLAN"): _check_act_to_plan,
}


# ============================================================
# API 端点
# ============================================================

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


@router.post("", response_model=ApiResponse, status_code=201)
async def create_cycle(body: CycleCreate):
    """新建 PDCA 周期"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pdca.pdca_cycle "
                "(account_id, cycle_type, cycle_name, status, start_date, end_date, goal_text) "
                "VALUES (1, %s, %s, 'PLAN', %s, %s, %s) RETURNING id",
                (body.cycle_type, body.cycle_name, body.start_date, body.end_date, body.goal_text),
            )
            new_id = cur.fetchone()[0]
            logger.info("创建 PDCA 周期 id=%s, name=%s", new_id, body.cycle_name)
            return ApiResponse(code=200, message="success", data={"id": new_id})


@router.put("/{cycle_id}", response_model=ApiResponse)
async def update_cycle(cycle_id: int, body: CycleUpdate):
    """更新 PDCA 周期（仅 PLAN 状态可修改）"""
    with get_db() as conn:
        cycle = _get_cycle_or_404(conn, cycle_id)

        if cycle["status"] != "PLAN":
            raise HTTPException(
                status_code=400,
                detail=f"不允许修改：当前状态为 {cycle['status']}，仅 PLAN 状态可修改",
            )

        # 构建动态 UPDATE 语句（仅更新非 None 字段）
        update_fields = []
        params = []
        for field in ("cycle_name", "start_date", "end_date", "goal_text"):
            val = getattr(body, field, None)
            if val is not None:
                update_fields.append(f"{field} = %s")
                params.append(val)

        if not update_fields:
            raise HTTPException(status_code=400, detail="没有需要更新的字段")

        update_fields.append("updated_at = NOW()")
        params.append(cycle_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE pdca.pdca_cycle SET {', '.join(update_fields)} WHERE id = %s",
                params,
            )
            logger.info("更新 PDCA 周期 id=%s，字段=%s", cycle_id, [f.split(" ")[0] for f in update_fields if "=" in f])
            return ApiResponse(code=200, message="success", data={"id": cycle_id})


@router.delete("/{cycle_id}", response_model=ApiResponse)
async def delete_cycle(cycle_id: int):
    """删除 PDCA 周期（仅 PLAN 状态，且无关联记录时可删除）"""
    with get_db() as conn:
        cycle = _get_cycle_or_404(conn, cycle_id)

        if cycle["status"] != "PLAN":
            raise HTTPException(
                status_code=400,
                detail=f"不允许删除：当前状态为 {cycle['status']}，仅 PLAN 状态可删除",
            )

        # 检查是否有关联交易记录
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM pdca.trading_record WHERE pdca_cycle_id = %s AND deleted_at IS NULL",
                (cycle_id,),
            )
            trade_count = cur.fetchone()[0]
            if trade_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"不允许删除：周期下有 {trade_count} 条关联交易记录",
                )

            # 检查是否有关联交易计划
            cur.execute(
                "SELECT COUNT(*) FROM pdca.trading_plan WHERE pdca_cycle_id = %s AND deleted_at IS NULL",
                (cycle_id,),
            )
            plan_count = cur.fetchone()[0]
            if plan_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"不允许删除：周期下有 {plan_count} 条关联交易计划",
                )

            # 物理删除
            cur.execute("DELETE FROM pdca.pdca_cycle WHERE id = %s", (cycle_id,))
            logger.info("删除 PDCA 周期 id=%s, name=%s", cycle_id, cycle.get("cycle_name"))
            return ApiResponse(code=200, message="success", data={"id": cycle_id})


@router.put("/{cycle_id}/transition", response_model=ApiResponse)
async def transition_cycle(cycle_id: int, body: CycleTransition):
    """PDCA 状态机流转"""
    target = body.target_status

    with get_db() as conn:
        cycle = _get_cycle_or_404(conn, cycle_id)
        current = cycle["status"]

        # 检查流转是否合法
        expected_target = VALID_TRANSITIONS.get(current)
        if expected_target is None:
            raise HTTPException(
                status_code=400,
                detail=f"未知的当前状态：{current}",
            )
        if target != expected_target:
            raise HTTPException(
                status_code=400,
                detail=f"不允许从 {current} 直接跳转到 {target}，只允许 {current} → {expected_target}",
            )

        # 执行边界条件检查
        check_func = TRANSITION_CHECK_FUNCS.get((current, target))
        if check_func:
            check_func(conn, cycle_id)

        # 更新状态
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pdca.pdca_cycle SET status = %s, updated_at = NOW() WHERE id = %s",
                (target, cycle_id),
            )
            logger.info("PDCA 周期 id=%s 状态流转: %s → %s", cycle_id, current, target)
            return ApiResponse(code=200, message="success", data={
                "id": cycle_id,
                "from_status": current,
                "to_status": target,
            })