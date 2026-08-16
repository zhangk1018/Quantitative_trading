"""
snapshots.py - 资金快照 CRUD + 资金曲线

推荐索引（需在数据库端创建）：
- pdca.account_snapshot: (account_id, snapshot_date)（已有唯一索引 uq_account_snapshot）
- pdca.trading_record: (code, trade_date DESC) 用于 get_auto_equity_curve 行情查询
"""
import logging
from typing import Optional
from datetime import date

import psycopg2
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


class SnapshotUpdate(BaseModel):
    snapshot_date: Optional[date] = None
    total_asset: Optional[float] = Field(None, ge=0)
    available_cash: Optional[float] = Field(None, ge=0)
    position_value: Optional[float] = Field(None, ge=0)
    deposit: Optional[float] = Field(None, ge=0)
    withdrawal: Optional[float] = Field(None, ge=0)
    realized_pnl: Optional[float] = None


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
            # numeric 列转 float，避免前端收到字符串导致数值计算/显示异常
            for it in items:
                for f in ("total_asset", "available_cash", "position_value", "deposit",
                          "withdrawal", "net_deposit", "realized_pnl", "adjusted_nav"):
                    if it.get(f) is not None:
                        it[f] = float(it[f])
            return ApiResponse(code=200, message="success", data={"items": items})


@router.post("", response_model=ApiResponse)
async def create_snapshot(snapshot: SnapshotCreate):
    """新增资金快照"""
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO pdca.account_snapshot
                        (account_id, snapshot_date, total_asset, available_cash, position_value,
                         deposit, withdrawal, realized_pnl)
                    VALUES (1, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (account_id, snapshot_date) DO NOTHING
                    RETURNING id
                    """,
                    (
                        snapshot.snapshot_date, snapshot.total_asset, snapshot.available_cash,
                        snapshot.position_value, snapshot.deposit, snapshot.withdrawal,
                        snapshot.realized_pnl,
                    ),
                )
                snap_id = cur.fetchone()
                if not snap_id:
                    raise HTTPException(status_code=400, detail="40012: 该日期已存在资金快照")
                conn.commit()
                return ApiResponse(code=200, message="success", data={"id": snap_id[0]})
            except HTTPException:
                raise
            except psycopg2.Error as e:
                logger.exception("创建资金快照失败")
                raise HTTPException(status_code=500, detail=f"50002: {str(e)}")


@router.put("/{snapshot_id}", response_model=ApiResponse)
async def update_snapshot(snapshot_id: int, snapshot: SnapshotUpdate):
    """修改资金记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, snapshot_date FROM pdca.account_snapshot WHERE id = %s",
                (snapshot_id,),
            )
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="40401: 资金记录不存在")

            # 若修改日期，检查是否与其他记录冲突
            if snapshot.snapshot_date and snapshot.snapshot_date != existing[1]:
                cur.execute(
                    "SELECT id FROM pdca.account_snapshot WHERE account_id = 1 AND snapshot_date = %s AND id != %s",
                    (snapshot.snapshot_date, snapshot_id),
                )
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="40012: 该日期已存在资金记录")

            # 判断哪些字段影响 adjusted_nav：资产/出入金相关字段变更时需置 NULL 重算
            nav_affecting_fields = {"total_asset", "available_cash", "position_value", "deposit", "withdrawal"}
            fields = []
            values = []
            has_nav_change = False
            for f in ("snapshot_date", "total_asset", "available_cash", "position_value",
                      "deposit", "withdrawal", "realized_pnl"):
                v = getattr(snapshot, f)
                if v is not None:
                    fields.append(f)
                    values.append(v)
                    if f in nav_affecting_fields:
                        has_nav_change = True
            if not fields:
                raise HTTPException(status_code=400, detail="40013: 无更新字段")

            if has_nav_change:
                fields.append("adjusted_nav")
                values.append(None)
            values.append(snapshot_id)
            cur.execute(
                f"UPDATE pdca.account_snapshot SET {', '.join(f'{f} = %s' for f in fields)} WHERE id = %s",
                values,
            )
            conn.commit()
            return ApiResponse(code=200, message="success")


@router.delete("/{snapshot_id}", response_model=ApiResponse)
async def delete_snapshot(snapshot_id: int):
    """删除资金记录"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pdca.account_snapshot WHERE id = %s", (snapshot_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="40401: 资金记录不存在")
            cur.execute("DELETE FROM pdca.account_snapshot WHERE id = %s", (snapshot_id,))
            conn.commit()
            return ApiResponse(code=200, message="success", data={"id": snapshot_id})


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

            # 回填调整后净值到数据库（批量回写，减少网络往返）
            with conn.cursor() as update_cur:
                update_cur.executemany(
                    "UPDATE pdca.account_snapshot SET adjusted_nav = %s WHERE account_id = 1 AND snapshot_date = %s",
                    [(item["adjusted_nav"], item["date"]) for item in curve_data],
                )
            conn.commit()

            return ApiResponse(code=200, message="success", data={"items": curve_data})


@router.get("/curve-auto", response_model=ApiResponse)
async def get_auto_equity_curve():
    """根据股票买卖记录自动计算净值曲线（含未平仓持仓浮盈）

    净值 = 初始本金 + 累计已实现盈亏 + 未平仓浮盈
    - 初始本金：取最早一条资金记录(account_snapshot)的 total_asset
    - 已实现盈亏：按出场日期聚合已平仓交易的 gross_profit
    - 未平仓浮盈：对仍持仓(held_qty>0)的记录，按最新收盘价 × 剩余数量
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 初始本金 = 最早资金记录总资产
            cur.execute(
                "SELECT snapshot_date, total_asset FROM pdca.account_snapshot "
                "WHERE account_id = 1 ORDER BY snapshot_date ASC LIMIT 1"
            )
            base = cur.fetchone()
            initial_capital = float(base[1]) if base else 0.0
            base_date = base[0] if base else None

            # 2. 全部未删除交易记录（held_qty = 剩余持仓，NULL 视为全量持仓）
            cur.execute(
                """
                SELECT code, entry_date, exit_date, entry_price, quantity,
                       COALESCE(remain_qty, quantity) AS held_qty, gross_profit
                FROM pdca.trading_record
                WHERE deleted_at IS NULL
                """
            )
            rows = cur.fetchall()
            trades = [
                {
                    "code": r[0], "entry_date": r[1], "exit_date": r[2],
                    "entry_price": float(r[3]), "quantity": int(r[4]),
                    "held_qty": int(r[5]),
                    "gross_profit": float(r[6]) if r[6] is not None else 0.0,
                }
                for r in rows
            ]

            # 3. 未平仓持仓的最新收盘价
            open_codes = {t["code"] for t in trades if t["held_qty"] > 0}
            latest_close = {}
            if open_codes:
                cur.execute(
                    """
                    SELECT DISTINCT ON (code) code, close
                    FROM stock_quotes
                    WHERE cycle = '1d' AND code = ANY(%s)
                    ORDER BY code, trade_date DESC
                    """,
                    (list(open_codes),),
                )
                for c, close in cur.fetchall():
                    latest_close[c] = float(close)

        # 4. 未平仓持仓的 unrealized 贡献（按事件日 sweep-line 计算，避免 O(D×T) 嵌套循环）
        # 注意：部分平仓场景（exit_date 非空且 held_qty > 0）需按原始数量建仓、按平仓数量扣减
        open_trades = [t for t in trades if t["held_qty"] > 0]
        unrealized_events = {}  # date -> delta
        for t in open_trades:
            close = latest_close.get(t["code"])
            if close is None:
                logger.warning("get_auto_equity_curve: 缺失 %s 最新收盘价，浮盈计算忽略该持仓", t["code"])
                continue
            if t["exit_date"]:
                # 部分平仓：入场时按原始数量建仓，出场时按平仓数量扣减
                full_contrib = (close - t["entry_price"]) * t["quantity"]
                closed_contrib = (close - t["entry_price"]) * (t["quantity"] - t["held_qty"])
                unrealized_events[t["entry_date"]] = unrealized_events.get(t["entry_date"], 0.0) + full_contrib
                unrealized_events[t["exit_date"]] = unrealized_events.get(t["exit_date"], 0.0) - closed_contrib
            else:
                # 全仓未平仓：入场时建仓，浮盈持续到当前
                contrib = (close - t["entry_price"]) * t["held_qty"]
                unrealized_events[t["entry_date"]] = unrealized_events.get(t["entry_date"], 0.0) + contrib

        # 5. 事件日期集合（初始本金日期 + 各交易的进出场日）
        dates = set()
        if base_date:
            dates.add(base_date)
        for t in trades:
            dates.add(t["entry_date"])
            if t["exit_date"]:
                dates.add(t["exit_date"])
        dates = sorted(dates)

        # 已实现盈亏累计（按出场日）
        realized_by_date = {}
        for t in trades:
            if t["exit_date"]:
                realized_by_date[t["exit_date"]] = (
                    realized_by_date.get(t["exit_date"], 0.0) + t["gross_profit"]
                )

        curve_data = []
        cum_realized = 0.0
        cum_unrealized = 0.0
        for d in dates:
            cum_realized += realized_by_date.get(d, 0.0)
            cum_unrealized += unrealized_events.get(d, 0.0)
            equity = initial_capital + cum_realized + cum_unrealized
            curve_data.append({
                "date": d.isoformat(),
                "equity": round(equity, 2),
                "realized": round(cum_realized, 2),
                "unrealized": round(cum_unrealized, 2),
            })

        return ApiResponse(code=200, message="success", data={"items": curve_data})