from fastapi import APIRouter, Path, Query, HTTPException, Depends
import logging
from typing import Optional
from functools import lru_cache
import re
from datetime import datetime

from core.api.models.schemas import KLineResponse
from core.service.kline_service import KlineService
from core.api.dependencies import get_loader

logger = logging.getLogger(__name__)
router = APIRouter(tags=["K线数据接口"])

# 股票代码校验正则 - 支持 000001.SZ、SH.000001、SZ.000001、000001 等多种格式
STOCK_CODE_PATTERN = r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'
# 有效K线周期
VALID_KLINE_PERIODS = {'daily', 'weekly', 'monthly'}


def validate_stock_code(code: str) -> str:
    """校验并规范化股票代码"""
    raw = code
    code = code.strip().upper()
    if not re.match(STOCK_CODE_PATTERN, code):
        raise HTTPException(
            status_code=400,
            detail=f"股票代码格式错误: '{raw}'，应为6位数字或带 SH/SZ 前缀（如 000001 或 SZ.000001）"
        )
    return code


def validate_date(date_str: Optional[str], label: str = "日期") -> Optional[str]:
    """校验日期格式 YYYY-MM-DD，返回规范化日期"""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{label}格式错误: '{date_str}'，应为 YYYY-MM-DD（如 2026-06-01）"
        )


def validate_date_range(start: Optional[str], end: Optional[str]):
    """校验日期范围：如果 start 和 end 均提供，必须 start <= end"""
    if start and end and start > end:
        raise HTTPException(
            status_code=400,
            detail=f"日期范围无效: start_date({start}) 不能晚于 end_date({end})"
        )


_kline_service: KlineService = None

def get_kline_service() -> KlineService:
    """获取 K线服务单例（同步）"""
    global _kline_service
    if _kline_service is None:
        loader = get_loader()
        _kline_service = KlineService(loader)
    return _kline_service


KlineServiceDep = Depends(get_kline_service)


@router.get("/{stock_code}", response_model=KLineResponse, summary="获取K线数据")
async def get_kline_data(
    stock_code: str = Path(..., description="股票代码，如 000001 或 SZ.000001"),
    period: str = Query("daily", description="K线周期，支持 daily/weekly/monthly"),
    start_date: Optional[str] = Query(None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式 YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制（1-1000）"),
    kline_service: KlineService = KlineServiceDep
):
    """获取指定股票的K线数据"""
    logger.info(f"获取K线: {stock_code}, 周期={period}")

    # 参数校验
    code = validate_stock_code(stock_code)

    if period not in VALID_KLINE_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的K线周期: '{period}'，可选: {sorted(VALID_KLINE_PERIODS)}"
        )

    validated_start = validate_date(start_date, "start_date")
    validated_end = validate_date(end_date, "end_date")
    validate_date_range(validated_start, validated_end)

    try:
        data = kline_service.get_kline_data(code, validated_start, validated_end, period, limit)
    except Exception as e:
        logger.error(f"K线数据获取失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"K线服务异常: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail=f"未找到 {code} 的K线数据")

    return data