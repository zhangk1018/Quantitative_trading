"""
records.py - 交易台账 CRUD API + 券商导入 + 股票搜索
"""
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["交易台账"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================

class TradingRecordCreate(BaseModel):
    pdca_cycle_id: Optional[int] = None
    code: str = Field(..., min_length=1, max_length=32)
    security_name: Optional[str] = None
    long_short: str = Field(..., pattern="^(long|short)$")
    entry_date: date
    entry_price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    exit_date: Optional[date] = None
    exit_price: Optional[float] = Field(None, gt=0)
    commission_entry: float = 0
    commission_exit: float = 0
    slip_point: float = 0
    channel_height: Optional[float] = None
    order_type: str = 'limit'
    trigger_source: Optional[str] = None
    exit_reason: Optional[str] = None
    instrument_type: str = 'stock'
    settlement_currency: str = 'CNY'
    trading_plan_id: Optional[int] = None
    actual_stop_loss: Optional[float] = None


class TradingRecordUpdate(BaseModel):
    code: Optional[str] = None
    security_name: Optional[str] = None
    long_short: Optional[str] = None
    entry_date: Optional[date] = None
    entry_price: Optional[float] = Field(None, gt=0)
    quantity: Optional[int] = None
    exit_date: Optional[date] = None
    exit_price: Optional[float] = Field(None, gt=0)
    commission_entry: Optional[float] = None
    commission_exit: Optional[float] = None
    slip_point: Optional[float] = None
    channel_height: Optional[float] = None
    order_type: Optional[str] = None
    trigger_source: Optional[str] = None
    exit_reason: Optional[str] = None
    instrument_type: Optional[str] = None
    settlement_currency: Optional[str] = None
    trading_plan_id: Optional[int] = None
    actual_stop_loss: Optional[float] = None
    entry_score: Optional[float] = None
    exit_score: Optional[float] = None
    trade_score: Optional[float] = None
    trade_grade: Optional[str] = None
    gross_profit: Optional[float] = None


# ============================================================
# 交易记录 CRUD
# ============================================================

@router.get("", response_model=ApiResponse)
async def list_records(
    cycle_id: Optional[int] = Query(None, alias="cycle_id"),
    code: Optional[str] = Query(None),
    trade_grade: Optional[str] = Query(None, alias="trade_grade"),
    entry_date_from: Optional[date] = Query(None, alias="entry_date_from"),
    entry_date_to: Optional[date] = Query(None, alias="entry_date_to"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """获取交易台账列表（分页/排序/筛选）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            where_clauses = ["r.deleted_at IS NULL"]
            params = []
            placeholders = []

            if cycle_id:
                placeholders.append("r.pdca_cycle_id = %s")
                params.append(cycle_id)
            if code:
                placeholders.append("r.code = %s")
                params.append(code)
            if trade_grade:
                placeholders.append("r.trade_grade = %s")
                params.append(trade_grade)
            if entry_date_from:
                placeholders.append("r.entry_date >= %s")
                params.append(entry_date_from)
            if entry_date_to:
                placeholders.append("r.entry_date <= %s")
                params.append(entry_date_to)

            where_sql = where_clauses[0]
            if placeholders:
                where_sql = " AND ".join(where_clauses + placeholders)

            # 总数
            cur.execute(f"SELECT COUNT(*) FROM pdca.trading_record r WHERE {where_sql}", params)
            total = cur.fetchone()[0]

            # 分页数据
            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT r.*, p.code as plan_code, p.security_name as plan_name
                FROM pdca.trading_record r
                LEFT JOIN pdca.trading_plan p ON r.trading_plan_id = p.id
                WHERE {where_sql}
                ORDER BY r.entry_date DESC, r.id DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]

            return ApiResponse(code=200, message="success", data={"items": items, "total": total})


@router.post("", response_model=ApiResponse)
async def create_record(record: TradingRecordCreate):
    """新增交易记录"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 数值校验
                if record.entry_price <= 0:
                    raise HTTPException(status_code=400, detail="40004: 入场价必须大于0")
                if record.exit_date and record.exit_date < record.entry_date:
                    raise HTTPException(status_code=400, detail="40008: 出场日期不能早于进场日期")

                # pdca_cycle_id 为空时自动获取当前活跃周期
                if record.pdca_cycle_id is None:
                    cur.execute(
                        "SELECT id FROM pdca.pdca_cycle WHERE status = 'DO' ORDER BY id DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row:
                        record.pdca_cycle_id = row[0]
                    else:
                        raise HTTPException(status_code=400, detail="40012: 没有活跃的 PDCA 周期，请先创建周期")

                cur.execute(
                    """
                    INSERT INTO pdca.trading_record
                        (pdca_cycle_id, code, security_name, long_short, entry_date, entry_price,
                         quantity, exit_date, exit_price, commission_entry, commission_exit,
                         slip_point, channel_height, order_type, trigger_source, exit_reason,
                         instrument_type, settlement_currency, trading_plan_id, actual_stop_loss)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        record.pdca_cycle_id, record.code, record.security_name, record.long_short,
                        record.entry_date, record.entry_price, record.quantity,
                        record.exit_date, record.exit_price, record.commission_entry,
                        record.commission_exit, record.slip_point, record.channel_height,
                        record.order_type, record.trigger_source, record.exit_reason,
                        record.instrument_type, record.settlement_currency,
                        record.trading_plan_id, record.actual_stop_loss,
                    ),
                )
                record_id = cur.fetchone()[0]
                conn.commit()
                return ApiResponse(code=200, message="success", data={"id": record_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("创建交易记录失败")
        raise HTTPException(status_code=500, detail=f"50002: {str(e)}")


@router.put("/{record_id}", response_model=ApiResponse)
async def update_record(record_id: int, record: TradingRecordUpdate):
    """更新交易记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 检查是否存在
            cur.execute("SELECT id, deleted_at FROM pdca.trading_record WHERE id = %s", (record_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="40011: 交易记录不存在")
            if existing[1]:
                raise HTTPException(status_code=400, detail="40011: 交易记录已被删除")

            # 构建动态更新
            updates = {}
            for field in ("code", "security_name", "long_short", "entry_date", "entry_price",
                          "quantity", "exit_date", "exit_price", "commission_entry",
                          "commission_exit", "slip_point", "channel_height", "order_type",
                          "trigger_source", "exit_reason", "instrument_type",
                          "settlement_currency", "trading_plan_id", "actual_stop_loss",
                          "entry_score", "exit_score", "trade_score", "trade_grade",
                          "gross_profit"):
                val = getattr(record, field, None)
                if val is not None:
                    updates[field] = val

            if not updates:
                return ApiResponse(code=200, message="success", data={"id": record_id})

            set_clauses = [f"{k} = %s" for k in updates]
            values = list(updates.values())
            values.append(record_id)

            cur.execute(
                f"UPDATE pdca.trading_record SET {', '.join(set_clauses)} WHERE id = %s",
                values,
            )
            conn.commit()
            return ApiResponse(code=200, message="success", data={"id": record_id})


@router.delete("/{record_id}", response_model=ApiResponse)
async def delete_record(record_id: int):
    """软删除交易记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, deleted_at FROM pdca.trading_record WHERE id = %s", (record_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="40011: 交易记录不存在")
            if existing[1]:
                return ApiResponse(code=200, message="success", data={"id": record_id})

            cur.execute("UPDATE pdca.trading_record SET deleted_at = NOW() WHERE id = %s", (record_id,))
            conn.commit()
            return ApiResponse(code=200, message="success", data={"id": record_id})




