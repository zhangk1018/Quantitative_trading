"""
router/watchlist.py - 自选股 CRUD 路由

提供用户自选股列表的增删改查功能。
所有接口使用统一响应信封格式 {code, message, data}。
"""

import logging
from fastapi import APIRouter, Query, Path, HTTPException
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from core.api.models.schemas import ApiResponse
from collector.db.database import get_db_session
from utils.stock_code_utils import normalize_db_code, normalize_code

logger = logging.getLogger(__name__)
router = APIRouter(tags=["自选股管理"])


# ============================================
# 请求/响应模型
# ============================================

class WatchlistItem(BaseModel):
    """自选股项"""
    id: int = Field(..., description="记录ID")
    code: str = Field(..., description="股票代码（A股6位 / 港股0001.HK / 美股AAPL）")
    market: str = Field('cn', description="所属市场（cn/hk/us）")
    group_name: str = Field(..., description="分组名称")
    sort_order: int = Field(0, description="排序序号")
    created_at: Optional[str] = Field(None, description="创建时间")


class WatchlistAddRequest(BaseModel):
    """添加自选股请求"""
    code: str = Field(..., min_length=1, max_length=10, description="股票代码（A股6位 / 港股0001.HK / 美股AAPL）")
    group_name: Optional[str] = Field(None, description="分组名称（默认：默认分组）")


class WatchlistUpdateRequest(BaseModel):
    """更新自选股请求"""
    group_name: Optional[str] = Field(None, description="分组名称")
    sort_order: Optional[int] = Field(None, ge=0, description="排序序号")


# ============================================
# CRUD 接口
# ============================================

@router.get("/", summary="获取自选股列表")
def get_watchlist(
    user_id: str = Query("default", description="用户ID"),
):
    """获取用户自选股列表，按 sort_order 升序排列"""
    try:
        with get_db_session() as db:
            result = db.execute(
                text("SELECT id, code, market, group_name, sort_order, created_at "
                     "FROM user_watchlist "
                     "WHERE user_id = :user_id "
                     "ORDER BY sort_order ASC, created_at ASC"),
                {"user_id": user_id},
            )
            rows = result.fetchall()

        items = [
            WatchlistItem(
                id=row[0],
                code=row[1],
                market=row[2] or 'cn',
                group_name=row[3],
                sort_order=row[4],
                created_at=str(row[5]) if row[5] else None,
            )
            for row in rows
        ]

        return ApiResponse(code=200, message="success", data=items)
    except Exception as e:
        logger.exception("获取自选股列表失败")
        return ApiResponse(code=500, message=f"获取自选股列表失败: {str(e)}", data=None)


@router.post("/", summary="添加自选股")
def add_watchlist(
    body: WatchlistAddRequest,
    user_id: str = Query("default", description="用户ID"),
):
    """
    添加股票到自选股。

    - code 自动归一化为库内代码（A股6位 / 港股 0001.HK / 美股 AAPL），并按市场存储
    - 重复添加返回 409 冲突
    """
    # 归一化 + 推断市场：A股剥 .SH/.SZ/.BJ，港股/美股原样
    db_code, market = normalize_db_code(body.code)
    # A股需满足 6 位数字规则（保留旧严格校验），港/美按原样接受
    if market == 'cn' and normalize_code(body.code) is None:
        return ApiResponse(
            code=400,
            message=f"无效的股票代码格式: {body.code}",
            data=None,
        )

    group_name = body.group_name or "默认分组"

    try:
        with get_db_session() as db:
            # 检查是否已存在（按 user + code + market 唯一匹配）
            existing = db.execute(
                text("SELECT id FROM user_watchlist WHERE user_id = :user_id AND code = :code AND market = :market"),
                {"user_id": user_id, "code": db_code, "market": market},
            ).fetchone()

            if existing:
                return ApiResponse(
                    code=409,
                    message=f"股票 {db_code} 已在自选股中",
                    data={"id": existing[0], "code": db_code, "market": market},
                )

            # 获取当前最大 sort_order
            max_order = db.execute(
                text("SELECT COALESCE(MAX(sort_order), -1) FROM user_watchlist WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalar()

            # 插入新记录
            db.execute(
                text("INSERT INTO user_watchlist (user_id, code, market, group_name, sort_order) "
                     "VALUES (:user_id, :code, :market, :group_name, :sort_order)"),
                {
                    "user_id": user_id,
                    "code": db_code,
                    "market": market,
                    "group_name": group_name,
                    "sort_order": max_order + 1,
                },
            )
            db.commit()

            # 返回新记录
            row = db.execute(
                text("SELECT id, code, market, group_name, sort_order, created_at "
                     "FROM user_watchlist "
                     "WHERE user_id = :user_id AND code = :code AND market = :market"),
                {"user_id": user_id, "code": db_code, "market": market},
            ).fetchone()

        item = WatchlistItem(
            id=row[0],
            code=row[1],
            market=row[2] or 'cn',
            group_name=row[3],
            sort_order=row[4],
            created_at=str(row[5]) if row[5] else None,
        )

        return ApiResponse(code=200, message="添加成功", data=item)
    except Exception as e:
        logger.exception("添加自选股失败")
        return ApiResponse(code=500, message=f"添加自选股失败: {str(e)}", data=None)


@router.delete("/{code}", summary="移除自选股")
def delete_watchlist(
    code: str = Path(..., description="股票代码（A股6位 / 港股0001.HK / 美股AAPL）"),
    user_id: str = Query("default", description="用户ID"),
):
    """从自选股中移除指定股票"""
    # 归一化 + 推断市场（与添加口径一致）
    db_code, market = normalize_db_code(code)
    if market == 'cn' and normalize_code(code) is None:
        return ApiResponse(
            code=400,
            message=f"无效的股票代码格式: {code}",
            data=None,
        )

    try:
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM user_watchlist WHERE user_id = :user_id AND code = :code AND market = :market"),
                {"user_id": user_id, "code": db_code, "market": market},
            )
            db.commit()

            if result.rowcount == 0:
                return ApiResponse(
                    code=404,
                    message=f"自选股中未找到股票 {db_code}",
                    data=None,
                )

        return ApiResponse(code=200, message=f"已移除 {db_code}", data=None)
    except Exception as e:
        logger.exception("移除自选股失败")
        return ApiResponse(code=500, message=f"移除自选股失败: {str(e)}", data=None)


@router.patch("/{code}", summary="更新自选股分组/排序")
def update_watchlist(
    body: WatchlistUpdateRequest,
    code: str = Path(..., description="股票代码（A股6位 / 港股0001.HK / 美股AAPL）"),
    user_id: str = Query("default", description="用户ID"),
):
    """更新自选股的分组名称或排序序号"""
    # 归一化 + 推断市场（与添加口径一致）
    db_code, market = normalize_db_code(code)
    if market == 'cn' and normalize_code(code) is None:
        return ApiResponse(
            code=400,
            message=f"无效的股票代码格式: {code}",
            data=None,
        )

    # 至少需要一个更新字段
    if body.group_name is None and body.sort_order is None:
        return ApiResponse(
            code=400,
            message="至少需要提供 group_name 或 sort_order",
            data=None,
        )

    try:
        with get_db_session() as db:
            # 检查记录是否存在（按 user + code + market 匹配）
            existing = db.execute(
                text("SELECT id FROM user_watchlist WHERE user_id = :user_id AND code = :code AND market = :market"),
                {"user_id": user_id, "code": db_code, "market": market},
            ).fetchone()

            if not existing:
                return ApiResponse(
                    code=404,
                    message=f"自选股中未找到股票 {db_code}",
                    data=None,
                )

            # 构建动态更新
            updates = []
            params = {"user_id": user_id, "code": db_code, "market": market}
            if body.group_name is not None:
                updates.append("group_name = :group_name")
                params["group_name"] = body.group_name
            if body.sort_order is not None:
                updates.append("sort_order = :sort_order")
                params["sort_order"] = body.sort_order

            set_clause = ", ".join(updates)
            # 安全校验：确保 set_clause 仅包含白名单字段
            allowed_fields = {"group_name", "sort_order"}
            for field in updates:
                col_name = field.split(" = ")[0]
                if col_name not in allowed_fields:
                    raise HTTPException(status_code=400, detail=f"不允许更新的字段: {col_name}")
            db.execute(
                text(f"UPDATE user_watchlist SET {set_clause} WHERE user_id = :user_id AND code = :code AND market = :market"),
                params,
            )
            db.commit()

            # 返回更新后的记录
            row = db.execute(
                text("SELECT id, code, market, group_name, sort_order, created_at "
                     "FROM user_watchlist "
                     "WHERE user_id = :user_id AND code = :code AND market = :market"),
                {"user_id": user_id, "code": db_code, "market": market},
            ).fetchone()

        item = WatchlistItem(
            id=row[0],
            code=row[1],
            market=row[2] or 'cn',
            group_name=row[3],
            sort_order=row[4],
            created_at=str(row[5]) if row[5] else None,
        )

        return ApiResponse(code=200, message="更新成功", data=item)
    except Exception as e:
        logger.exception("更新自选股失败")
        return ApiResponse(code=500, message=f"更新自选股失败: {str(e)}", data=None)