"""
snapshots.py - 资金快照 + 资金曲线 API
"""
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["资金快照"])


class SnapshotCreate(BaseModel):
    snapshot_date: date
    total_asset: float = Field(..., ge=0)
    available_cash: float = Field(..., ge=0)
    position_value: float = Field(..., ge=0)
    deposit: float = 0
    withdrawal: float = 0
    realized_pnl: float = 0


# ============================================================
# 资金快照 CRUD
# ============================================================

@router.get("", response_model=ApiResponse)
async def list_snapshots(
    start_date: Optional[date] = Query(None, alias="start_date"),
    end_date: Optional[date] = Query(None, alias="end_date"),
):
    """获取资金快照列表（按日期范围）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            where_clauses = []
            params = []
            if start_date:
                where_clauses.append("snapshot_date >= %s")
                params.append(start_date)
            if end_date:
                where_clauses.append("snapshot_date <= %s")
                params.append(end_date)

            where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
            cur.execute(
                f"""
                SELECT id, snapshot_date, total_asset, available_cash, position_value,
                       deposit, withdrawal, net_deposit, realized_pnl, adjusted_nav, created_at
                FROM pdca.account_snapshot
                WHERE {where_sql}
                ORDER BY snapshot_date DESC
                """,
                params,
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("", response_model=ApiResponse)
async def create_snapshot(snapshot: SnapshotCreate):
    """新增资金快照"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 检查是否已存在
            cur.execute(
                "SELECT id FROM pdca.account_snapshot WHERE account_id = 1 AND snapshot_date = %s",
                (snapshot.snapshot_date,),
            )
            existing = cur.fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="40012: 该日期已存在资金快照")

            try:
                cur.execute(
                    """
                    INSERT INTO pdca.account_snapshot
                        (account_id, snapshot_date, total_asset, available_cash, position_value,
                         deposit, withdrawal, realized_pnl)
                    VALUES (1, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        snapshot.snapshot_date, snapshot.total_asset, snapshot.available_cash,
                        snapshot.position_value, snapshot.deposit, snapshot.withdrawal,
                        snapshot.realized_pnl,
                    ),
                )
                snap_id = cur.fetchone()[0]
                conn.commit()
                return ApiResponse(code=200, message="success", data={"id": snap_id})
            except Exception as e:
                logger.exception("创建资金快照失败")
                raise HTTPException(status_code=500, detail=f"50002: {str(e)}")


# ============================================================
# 资金曲线
# ============================================================

@router.get("/curve", response_model=ApiResponse)
async def get_equity_curve(
    start_date: Optional[date] = Query(None, alias="start_date"),
    end_date: Optional[date] = Query(None, alias="end_date"),
):
    """获取资金曲线数据（含调整后净值计算）

    调整后净值公式（SRS 3.6 节）：
    调整后净值(T) = 调整后净值(T-1) × (total_asset(T) / (total_asset(T) - net_deposit(T)))
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            where_clauses = []
            params = []
            if start_date:
                where_clauses.append("snapshot_date >= %s")
                params.append(start_date)
            if end_date:
                where_clauses.append("snapshot_date <= %s")
                params.append(end_date)

            where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
            cur.execute(
                f"""
                SELECT snapshot_date, total_asset, deposit, withdrawal, net_deposit, adjusted_nav
                FROM pdca.account_snapshot
                WHERE {where_sql}
                ORDER BY snapshot_date ASC
                """,
                params,
            )
            rows = cur.fetchall()

            if not rows:
                return ApiResponse(code=200, message="success", data={"items": []})

            # 计算调整后净值
            curve_data = []
            prev_nav = None

            for row in rows:
                snapshot_date, total_asset, deposit, withdrawal, net_deposit, adjusted_nav = row

                if adjusted_nav is not None:
                    # 使用已存储的调整后净值
                    nav = float(adjusted_nav)
                elif prev_nav is None:
                    # 第一条记录：净值 = 总资产
                    nav = float(total_asset)
                else:
                    # 调整后净值公式
                    denominator = float(total_asset) - float(net_deposit)
                    if denominator > 0:
                        nav = prev_nav * (float(total_asset) / denominator)
                    else:
                        nav = prev_nav

                prev_nav = nav
                curve_data.append({
                    "date": snapshot_date.isoformat(),
                    "total_asset": float(total_asset),
                    "net_deposit": float(net_deposit),
                    "adjusted_nav": round(nav, 2),
                })

            # 回填调整后净值到数据库
            with conn.cursor() as update_cur:
                for item in curve_data:
                    update_cur.execute(
                        "UPDATE pdca.account_snapshot SET adjusted_nav = %s WHERE account_id = 1 AND snapshot_date = %s",
                        (item["adjusted_nav"], item["date"]),
                    )
            conn.commit()

            return ApiResponse(code=200, message="success", data={"items": curve_data})