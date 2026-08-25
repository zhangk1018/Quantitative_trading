"""
experience.py - 经验知识库查询 API

经验知识库（pdca.trade_experience）只读浏览接口：
- 支持标签筛选（tags @> 数组全命中）、关键词模糊搜索（title/content ILIKE）
- 支持分页（page / page_size，默认 1 / 20）
- 过滤软删除（deleted_at IS NULL），按 created_at DESC 排序
- 数据来源：Act 模块「冻结经验」自动落库（见 act_record._sync_trade_experience）

对应协作单 [21.0-EXPERIENCE-LIBRARY-API-20260825]
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from core.api.dependencies import get_db
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["经验知识库"])

# 响应字段（排除内部字段 deleted_at）
_EXPERIENCE_COLUMNS = (
    "id, account_id, trading_record_id, title, content, tags, "
    "source_act_record_id, created_at, updated_at"
)


def _escape_like(pattern: str) -> str:
    """转义 LIKE 通配符，避免用户输入 % / _ 干扰模糊匹配"""
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_tags(request: Request) -> list[str]:
    """从查询参数收集标签数组，兼容多种数组序列化形式：

    - ``tags=a&tags=b``：标准重复 key（FastAPI 原生解析）
    - ``tags[]=a&tags[]=b``：axios 默认数组序列化
    - ``tags[0]=a&tags[1]=b``：显式索引形式
    """
    tags = []
    for key, value in request.query_params.multi_items():
        if key == "tags" or key.startswith("tags["):
            if value:
                tags.append(value)
    return tags


@router.get("/experiences", response_model=ApiResponse)
async def list_experiences(
    request: Request,
    keyword: Optional[str] = Query(default=None, description="标题/内容关键词模糊搜索"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
):
    """查询经验知识库列表（只读）"""
    where = ["deleted_at IS NULL"]
    params: list = []

    # 标签筛选：过滤空字符串，全部命中（tags @> 数组）
    tags = _parse_tags(request)
    if tags:
        where.append("tags @> %s::varchar[]")
        params.append(tags)

    # 关键词搜索：标题/内容模糊匹配，转义通配符
    if keyword and keyword.strip():
        like = f"%{_escape_like(keyword.strip())}%"
        where.append("(title ILIKE %s ESCAPE '\\' OR content ILIKE %s ESCAPE '\\')")
        params.extend([like, like])

    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM pdca.trade_experience WHERE {where_sql}",
                params,
            )
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT {_EXPERIENCE_COLUMNS}
                FROM pdca.trade_experience
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            columns = [desc[0] for desc in cur.description]
            items = [dict(zip(columns, row)) for row in cur.fetchall()]

    logger.info("查询经验知识库 total=%s, page=%s, page_size=%s, tags=%s", total, page, page_size, tags)
    return ApiResponse(code=200, message="success", data={"items": items, "total": total})
