"""
router/stocks.py - 股票数据查询路由

提供股票搜索、筛选、分页、排序等 REST 接口。
所有处理函数均为同步（FastAPI 自动在线程池中执行）。
返回统一响应信封格式 {code, message, data}。
"""

import pandas as pd
import logging
import time
from fastapi import APIRouter, Query, Path, Depends, Request

from core.api.models.schemas import ScreenerRequest, ApiResponse
from core.service.screener_service import ScreenerService
from core.api.dependencies import get_screener_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["股票数据接口"])

# 前端指标 id → 后端 parquet 字段名映射
INDICATOR_FIELD_MAP = {
    "market_cap": "market_cap",
    "price": "close",
    "change_pct": "change_pct",
    "pe_static": "pe",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "volume_ratio": "volume_ratio",
    "amount": "amount",
    "volume": "volume",
    "turnover": "turnover_rate",
}

# 条件构建器 preset fieldKey → 后端 filter_dict 特殊键（复合条件，
# 需在 _apply_filters 中特判；其余 fieldKey 与 parquet 列名同名）
# 命名规则：键以 `__cond_` 开头避免与普通列名冲突
_COND_SPECIAL_PREFIX = "__cond_"

# preset fieldKey → filter_dict 特殊条件映射（值是 dict 形式，
# 后续在 screener_service._apply_cond_special 中处理）
COND_SPECIAL_MAP = {
    "rsi_oversold": {
        # 6 日 RSI < 30 视为超卖
        "kind": "threshold",
        "field": "rsi_6",
        "op": "<",
        "value": 30,
    },
    "volume_breakout": {
        # 量比 ≥ 1.5 视为放量
        "kind": "threshold",
        "field": "volume_ratio",
        "op": ">=",
        "value": 1.5,
    },
    "low_valuation": {
        # K 2026-06-18 决策：pe_ttm<30 且 pb<3 且非负
        "kind": "multi_threshold",
        "conditions": [
            {"field": "pe_ttm", "op": ">", "value": 0},
            {"field": "pe_ttm", "op": "<", "value": 30},
            {"field": "pb", "op": "<", "value": 3},
        ],
    },
    "consecutive_up": {
        # K 2026-06-18 决策：parquet 只有 consec_up_days（int64），
        # 连涨 3 天及以上 = consec_up_days >= 3
        "kind": "threshold",
        "field": "consec_up_days",
        "op": ">=",
        "value": 3,
    },
}

# K 2026-06-18 决策：5 个 K线形态 parquet 暂无对应列，标记为不支持
# 后端收到这些 fieldKey 写入 logger.warning 并跳过（前端 UI 仍保留，
# 等后续 ETL 接入后从该集合移除即可生效）
COND_UNSUPPORTED_FIELD_KEYS = {
    "pattern_morning_star",
    "pattern_evening_star",
    "pattern_bullish_engulfing",
    "pattern_bearish_engulfing",
    "pattern_hammer",
}

# 条件构建器 preset fieldKey → 真实 parquet 列名（同名的 fieldKey 走这条路径）
# 业务：K 2026-06-18 任务，仅保留与 parquet 列名 1:1 映射的 preset。
# 其余复杂/不支持的 preset 见 COND_SPECIAL_MAP / COND_UNSUPPORTED_FIELD_KEYS。
COND_DIRECT_FIELD_KEYS = {
    # MACD pattern（preset fieldKey 简写 → parquet 全称）
    "macd_golden_cross": "macd_low_golden_cross",
    "bottom_volume_macd": None,  # 组合 preset，下面特殊处理
}


def _parse_indicator_ranges(query_params) -> dict:
    """解析 query 参数中的 ${id}_min / ${id}_max，通过映射表转换为 filter_dict 范围条件。

    返回格式: {"field_name": {"min": 1.0, "max": 2.0}, ...}
    """
    ranges = {}
    for param_name, param_value in query_params.items():
        if not (param_name.endswith("_min") or param_name.endswith("_max")):
            continue
        suffix = "_min" if param_name.endswith("_min") else "_max"
        ind_id = param_name[: -len(suffix)]  # 'market_cap_min' → 'market_cap'
        field = INDICATOR_FIELD_MAP.get(ind_id)
        if not field:
            continue
        try:
            val = float(param_value)
        except (ValueError, TypeError):
            continue
        if field not in ranges:
            ranges[field] = {}
        if suffix == "_min":
            ranges[field]["min"] = val
        else:
            ranges[field]["max"] = val
    return ranges


def _parse_condition_builder(query_params) -> dict:
    """解析 query 参数中的 cond_<fieldKey>=<op>，转换为 filter_dict。

    K 2026-06-18 任务：把"条件构建器"中的筛选条件接入选股。

    三种 preset 落地方案：
    1. 复合条件（如 rsi_oversold/volume_breakout/low_valuation）：
       写入 filter_dict[`__cond_<fieldKey>`] = {kind, field/op/value/...}，
       后续由 screener_service._apply_cond_special 处理。
    2. 1:1 映射的 preset（如 consecutive_up → consec_up_3、5 个 K线形态）：
       写入 filter_dict[<parquet_col>] = True（二进制列 =1 即命中）。
    3. 组合 preset（如 bottom_volume_macd = volume_breakout AND macd_golden_cross）：
       展开为两个条件。

    自编指标（fieldKey 以 `custom_` 开头）后端暂无 ETL 支持，跳过。

    返回: dict（写入到 filter_dict 的子集）
    """
    result = {}
    for param_name, param_value in query_params.items():
        if not param_name.startswith("cond_"):
            continue
        field_key = param_name[len("cond_"):]
        if not field_key:
            continue
        # 自编指标：后端暂无 ETL 支持，跳过（前端会兜底）
        if field_key.startswith("custom_"):
            continue

        # 0. 不支持的 preset（K 2026-06-18 决策：写 warning 后跳过）
        if field_key in COND_UNSUPPORTED_FIELD_KEYS:
            logger.warning(
                "条件构建器 preset %r 当前无 parquet 数据支持（K 2026-06-18 决策 ignore），已跳过",
                field_key,
            )
            continue

        # 1. 复合条件（需特判）
        if field_key in COND_SPECIAL_MAP:
            result[f"{_COND_SPECIAL_PREFIX}{field_key}"] = COND_SPECIAL_MAP[field_key]
            continue

        # 2. 组合 preset：展开
        if field_key == "bottom_volume_macd":
            result[f"{_COND_SPECIAL_PREFIX}volume_breakout"] = COND_SPECIAL_MAP["volume_breakout"]
            result["macd_low_golden_cross"] = True
            continue

        # 3. 1:1 映射 preset
        parquet_col = COND_DIRECT_FIELD_KEYS.get(field_key)
        if parquet_col:
            result[parquet_col] = True
            continue

        # 未识别的 fieldKey：忽略（不抛错，保持兼容性）
        logger.warning("条件构建器忽略未识别的 fieldKey: %s", field_key)

    return result


@router.get("/", summary="股票列表（支持筛选、排序、分页）")
def get_stocks(
    request: Request,
    filters: str = Query(None, description="K线形态筛选条件（逗号分隔）"),
    listed_board: str = Query(None, description="上市板块筛选"),
    industry: str = Query(None, description="行业筛选（逗号分隔）"),
    area: str = Query(None, description="地区筛选（逗号分隔）"),
    # 技术指标 pattern 筛选（2026-06-16 新增）
    tech_ma: str = Query(None, description="MA形态筛选（逗号分隔：long_align,short_align）"),
    tech_macd: str = Query(None, description="MACD形态筛选（逗号分隔：low_golden_cross,bottom_divergence,high_death_cross,top_divergence）"),
    tech_boll: str = Query(None, description="BOLL形态筛选（逗号分隔：break_upper,break_middle_up,break_middle_down,break_lower）"),
    tech_rsi: str = Query(None, description="RSI形态筛选（逗号分隔：low_golden_cross,high_death_cross,top_divergence,bottom_divergence）"),
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
            # 支持多值逗号分隔（如 "上海主板,创业板"）
            boards = [b.strip() for b in listed_board.split(",") if b.strip()]
            if len(boards) == 1:
                filter_dict["listed_board"] = boards[0]
            else:
                filter_dict["listed_board"] = boards

        # 解析行情/财务指标范围参数（*_min / *_max）
        indicator_ranges = _parse_indicator_ranges(request.query_params)
        for field, range_cond in indicator_ranges.items():
            filter_dict[field] = range_cond

        # 解析条件构建器 cond_<fieldKey>=<op>（K 2026-06-18 任务）
        cond_filters = _parse_condition_builder(request.query_params)
        filter_dict.update(cond_filters)

        # 解析技术指标 pattern 筛选参数（2026-06-16 新增）
        tech_pattern_map = {
            'ma': {
                'long_align': 'ma_long_align',
                'short_align': 'ma_short_align',
            },
            'macd': {
                'low_golden_cross': 'macd_low_golden_cross',
                'bottom_divergence': 'macd_bottom_divergence',
                'high_death_cross': 'macd_high_death_cross',
                'top_divergence': 'macd_top_divergence',
            },
            'boll': {
                'break_upper': 'boll_break_upper',
                'break_middle_up': 'boll_break_middle_up',
                'break_middle_down': 'boll_break_middle_down',
                'break_lower': 'boll_break_lower',
            },
            'rsi': {
                'low_golden_cross': 'rsi_low_golden_cross',
                'high_death_cross': 'rsi_high_death_cross',
                'top_divergence': 'rsi_top_divergence',
                'bottom_divergence': 'rsi_bottom_divergence',
            },
        }
        for tech_key, param_value in [('ma', tech_ma), ('macd', tech_macd), ('boll', tech_boll), ('rsi', tech_rsi)]:
            if param_value:
                for p in param_value.split(','):
                    p = p.strip()
                    if p in tech_pattern_map.get(tech_key, {}):
                        filter_dict[tech_pattern_map[tech_key][p]] = True

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