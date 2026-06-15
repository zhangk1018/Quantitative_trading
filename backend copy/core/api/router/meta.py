"""
router/meta.py - 元数据接口路由

提供系统元数据、筛选条件配置、统计数据等接口。
"""

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
import pandas as pd

from core.api.models.schemas import MetaResponse, FilterGroup, ApiResponse
from core.service.screener_service import ScreenerService
from collector.db.loader import DataLoader
from core.api.dependencies import get_loader, get_screener_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["元数据"])


@router.get("/", summary="获取系统元数据")
def get_meta(
    loader: DataLoader = Depends(get_loader),
    screener: ScreenerService = Depends(get_screener_service),
) -> ApiResponse[MetaResponse]:
    """
    获取系统元数据
    
    返回统一响应信封格式 {code, message, data}
    """
    try:
        df = loader.df
        industry_options = sorted(df["industry"].dropna().unique().tolist())[:100]
        area_options = sorted(df["area"].dropna().unique().tolist())[:50]
        
        meta_data = MetaResponse(
            trade_date=loader.trade_date,
            total=len(df),
            groups=[g.model_dump() for g in screener.get_filter_meta()],
            industry_options=industry_options,
            area_options=area_options,
        )
        
        return ApiResponse(
            code=200,
            message="success",
            data=meta_data,
        )
    except Exception as e:
        logger.exception("获取元数据失败")
        return ApiResponse(
            code=500,
            message=f"获取元数据失败: {str(e)}",
            data=None,
        )


@router.get("/filters", response_model=List[FilterGroup], summary="获取筛选条件列表")
def get_filters(
    screener: ScreenerService = Depends(get_screener_service),
) -> List[FilterGroup]:
    return screener.get_filter_meta()


@router.get("/stats", summary="获取系统统计数据")
def get_stats(
    loader: DataLoader = Depends(get_loader),
) -> Dict[str, Any]:
    try:
        df = loader.df

        # 动态检测板块列名
        board_col = None
        for col in ("board", "listed_board"):
            if col in df.columns:
                board_col = col
                break

        by_board = {}
        if board_col:
            col_series = df[board_col].astype(str)
            board_keywords = {
                "上海主板": ["上海主板", "SH"],
                "深圳主板": ["深圳主板", "SZ"],
                "创业板": ["创业", "300"],
                "科创板": ["科创", "688"],
                "北交所": ["北交"],
            }
            for board_name, keywords in board_keywords.items():
                mask = pd.Series(False, index=df.index)
                for kw in keywords:
                    mask |= col_series.str.contains(kw, na=False)
                by_board[board_name] = int(mask.sum())

        # 价格统计
        close_exists = "close" in df.columns and not df["close"].isna().all()
        price_stats = {
            "avg_close": float(df["close"].mean()) if close_exists else None,
            "max_close": float(df["close"].max()) if close_exists else None,
            "min_close": float(df["close"].min()) if close_exists else None,
        }

        return {
            "total_stocks": len(df),
            "by_board": by_board,
            "price_stats": price_stats,
        }
    except KeyError as e:
        logger.warning("统计数据缺少字段: %s", e)
        raise HTTPException(status_code=400, detail=f"缺失必要字段: {str(e)}")
    except Exception as e:
        logger.exception("获取统计数据失败")
        raise HTTPException(status_code=500, detail=f"统计计算异常: {str(e)}")