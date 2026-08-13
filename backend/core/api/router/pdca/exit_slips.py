"""
exit_slips.py - 退出子单 API（一买多卖分批卖出）
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["退出子单"])


class ExitSlipCreate(BaseModel):
    exit_date: date
    exit_price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    commission: float = 0
    exit_reason: Optional[str] = None
    exit_score: Optional[float] = None
    actual_stop_loss: Optional[float] = None
    slip_point: float = 0


class ExitSlipUpdate(BaseModel):
    exit_date: Optional[date] = None
    exit_price: Optional[float] = Field(None, gt=0)
    quantity: Optional[int] = Field(None, gt=0)
    commission: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_score: Optional[float] = None
    actual_stop_loss: Optional[float] = None
    slip_point: Optional[float] = None


class ExitSlipBatchCreate(BaseModel):
    slips: list[ExitSlipCreate]


@router.get("/records/{record_id}/exit-slips", response_model=ApiResponse)
async def list_exit_slips(record_id: int):
    """获取某买入单的所有卖出子单"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pdca.trading_exit_slip WHERE record_id = %s AND deleted_at IS NULL ORDER BY exit_date ASC, id ASC",
                (record_id,),
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("/records/{record_id}/exit-slips/batch", response_model=ApiResponse)
async def batch_create_exit_slips(record_id: int, batch: ExitSlipBatchCreate):
    """批量新增卖出子单，事务内完成 remain_qty 更新 + gross_profit 重算"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 检查买入单存在且剩余持仓充足
            cur.execute(
                "SELECT id, quantity, remain_qty, entry_price, commission_entry FROM pdca.trading_record WHERE id = %s AND deleted_at IS NULL",
                (record_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="40011: 交易记录不存在")
            _, total_qty, remain_qty, entry_price, commission_entry = row
            if remain_qty is None:
                remain_qty = total_qty

            # 2. 校验总卖出数量不超过 remain_qty
            total_sell_qty = sum(s.quantity for s in batch.slips)
            if total_sell_qty > remain_qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"40013: 卖出数量 {total_sell_qty} 超过剩余持仓 {remain_qty}",
                )

            # 3. 批量插入子单
            for slip in batch.slips:
                cur.execute(
                    """INSERT INTO pdca.trading_exit_slip
                       (record_id, exit_date, exit_price, quantity, commission, exit_reason, exit_score, actual_stop_loss, slip_point)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (record_id, slip.exit_date, slip.exit_price, slip.quantity,
                     slip.commission, slip.exit_reason, slip.exit_score,
                     slip.actual_stop_loss, slip.slip_point),
                )

            # 4. 更新 remain_qty
            new_remain = remain_qty - total_sell_qty
            cur.execute("UPDATE pdca.trading_record SET remain_qty = %s WHERE id = %s", (new_remain, record_id))

            # 5. 重算 gross_profit（聚合所有子单利润）
            cur.execute(
                """SELECT COALESCE(SUM(
                    (exit_price::numeric - %s) * quantity - commission
                ), 0) FROM pdca.trading_exit_slip
                   WHERE record_id = %s AND deleted_at IS NULL""",
                (entry_price, record_id),
            )
            total_profit = float(cur.fetchone()[0]) - float(commission_entry)
            cur.execute("UPDATE pdca.trading_record SET gross_profit = %s WHERE id = %s", (round(total_profit, 4), record_id))

            conn.commit()
            return ApiResponse(code=200, message="success", data={
                "record_id": record_id, "remain_qty": new_remain, "gross_profit": round(total_profit, 4),
            })


@router.put("/exit-slips/{slip_id}", response_model=ApiResponse)
async def update_exit_slip(slip_id: int, slip: ExitSlipUpdate):
    """修改卖出子单，同时重算对应买入单的 remain_qty 和 gross_profit"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 检查子单存在
            cur.execute(
                "SELECT es.*, r.entry_price, r.commission_entry FROM pdca.trading_exit_slip es "
                "JOIN pdca.trading_record r ON es.record_id = r.id "
                "WHERE es.id = %s AND es.deleted_at IS NULL AND r.deleted_at IS NULL",
                (slip_id,),
            )
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="40011: 卖出子单不存在")
            slip_data = dict(zip(columns, row))
            entry_price = slip_data["entry_price"]
            commission_entry = slip_data["commission_entry"]
            record_id = slip_data["record_id"]
            old_qty = slip_data["quantity"]

            # 2. 构建动态更新
            updates = {}
            for field in ("exit_date", "exit_price", "quantity", "commission",
                          "exit_reason", "exit_score", "actual_stop_loss", "slip_point"):
                val = getattr(slip, field, None)
                if val is not None:
                    updates[field] = val

            new_qty = updates.get("quantity", old_qty)

            if not updates:
                return ApiResponse(code=200, message="success", data={"id": slip_id})

            set_clauses = [f"{k} = %s" for k in updates]
            set_clauses.append("updated_at = NOW()")
            values = list(updates.values())
            values.append(slip_id)

            cur.execute(
                f"UPDATE pdca.trading_exit_slip SET {', '.join(set_clauses)} WHERE id = %s",
                values,
            )

            # 3. 重算 remain_qty（差值调整）
            qty_diff = new_qty - old_qty
            if qty_diff != 0:
                cur.execute(
                    "UPDATE pdca.trading_record SET remain_qty = remain_qty - %s WHERE id = %s",
                    (qty_diff, record_id),
                )

            # 4. 重算 gross_profit
            cur.execute(
                """SELECT COALESCE(SUM(
                    (exit_price::numeric - %s) * quantity - commission
                ), 0) FROM pdca.trading_exit_slip
                   WHERE record_id = %s AND deleted_at IS NULL""",
                (entry_price, record_id),
            )
            total_profit = float(cur.fetchone()[0]) - float(commission_entry)
            cur.execute("UPDATE pdca.trading_record SET gross_profit = %s WHERE id = %s", (round(total_profit, 4), record_id))

            # 5. 获取最新 remain_qty
            cur.execute("SELECT remain_qty FROM pdca.trading_record WHERE id = %s", (record_id,))
            new_remain = cur.fetchone()[0]

            conn.commit()
            return ApiResponse(code=200, message="success", data={
                "id": slip_id, "record_id": record_id, "remain_qty": new_remain, "gross_profit": round(total_profit, 4),
            })


@router.delete("/exit-slips/{slip_id}", response_model=ApiResponse)
async def delete_exit_slip(slip_id: int):
    """软删除卖出子单，恢复 remain_qty 并重算 gross_profit"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 检查子单存在
            cur.execute(
                "SELECT es.id, es.record_id, es.quantity, r.entry_price, r.commission_entry "
                "FROM pdca.trading_exit_slip es "
                "JOIN pdca.trading_record r ON es.record_id = r.id "
                "WHERE es.id = %s AND es.deleted_at IS NULL AND r.deleted_at IS NULL",
                (slip_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="40011: 卖出子单不存在")
            _, record_id, qty, entry_price, commission_entry = row

            # 2. 软删除
            cur.execute("UPDATE pdca.trading_exit_slip SET deleted_at = NOW() WHERE id = %s", (slip_id,))

            # 3. 恢复 remain_qty
            cur.execute("UPDATE pdca.trading_record SET remain_qty = remain_qty + %s WHERE id = %s", (qty, record_id))

            # 4. 重算 gross_profit
            cur.execute(
                """SELECT COALESCE(SUM(
                    (exit_price::numeric - %s) * quantity - commission
                ), 0) FROM pdca.trading_exit_slip
                   WHERE record_id = %s AND deleted_at IS NULL""",
                (entry_price, record_id),
            )
            total_profit = float(cur.fetchone()[0]) - float(commission_entry)
            cur.execute("UPDATE pdca.trading_record SET gross_profit = %s WHERE id = %s", (round(total_profit, 4), record_id))

            # 5. 获取最新 remain_qty
            cur.execute("SELECT remain_qty FROM pdca.trading_record WHERE id = %s", (record_id,))
            new_remain = cur.fetchone()[0]

            conn.commit()
            return ApiResponse(code=200, message="success", data={
                "id": slip_id, "record_id": record_id, "remain_qty": new_remain, "gross_profit": round(total_profit, 4),
            })