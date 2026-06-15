"""
router/stocks.py - 股票数据查询路由

提供股票搜索、筛选、分页、排序等 REST 接口。
所有处理函数均为同步（FastAPI 自动在线程池中执行）。
返回统一响应信封格式 {code, message, data}。
"""

import pandas as pd
import logging
import time
from fastapi import APIRouter, Query, Path, Depends

from core.api.models.schemas import ScreenerRequest, ApiResponse
from core.service.screener_service import ScreenerService
from core.api.dependencies import get_screener_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["股票数据接口"])


@router.get("/", summary="股票列表（支持筛选、排序、分页）")
def get_stocks(
    filters: str = Query(None, description="K线形态筛选条件（逗号分隔）"),
    listed_board: str = Query(None, description="上市板块筛选"),
    industry: str = Query(None, description="行业筛选（逗号分隔）"),
    area: str = Query(None, description="地区筛选（逗号分隔）"),
    sort_by: str = Query("change_pct", description="排序字段"),
    sort_asc: bool = Query(False, description="是否升序排列"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
    limit: int = Query(100, ge=1, le=200, description="每页数量"),
    as_of_date: str = Query(None, description="数据截止日期（YYYYMMDD），不传则使用最新交易日"),
    screener: ScreenerService = Depends(get_screener_service),
) -> ApiResponse:
    try:
        # 若未传 as_of_date，使用 screener 内部的最新交易日
        if not as_of_date:
            as_of_date = screener.trade_date

        filter_dict = {}
        if filters:
            for f in filters.split(","):
                filter_dict[f.strip()] = True
        if industry:
            filter_dict["industry"] = industry.split(",")
        if area:
            filter_dict["area"] = area.split(",")
        if listed_board:
            filter_dict["listed_board"] = listed_board

        page = offset // limit + 1 if limit > 0 else 1
        page_size = limit

        request = ScreenerRequest(
            filters=filter_dict,
            sort_by=sort_by,
            sort_order="asc" if sort_asc else "desc",
            page=page,
            page_size=page_size,
            as_of_date=as_of_date,
        )
        
        # 调用服务获取结果
        result = screener.screen_stocks(request)
        
        # 转换为前端期望的格式 {items, total, offset, limit}
        data = {
            "items": result.data,
            "total": result.total,
            "offset": offset,
            "limit": limit,
        }
        
        return ApiResponse(code=200, message="success", data=data)
    except Exception as e:
        logger.exception("获取股票列表失败")
        return ApiResponse(code=500, message=f"获取股票列表失败: {str(e)}", data=None)


@router.get("/top/gainers", summary="涨幅榜")
def get_top_gainers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    screener: ScreenerService = Depends(get_screener_service),
):
    try:
        request = ScreenerRequest(page=page, page_size=page_size, sort_by="change_pct", sort_order="desc")
        result = screener.screen_stocks(request)
        
        offset = (page - 1) * page_size
        data = {
            "items": result.data,
            "total": result.total,
            "offset": offset,
            "limit": page_size,
        }
        
        return ApiResponse(code=200, message="success", data=data)
    except Exception as e:
        logger.exception("获取涨幅榜失败")
        return ApiResponse(code=500, message=f"获取涨幅榜失败: {str(e)}", data=None)


@router.get("/top/losers", summary="跌幅榜")
def get_top_losers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    screener: ScreenerService = Depends(get_screener_service),
):
    try:
        request = ScreenerRequest(page=page, page_size=page_size, sort_by="change_pct", sort_order="asc")
        result = screener.screen_stocks(request)
        
        offset = (page - 1) * page_size
        data = {
            "items": result.data,
            "total": result.total,
            "offset": offset,
            "limit": page_size,
        }
        
        return ApiResponse(code=200, message="success", data=data)
    except Exception as e:
        logger.exception("获取跌幅榜失败")
        return ApiResponse(code=500, message=f"获取跌幅榜失败: {str(e)}", data=None)


@router.get("/top/volume", summary="成交量榜")
def get_top_volume(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    screener: ScreenerService = Depends(get_screener_service),
):
    try:
        request = ScreenerRequest(page=page, page_size=page_size, sort_by="volume", sort_order="desc")
        result = screener.screen_stocks(request)
        
        offset = (page - 1) * page_size
        data = {
            "items": result.data,
            "total": result.total,
            "offset": offset,
            "limit": page_size,
        }
        
        return ApiResponse(code=200, message="success", data=data)
    except Exception as e:
        logger.exception("获取成交量榜失败")
        return ApiResponse(code=500, message=f"获取成交量榜失败: {str(e)}", data=None)


@router.get("/search", summary="股票搜索（代码/名称）")
def search_stocks(
    keyword: str = Query(..., min_length=1, description="搜索关键词（代码/名称）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    sort_by: str = Query("change_pct", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    screener: ScreenerService = Depends(get_screener_service),
):
    try:
        start_time = time.time()
        logger.info("股票搜索请求: keyword=%s", keyword)

        df = screener.df
        required_cols = ["ts_code", "name"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return ApiResponse(code=500, message=f"数据源缺少字段: {missing}", data=None)

        keyword_lower = keyword.lower()
        search_mask = pd.Series(False, index=df.index)
        for col in required_cols:
            search_mask |= df[col].astype(str).str.lower().str.contains(keyword_lower, na=False)

        filtered_df = df[search_mask]
        total = len(filtered_df)

        if total == 0:
            data = {"items": [], "total": 0, "offset": 0, "limit": page_size}
            return ApiResponse(code=200, message="success", data=data)

        # 排序
        sort_col = screener.to_parquet_col(sort_by)
        if sort_col not in df.columns:
            sort_col = "pct_chg"
        ascending = sort_order == "asc"
        filtered_df = filtered_df.sort_values(by=sort_col, ascending=ascending)

        # 分页
        offset = (page - 1) * page_size
        if offset >= total:
            offset = 0
        end = min(offset + page_size, total)
        page_df = filtered_df.iloc[offset:end]

        data_list = screener._convert_to_stock_responses(page_df)
        elapsed = time.time() - start_time
        logger.info("搜索完成: 耗时=%.2fs, 结果数=%d", elapsed, total)

        data = {
            "items": data_list,
            "total": total,
            "offset": offset,
            "limit": page_size,
        }
        
        return ApiResponse(code=200, message="success", data=data)
    except Exception as e:
        logger.exception("股票搜索失败")
        return ApiResponse(code=500, message=f"股票搜索失败: {str(e)}", data=None)


@router.get("/{stock_code}", summary="按股票代码查询详情")
def get_stock_by_code(
    stock_code: str = Path(..., description="股票代码"),
    screener: ScreenerService = Depends(get_screener_service),
):
    try:
        stock = screener.get_stock_by_code(stock_code)
        if stock is None:
            return ApiResponse(code=404, message=f"股票代码 {stock_code} 不存在", data=None)
        
        return ApiResponse(code=200, message="success", data=stock)
    except Exception as e:
        logger.exception("获取股票详情失败")
        return ApiResponse(code=500, message=f"获取股票详情失败: {str(e)}", data=None)