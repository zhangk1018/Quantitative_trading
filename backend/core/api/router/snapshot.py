"""
router/snapshot.py - 全量快照路由
RuntimeError 统一由全局异常处理器返回 503，路由层仅处理业务参数校验异常
"""
import os
import time
import logging
from fastapi import APIRouter, Query, HTTPException
from shared.schemas import ApiResponse, SnapshotAllData, SnapshotIncrementalData
from core.api.dependencies import validate_required_date, validate_board, SnapshotServiceDep, get_snapshot_service

logger = logging.getLogger(__name__)
# 慢请求阈值支持环境变量配置
SLOW_REQUEST_THRESHOLD = float(os.getenv("SNAPSHOT_SLOW_THRESHOLD", "2.0"))
LARGE_DATA_WARN_COUNT = 4000

router = APIRouter(tags=["全量快照接口"])

@router.get("/all", summary="全量快照（300天OHLCV+指标）", response_model=ApiResponse[SnapshotAllData])
def get_all_snapshot(
    snapshot: SnapshotServiceDep,
    board: str | None = Query(None, description="板块过滤 main_board/gem/beijing"),
    industry: str | None = Query(None, description="行业名称过滤")
):
    board = validate_board(board)
    start = time.time()
    result = snapshot.get_all_snapshot(board=board, industry=industry)
    elapsed = time.time() - start

    if elapsed > SLOW_REQUEST_THRESHOLD:
        logger.warning("全量快照慢请求：%d只股票，耗时%.2fs", result.total, elapsed)
    elif result.total > LARGE_DATA_WARN_COUNT:
        logger.warning("全量快照返回超大批量：%d只股票", result.total)
    else:
        logger.info("全量快照请求：%d只股票，耗时%.2fs", result.total, elapsed)
    return ApiResponse(code=200, message="success", data=result)

@router.get("/incremental", summary="增量同步", response_model=ApiResponse[SnapshotIncrementalData])
def get_incremental_snapshot(
    snapshot: SnapshotServiceDep,
    since: str = Query(..., description="起始日期 YYYY-MM-DD", examples=["2026-06-20"]),
    board: str | None = Query(None, description="板块过滤 main_board/gem/beijing"),
    industry: str | None = Query(None, description="行业名称过滤")
):
    since = validate_required_date(since, label="since")
    board = validate_board(board)
    start = time.time()
    try:
        result = snapshot.get_incremental_snapshot(since=since, board=board, industry=industry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    elapsed = time.time() - start

    if elapsed > SLOW_REQUEST_THRESHOLD:
        logger.warning("增量快照慢请求：since=%s, %d只, %d天, %.2fs", since, len(result.stocks), result.days, elapsed)
    else:
        logger.info("增量快照请求：since=%s, %d只, %d天, %.2fs", since, len(result.stocks), result.days)
    return ApiResponse(code=200, message="success", data=result)


@router.get("/ready", summary="服务就绪状态检查")
def check_ready():
    """检查全量快照数据是否加载就绪"""
    svc = get_snapshot_service()
    status = svc.get_status()
    if status["ready"]:
        return ApiResponse(code=200, message="ready", data=status)
    else:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content=ApiResponse(code=503, message="loading", data=status).model_dump(),
        )