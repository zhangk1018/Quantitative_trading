"""
diaries.py - 交易日记 CRUD API + 附件上传
"""
import os
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from core.api.dependencies import get_db
from shared.error_codes import CommonError, PDCAError
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["交易日记"])

# 附件存储目录
_ATTACHMENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "attachments", "pdca",
)
# 允许的附件 MIME 类型
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class DiaryCreate(BaseModel):
    # 需求③禁止独立日记：必须关联交易记录（前端可绕过后端仍需强校验）
    trading_record_id: int
    pdca_cycle_id: int
    emotion_note: Optional[str] = None
    review_text: str = Field(..., min_length=1)
    three_month_review_done: bool = False


class DiaryUpdate(BaseModel):
    emotion_note: Optional[str] = None
    review_text: Optional[str] = None
    three_month_review_done: Optional[bool] = None


# ============================================================
# 交易日记 CRUD
# ============================================================

@router.get("", response_model=ApiResponse)
async def list_diaries(
    cycle_id: Optional[int] = Query(None, alias="cycle_id"),
    record_id: Optional[int] = Query(None, alias="record_id"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """获取交易日记列表"""
    with get_db() as conn:
        with conn.cursor() as cur:
            where_clauses = ["d.deleted_at IS NULL"]
            params = []
            placeholders = []

            if cycle_id:
                placeholders.append("d.pdca_cycle_id = %s")
                params.append(cycle_id)
            if record_id:
                placeholders.append("d.trading_record_id = %s")
                params.append(record_id)

            where_sql = where_clauses[0]
            if placeholders:
                where_sql = " AND ".join(where_clauses + placeholders)

            cur.execute(f"SELECT COUNT(*) FROM pdca.trading_diary d WHERE {where_sql}", params)
            total = cur.fetchone()[0]

            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT d.*, r.code, r.security_name
                FROM pdca.trading_diary d
                LEFT JOIN pdca.trading_record r ON d.trading_record_id = r.id
                WHERE {where_sql}
                ORDER BY d.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]
            return ApiResponse(code=200, message="success", data={"items": items, "total": total})


def _cycle_status(conn, cycle_id: int) -> Optional[str]:
    """查询周期状态；周期不存在返回 None。"""
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM pdca.pdca_cycle WHERE id = %s", (cycle_id,))
        row = cur.fetchone()
        return row[0] if row else None


def _assert_cycle_not_done(conn, cycle_id: int) -> None:
    """校验周期未闭环（供新建/改删日记前调用）。

    - 周期不存在 → 404 CYCLE_NOT_FOUND
    - 周期已闭环（DONE）→ 400 DIARY_CYCLE_CLOSED
    """
    status = _cycle_status(conn, cycle_id)
    if status is None:
        raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())
    if status == "DONE":
        raise HTTPException(status_code=400, detail=PDCAError.DIARY_CYCLE_CLOSED.detail())


def _diary_cycle_id(conn, diary_id: int) -> Optional[int]:
    """查询日记关联的周期 id（含软删除，供改删前校验）；不存在返回 None。"""
    with conn.cursor() as cur:
        cur.execute("SELECT pdca_cycle_id FROM pdca.trading_diary WHERE id = %s", (diary_id,))
        row = cur.fetchone()
        return row[0] if row else None


@router.post("", response_model=ApiResponse)
async def create_diary(diary: DiaryCreate):
    """新增交易日记（必须关联交易记录；仅允许写入未闭环周期）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                # ① 交易记录必须存在且未删除
                cur.execute(
                    "SELECT id FROM pdca.trading_record WHERE id = %s AND deleted_at IS NULL",
                    (diary.trading_record_id,),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail=PDCAError.RECORD_NOT_FOUND.detail())

                # ③ 仅允许在未闭环周期新建日记
                status = _cycle_status(conn, diary.pdca_cycle_id)
                if status is None:
                    raise HTTPException(status_code=404, detail=PDCAError.CYCLE_NOT_FOUND.detail())
                if status == "DONE":
                    raise HTTPException(status_code=400, detail=PDCAError.DIARY_CYCLE_CLOSED.detail())

                cur.execute(
                    """
                    INSERT INTO pdca.trading_diary
                        (trading_record_id, pdca_cycle_id, emotion_note, review_text, three_month_review_done)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        diary.trading_record_id, diary.pdca_cycle_id,
                        diary.emotion_note, diary.review_text, diary.three_month_review_done,
                    ),
                )
                diary_id = cur.fetchone()[0]
                conn.commit()
                return ApiResponse(code=200, message="success", data={"id": diary_id})
            except HTTPException:
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                logger.exception("创建交易日记失败")
                raise HTTPException(status_code=500, detail=CommonError.DB_QUERY.detail(detail=str(e)))


@router.put("/{diary_id}", response_model=ApiResponse)
async def update_diary(diary_id: int, diary: DiaryUpdate):
    """更新交易日记（仅未闭环周期可改）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, deleted_at FROM pdca.trading_diary WHERE id = %s", (diary_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=PDCAError.DIARY_NOT_FOUND.detail())
            if existing[1]:
                raise HTTPException(status_code=400, detail=PDCAError.DIARY_DELETED.detail())

            # ③ 仅未闭环周期允许修改
            cycle_id = _diary_cycle_id(conn, diary_id)
            if cycle_id is None:
                raise HTTPException(status_code=404, detail=PDCAError.DIARY_NOT_FOUND.detail())
            _assert_cycle_not_done(conn, cycle_id)

            updates = {}
            for field in ("emotion_note", "review_text", "three_month_review_done"):
                val = getattr(diary, field, None)
                if val is not None:
                    updates[field] = val

            if not updates:
                return ApiResponse(code=200, message="success", data={"id": diary_id})

            set_clauses = [f"{k} = %s" for k in updates]
            values = list(updates.values())
            values.append(diary_id)

            cur.execute(
                f"UPDATE pdca.trading_diary SET {', '.join(set_clauses)} WHERE id = %s",
                values,
            )
            conn.commit()
            return ApiResponse(code=200, message="success", data={"id": diary_id})


@router.delete("/{diary_id}", response_model=ApiResponse)
async def delete_diary(diary_id: int):
    """软删除交易日记（仅未闭环周期可删，幂等）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, deleted_at FROM pdca.trading_diary WHERE id = %s", (diary_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=PDCAError.DIARY_NOT_FOUND.detail())
            if existing[1]:
                raise HTTPException(status_code=400, detail=PDCAError.DIARY_DELETED.detail())

            # ③ 仅未闭环周期允许删除
            cycle_id = _diary_cycle_id(conn, diary_id)
            if cycle_id is None:
                raise HTTPException(status_code=404, detail=PDCAError.DIARY_NOT_FOUND.detail())
            _assert_cycle_not_done(conn, cycle_id)

            cur.execute(
                "UPDATE pdca.trading_diary SET deleted_at = NOW() WHERE id = %s",
                (diary_id,),
            )
            conn.commit()
            return ApiResponse(code=200, message="success", data={"id": diary_id})


# ============================================================
# 附件上传
# ============================================================

@router.post("/{diary_id}/upload", response_model=ApiResponse)
async def upload_attachment(diary_id: int, file: UploadFile = File(...)):
    """上传附件（jpg/png/gif ≤10MB）"""
    # 校验文件类型
    if file.content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=PDCAError.FILE_FORMAT_UNSUPPORTED.detail())

    # 校验文件大小
    contents = await file.read()
    if len(contents) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=PDCAError.FILE_TOO_LARGE.detail())

    # 确保目录存在
    os.makedirs(_ATTACHMENT_DIR, exist_ok=True)

    # 生成唯一文件名
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(_ATTACHMENT_DIR, unique_name)

    # 写入文件
    with open(file_path, "wb") as f:
        f.write(contents)

    # 更新日记的附件路径
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, deleted_at, attach_file_paths FROM pdca.trading_diary WHERE id = %s",
                (diary_id,),
            )
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=PDCAError.DIARY_NOT_FOUND.detail())
            if existing[1]:
                raise HTTPException(status_code=400, detail=PDCAError.DIARY_DELETED.detail())

            existing_paths = existing[2] or []
            if isinstance(existing_paths, list):
                new_paths = existing_paths + [file_path]
            else:
                new_paths = [file_path]

            cur.execute(
                "UPDATE pdca.trading_diary SET attach_file_paths = %s WHERE id = %s",
                (new_paths, diary_id),
            )
            conn.commit()

    return ApiResponse(code=200, message="success", data={"file_path": file_path})