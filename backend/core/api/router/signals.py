from fastapi import APIRouter, HTTPException, Depends, Query, Path
import logging
from typing import Optional
from datetime import datetime

from core.api.models.schemas import SignalResponse
from core.service.signal_service import SignalService
from core.api.dependencies import get_loader, validate_stock_code_format, validate_date_range, VALID_SIGNAL_TYPES
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["交易信号接口"])

# 股票代码校验正则 - 已迁移到 dependencies.STOCK_CODE_PATTERN
# 有效信号类型 - 已迁移到 dependencies.VALID_SIGNAL_TYPES

# 向后兼容别名
STOCK_CODE_PATTERN = r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'
VALID_SIGNAL_TYPES_LOCAL = VALID_SIGNAL_TYPES  # 向后兼容


def validate_stock_code(code: str) -> str:
    """校验并规范化股票代码（兼容函数）"""
    return validate_stock_code_format(code)


def validate_date(date_str: Optional[str], label: str = "日期") -> Optional[str]:
    """校验日期格式 YYYY-MM-DD 或 YYYYMMDD"""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        pass
    try:
        datetime.strptime(date_str, '%Y%m%d')
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{label}格式错误: '{date_str}'，应为 YYYY-MM-DD 或 YYYYMMDD"
        )


# validate_date_range 已迁移到 dependencies.py


_signal_service: SignalService = None

def get_signal_service() -> SignalService:
    """获取信号服务单例（同步），注入 PostgreSQLStorage 读取真实数据"""
    global _signal_service
    if _signal_service is None:
        loader = get_loader()
        db_config = config.get('database', {})
        storage = PostgreSQLStorage({
            'host': db_config.get('host', 'localhost'),
            'port': db_config.get('port', 5432),
            'database': db_config.get('database', 'quant_trading'),
            'username': db_config.get('username', 'quant_user'),
            'password': db_config.get('password', ''),
        })
        storage.connect()
        _signal_service = SignalService(loader, storage)
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