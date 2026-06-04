from fastapi import APIRouter, HTTPException, Depends, Query, Path
import logging
from typing import Optional
import re
from datetime import datetime

from core.api.models.schemas import SignalResponse
from core.service.signal_service import SignalService
from core.api.dependencies import get_loader

logger = logging.getLogger(__name__)
router = APIRouter(tags=["交易信号接口"])

# 股票代码校验正则 - 支持 000001.SZ、SH.000001、SZ.000001、000001 等多种格式
STOCK_CODE_PATTERN = r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'
# 有效信号类型（与 signal_service.signal_config 对齐）
VALID_SIGNAL_TYPES = {'macd_cross', 'rsi_oversold', 'rsi_overbought', 'bollinger_breakout', 'all'}


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


_signal_service: SignalService = None

def get_signal_service() -> SignalService:
    """获取信号服务单例（同步）"""
    global _signal_service
    if _signal_service is None:
        loader = get_loader()
        _signal_service = SignalService(loader)
    return _signal_service


SignalServiceDep = Depends(get_signal_service)


@router.get("/{stock_code}", response_model=SignalResponse, summary="获取买卖信号")
async def get_signals(
    stock_code: str = Path(..., description="股票代码，如 000001 或 SZ.000001"),
    signal_type: Optional[str] = Query(None, description="信号类型，支持 macd_cross/rsi_oversold/rsi_overbought/bollinger_breakout/all（默认 all）"),
    start_date: Optional[str] = Query(None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式 YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制（1-1000）"),
    signal_service: SignalService = SignalServiceDep
):
    """获取指定股票的交易信号"""
    logger.info(f"获取信号: {stock_code}, type={signal_type}")

    # 参数校验
    code = validate_stock_code(stock_code)

    # signal_type 默认 'all'
    sig_type = (signal_type or 'all').strip().lower()
    if sig_type not in VALID_SIGNAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的信号类型: '{signal_type}'，可选: {sorted(VALID_SIGNAL_TYPES)}"
        )

    validated_start = validate_date(start_date, "start_date")
    validated_end = validate_date(end_date, "end_date")
    validate_date_range(validated_start, validated_end)

    try:
        data = signal_service.get_signals(code, validated_start, validated_end, sig_type, limit)
    except Exception as e:
        logger.error(f"信号获取失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"信号服务异常: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail=f"未找到 {code} 的信号数据")

    return data