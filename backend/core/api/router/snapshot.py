"""
router/snapshot.py - 全量快照路由
RuntimeError 统一由全局异常处理器返回 503，路由层仅处理业务参数校验异常
"""
import os
import time
import logging
from fastapi import APIRouter, Query, HTTPException
from shared.schemas import ApiResponse, SnapshotAllData, SnapshotHistoryData, SnapshotIncrementalData
from core.api.dependencies import (
    validate_optional_date,
    validate_required_date,
    validate_board,
    validate_market,
    SnapshotServiceDep,
    get_snapshot_service,
)

logger = logging.getLogger(__name__)
# 慢请求阈值支持环境变量配置
SLOW_REQUEST_THRESHOLD = float(os.getenv("SNAPSHOT_SLOW_THRESHOLD", "2.0"))
LARGE_DATA_WARN_COUNT = 4000

router = APIRouter(tags=["全量快照接口"])

@router.get("/all", summary="全量快照（300天OHLCV+指标）", response_model=ApiResponse[SnapshotAllData])
def get_all_snapshot(
    snapshot: SnapshotServiceDep,
    market: str | None = Query(None, description="市场过滤 cn/hk/us"),
    board: str | None = Query(None, description="板块过滤 main_board/gem/beijing"),
    industry: str | None = Query(None, description="行业名称过滤"),
    codes: str | None = Query(None, description="股票代码过滤，逗号分隔，如 000001,600000")
):
    mkt = validate_market(market)
    # 港美股无 A 股板块概念，board 过滤直接忽略
    board = validate_board(board) if mkt in ('cn', None) else None
    code_list = codes.split(",") if codes else None
    start = time.time()
    result = snapshot.get_all_snapshot(market=mkt, board=board, industry=industry, codes=code_list)
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
    market: str | None = Query(None, description="市场过滤 cn/hk/us"),
    board: str | None = Query(None, description="板块过滤 main_board/gem/beijing"),
    industry: str | None = Query(None, description="行业名称过滤"),
    codes: str | None = Query(None, description="股票代码过滤，逗号分隔，如 000001,600000")
):
    since = validate_required_date(since, label="since")
    mkt = validate_market(market)
    board = validate_board(board) if mkt in ('cn', None) else None
    code_list = codes.split(",") if codes else None
    start = time.time()
    try:
        result = snapshot.get_incremental_snapshot(since=since, market=mkt, board=board, industry=industry, codes=code_list)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    elapsed = time.time() - start

    if elapsed > SLOW_REQUEST_THRESHOLD:
        logger.warning("增量快照慢请求：since=%s, %d只, %d天, %.2fs", since, len(result.stocks), result.days, elapsed)
    else:
        logger.info("增量快照请求：since=%s, %d只, %d天, %.2fs", since, len(result.stocks), result.days)
    return ApiResponse(code=200, message="success", data=result)


@router.get("/history", summary="历史逐日快照（预计算字段，与选股视图同口径）", response_model=ApiResponse[SnapshotHistoryData])
def get_history_snapshot(
    snapshot: SnapshotServiceDep,
    codes: str = Query(..., description="股票代码过滤，逗号分隔（≤2000只），如 000001,600000,0001.HK"),
    market: str | None = Query(None, description="市场过滤 cn/hk/us；传入时剔除推断市场不符的代码"),
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD（含），缺省为 end_date 前 300 天"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD（含），缺省为最新交易日"),
    fields: str | None = Query(None, description="字段白名单裁剪，逗号分隔；缺省返回全部预计算字段"),
):
    """按股票列表 + 日期区间返回 stock_daily_snapshot 全历史预计算字段（只读）。

    供回测引擎逐日判定使用，字段与选股视图 /api/stocks/（同一宽表导出）口径一致。
    """
    code_list = [c for c in (codes.split(",") if codes else []) if c.strip()]
    field_list = [f for f in (fields.split(",") if fields else []) if f.strip()]
    start_val = validate_optional_date(start_date, label="start_date") if start_date else None
    end_val = validate_optional_date(end_date, label="end_date") if end_date else None
    t0 = time.time()
    try:
        result = snapshot.get_history_snapshots(
            codes=code_list,
            market=market,
            start_date=start_val,
            end_date=end_val,
            fields=field_list or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    elapsed = time.time() - t0
    row_count = sum(len(s.rows) for s in result.stocks)

    if elapsed > SLOW_REQUEST_THRESHOLD:
        logger.warning(
            "历史快照慢请求：%d只/%d行，区间 %s~%s，耗时%.2fs",
            result.total_codes, row_count, result.start_date, result.end_date, elapsed,
        )
    else:
        logger.info(
            "历史快照请求：%d只/%d行，区间 %s~%s，耗时%.2fs",
            result.total_codes, row_count, result.start_date, result.end_date, elapsed,
        )
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