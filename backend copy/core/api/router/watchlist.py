"""
router/watchlist.py - 自选股 CRUD 路由

提供用户自选股列表的增删改查功能。
所有接口使用统一响应信封格式 {code, message, data}。
"""

import logging
from fastapi import APIRouter, Query, Path
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from core.api.models.schemas import ApiResponse
from collector.db.database import get_db_session
from utils.stock_code_utils import normalize_code

logger = logging.getLogger(__name__)
router = APIRouter(tags=["自选股管理"])


# ============================================
# 请求/响应模型
# ============================================

class WatchlistItem(BaseModel):
    """自选股项"""
    id: int = Field(..., description="记录ID")
    code: str = Field(..., description="股票代码（6位纯数字）")
    group_name: str = Field(..., description="分组名称")
    sort_order: int = Field(0, description="排序序号")
    created_at: Optional[str] = Field(None, description="创建时间")


class WatchlistAddRequest(BaseModel):
    """添加自选股请求"""
    code: str = Field(..., min_length=6, max_length=10, description="股票代码")
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
                text("SELECT id, code, group_name, sort_order, created_at "
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
                group_name=row[2],
                sort_order=row[3],
                created_at=str(row[4]) if row[4] else None,
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

    - code 会自动标准化为6位纯数字格式
    - 重复添加返回 409 冲突
    """
    # 标准化股票代码
    code = normalize_code(body.code)
    if not code:
        return ApiResponse(
            code=400,
            message=f"无效的股票代码格式: {body.code}",
            data=None,
        )

    group_name = body.group_name or "默认分组"

    try:
        with get_db_session() as db:
            # 检查是否已存在
            existing = db.execute(
                text("SELECT id FROM user_watchlist WHERE user_id = :user_id AND code = :code"),
                {"user_id": user_id, "code": code},
            ).fetchone()

            if existing:
                return ApiResponse(
                    code=409,
                    message=f"股票 {code} 已在自选股中",
                    data={"id": existing[0], "code": code},
                )

            # 获取当前最大 sort_order
            max_order = db.execute(
                text("SELECT COALESCE(MAX(sort_order), -1) FROM user_watchlist WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalar()

            # 插入新记录
            db.execute(
                text("INSERT INTO user_watchlist (user_id, code, group_name, sort_order) "
                     "VALUES (:user_id, :code, :group_name, :sort_order)"),
                {
                    "user_id": user_id,
                    "code": code,
                    "group_name": group_name,
                    "sort_order": max_order + 1,
                },
            )
            db.commit()

            # 返回新记录
            row = db.execute(
                text("SELECT id, code, group_name, sort_order, created_at "
                     "FROM user_watchlist "
                     "WHERE user_id = :user_id AND code = :code"),
                {"user_id": user_id, "code": code},
            ).fetchone()

        item = WatchlistItem(
            id=row[0],
            code=row[1],
            group_name=row[2],
            sort_order=row[3],
            created_at=str(row[4]) if row[4] else None,
        )

        return ApiResponse(code=200, message="添加成功", data=item)
    except Exception as e:
        logger.exception("添加自选股失败")
        return ApiResponse(code=500, message=f"添加自选股失败: {str(e)}", data=None)


@router.delete("/{code}", summary="移除自选股")
def delete_watchlist(
    code: str = Path(..., description="股票代码（6位数字）"),
    user_id: str = Query("default", description="用户ID"),
):
    """从自选股中移除指定股票"""
    # 标准化股票代码
    normalized = normalize_code(code)
    if not normalized:
        return ApiResponse(
            code=400,
            message=f"无效的股票代码格式: {code}",
            data=None,
        )

    try:
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM user_watchlist WHERE user_id = :user_id AND code = :code"),
                {"user_id": user_id, "code": normalized},
            )
            db.commit()

            if result.rowcount == 0:
                return ApiResponse(
                    code=404,
                    message=f"自选股中未找到股票 {normalized}",
                    data=None,
                )

        return ApiResponse(code=200, message=f"已移除 {normalized}", data=None)
    except Exception as e:
        logger.exception("移除自选股失败")
        return ApiResponse(code=500, message=f"移除自选股失败: {str(e)}", data=None)


@router.patch("/{code}", summary="更新自选股分组/排序")
def update_watchlist(
    body: WatchlistUpdateRequest,
    code: str = Path(..., description="股票代码（6位数字）"),
    user_id: str = Query("default", description="用户ID"),
):
    """更新自选股的分组名称或排序序号"""
    # 标准化股票代码
    normalized = normalize_code(code)
    if not normalized:
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
            # 检查记录是否存在
            existing = db.execute(
                text("SELECT id FROM user_watchlist WHERE user_id = :user_id AND code = :code"),
                {"user_id": user_id, "code": normalized},
            ).fetchone()

            if not existing:
                return ApiResponse(
                    code=404,
                    message=f"自选股中未找到股票 {normalized}",
                    data=None,
                )

            # 构建动态更新
            updates = []
            params = {"user_id": user_id, "code": normalized}
            if body.group_name is not None:
                updates.append("group_name = :group_name")
                params["group_name"] = body.group_name
            if body.sort_order is not None:
                updates.append("sort_order = :sort_order")
                params["sort_order"] = body.sort_order

            set_clause = ", ".join(updates)
            db.execute(
                text(f"UPDATE user_watchlist SET {set_clause} WHERE user_id = :user_id AND code = :code"),
                params,
            )
            db.commit()

            # 返回更新后的记录
            row = db.execute(
                text("SELECT id, code, group_name, sort_order, created_at "
                     "FROM user_watchlist "
                     "WHERE user_id = :user_id AND code = :code"),
                {"user_id": user_id, "code": normalized},
            ).fetchone()

        item = WatchlistItem(
            id=row[0],
            code=row[1],
            group_name=row[2],
            sort_order=row[3],
            created_at=str(row[4]) if row[4] else None,
        )

        return ApiResponse(code=200, message="更新成功", data=item)
    except Exception as e:
        logger.exception("更新自选股失败")
        return ApiResponse(code=500, message=f"更新自选股失败: {str(e)}", data=None)