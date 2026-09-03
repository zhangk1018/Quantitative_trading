"""
cycles.py - PDCA 周期 CRUD + 状态机引擎
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.error_codes import PDCAError
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
    target_status: str = Field(..., pattern="^(PLAN|DO|CHECK|ACT|DONE)$")


# 终态（已闭环）：ACT 结束后进入，仅可查看/统计，不可再流转、修改、加计划
TERMINAL_STATUS = "DONE"

# 有效状态流转映射（终态 DONE 不作为 key，天然不可继续流转）
VALID_TRANSITIONS = {
    "PLAN": "DO",
    "DO": "CHECK",
    "CHECK": "ACT",
    "ACT": "DONE",
}

# 每个流转对应的边界条件检查函数名
TRANSITION_CHECKS = {
    "PLAN": "DO",     # PLAN→DO: 检查交易计划
    "DO": "CHECK",    # DO→CHECK: 允许未平仓持仓结转，不强制全平仓
    "CHECK": "ACT",   # CHECK→ACT: 检查复盘报告
    "ACT": "DONE",    # ACT→DONE: 进入终态「已闭环」，不再自动创建下一周期
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
            raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())
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
    """DO→CHECK: 允许存在未平仓持仓（自动结转下周期），复盘聚焦已了结交易。

    需求③：未平仓持仓不阻塞进入 CHECK。复盘统计口径——未平仓不计入毛盈亏
    （gross_profit 仅由已落库的卖出子单累计），此处仅提示、不拦截。
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pdca.trading_record "
            "WHERE pdca_cycle_id = %s AND deleted_at IS NULL AND exit_date IS NULL",
            (cycle_id,),
        )
        open_count = cur.fetchone()[0]
        if open_count > 0:
            logger.info(
                "DO→CHECK：周期 %s 有 %s 笔未平仓持仓，允许结转下周期（不计入已实现盈亏）",
                cycle_id, open_count,
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


def _check_act_to_done(conn, cycle_id: int):
    """ACT→DONE: 终止当前周期，进入终态「已闭环」。

    需求①：取消自动续期——不再 INSERT 新周期、不再把旧周期重置为 PLAN。
    旧周期置为 DONE（终态，仅查看/统计），新周期由用户手动 POST /cycles 创建。
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM pdca.pdca_cycle WHERE id = %s",
            (cycle_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())
        if row[0] != "ACT":
            raise HTTPException(
                status_code=400,
                detail=f"仅 ACT（改进中）状态可进入终态，当前为 {row[0]}",
            )


# 边界条件检查映射
TRANSITION_CHECK_FUNCS = {
    ("PLAN", "DO"): _check_plan_to_do,
    ("DO", "CHECK"): _check_do_to_check,
    ("CHECK", "ACT"): _check_check_to_act,
    ("ACT", "DONE"): _check_act_to_done,
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
    """删除 PDCA 周期（级联删除关联记录、计划、日记，解除引用约束）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 删除关联交易记录（exit_slip 自动级联删除，diary/log 的 record_id 自动 SET NULL）
            #    trading_record.pdca_cycle_id 为 NOT NULL，不能 SET NULL，只能 DELETE
            cur.execute(
                "SELECT COUNT(*) FROM pdca.trading_record WHERE pdca_cycle_id = %s AND deleted_at IS NULL",
                (cycle_id,),
            )
            record_count = cur.fetchone()[0]
            cur.execute(
                "DELETE FROM pdca.trading_record WHERE pdca_cycle_id = %s",
                (cycle_id,),
            )
            logger.info("从周期 id=%s 删除 %s 条交易记录", cycle_id, record_count)

            # 2. 删除关联的交易计划（物理删除）
            cur.execute("DELETE FROM pdca.trading_plan WHERE pdca_cycle_id = %s", (cycle_id,))
            plan_deleted = cur.rowcount
            logger.info("从周期 id=%s 删除 %s 条交易计划", cycle_id, plan_deleted)

            # 3. 物理删除周期（trading_diary 的 fk_diary_cycle 为 ON DELETE CASCADE，自动级联删除）
            cur.execute("DELETE FROM pdca.pdca_cycle WHERE id = %s", (cycle_id,))
            logger.info("删除 PDCA 周期 id=%s", cycle_id)
            return ApiResponse(code=200, message="success", data={
                "id": cycle_id,
                "records_deleted": record_count,
                "plans_deleted": plan_deleted,
            })


@router.get("/{cycle_id}/execution-summary", response_model=ApiResponse)
async def execution_summary(cycle_id: int):
    """获取周期执行跟踪摘要（Do 模块增强）：对比交易计划 vs 实际执行情况"""
    with get_db() as conn:
        cycle = _get_cycle_or_404(conn, cycle_id)

        with conn.cursor() as cur:
            # 获取周期内所有交易计划（含软删除和已取消的）
            cur.execute(
                "SELECT * FROM pdca.trading_plan "
                "WHERE pdca_cycle_id = %s AND deleted_at IS NULL AND plan_status != 'cancelled' "
                "ORDER BY created_at",
                (cycle_id,),
            )
            plan_columns = [desc[0] for desc in cur.description]
            plan_rows = cur.fetchall()

            # 获取周期内所有交易记录（含关联 trading_plan_id）
            cur.execute(
                "SELECT * FROM pdca.trading_record "
                "WHERE pdca_cycle_id = %s AND deleted_at IS NULL "
                "ORDER BY entry_date",
                (cycle_id,),
            )
            record_columns = [desc[0] for desc in cur.description]
            record_rows = cur.fetchall()
            records = [dict(zip(record_columns, r)) for r in record_rows]

            # 按 trading_plan_id 建立索引
            records_by_plan_id: dict[int, list[dict]] = {}
            for rec in records:
                pid = rec.get("trading_plan_id")
                if pid is not None:
                    records_by_plan_id.setdefault(pid, []).append(rec)

            # 按 code 索引未关联计划的记录
            records_no_plan = [r for r in records if r.get("trading_plan_id") is None]

            # 构建计划执行明细
            details = []
            executed_count = 0
            for row in plan_rows:
                plan = dict(zip(plan_columns, row))
                plan_id = plan["id"]
                matched_records = records_by_plan_id.get(plan_id, [])

                # 计算执行状态
                total_planned_qty = plan["plan_quantity"]
                total_executed_qty = sum(r["quantity"] for r in matched_records)
                fill_rate = min(total_executed_qty / total_planned_qty, 1.0) if total_planned_qty > 0 else 0.0

                # 实际平均入场价
                if matched_records:
                    avg_entry = sum(r["entry_price"] * r["quantity"] for r in matched_records) / total_executed_qty
                    first_entry_date = matched_records[0]["entry_date"]
                else:
                    avg_entry = None
                    first_entry_date = None

                # 计划盈亏状态
                is_executed = len(matched_records) > 0
                if is_executed:
                    executed_count += 1

                status = "executed" if is_executed else "pending"

                details.append({
                    "plan_id": plan_id,
                    "code": plan["code"],
                    "security_name": plan.get("security_name"),
                    "long_short": plan["long_short"],
                    "plan_entry_price": float(plan["entry_price"]),
                    "plan_stop_loss": float(plan["stop_loss_price"]),
                    "plan_quantity": plan["plan_quantity"],
                    "plan_status": plan["plan_status"],
                    "execution_status": status,
                    "actual_entry_price": float(avg_entry) if avg_entry else None,
                    "actual_quantity": total_executed_qty,
                    "fill_rate": round(fill_rate, 4),
                    "matched_records": len(matched_records),
                    "first_entry_date": str(first_entry_date) if first_entry_date else None,
                    "price_deviation": round(float(avg_entry) - float(plan["entry_price"]), 4)
                    if avg_entry else None,
                })

            # 无计划裸交易
            naked_trades = []
            for rec in records_no_plan:
                naked_trades.append({
                    "record_id": rec["id"],
                    "code": rec["code"],
                    "security_name": rec.get("security_name"),
                    "entry_date": str(rec["entry_date"]),
                    "entry_price": float(rec["entry_price"]),
                    "quantity": rec["quantity"],
                    "trigger_source": rec.get("trigger_source"),
                })

            total_plans = len(details)
            pending_plans = total_plans - executed_count

            return ApiResponse(code=200, message="success", data={
                "cycle_id": cycle_id,
                "cycle_name": cycle["cycle_name"],
                "cycle_status": cycle["status"],
                "total_plans": total_plans,
                "executed_plans": executed_count,
                "pending_plans": pending_plans,
                "total_trades": len(records),
                "naked_trades": len(naked_trades),
                "fill_rate": round(executed_count / total_plans, 4) if total_plans > 0 else 0,
                "details": details,
                "naked_trade_details": naked_trades,
            })


@router.put("/{cycle_id}/transition", response_model=ApiResponse)
async def transition_cycle(cycle_id: int, body: CycleTransition):
    """PDCA 状态机流转"""
    target = body.target_status

    with get_db() as conn:
        cycle = _get_cycle_or_404(conn, cycle_id)
        current = cycle["status"]

        # 终态周期不可再流转（仅查看/统计）
        if current == TERMINAL_STATUS:
            raise HTTPException(
                status_code=400,
                detail=f"周期已进入终态「已闭环」，仅可查看/统计，不可再流转（id={cycle_id}）",
            )

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