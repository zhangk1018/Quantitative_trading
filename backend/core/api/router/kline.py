from fastapi import APIRouter, Path, Query, HTTPException, Depends
import logging
from typing import Optional
from datetime import datetime

from core.api.models.schemas import KLineResponse
from core.service.kline_service import KlineService
from core.api.dependencies import get_loader, validate_stock_code_format, validate_date_range
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["K线数据接口"])

# 股票代码校验正则 - 已迁移到 dependencies.py，复用公共常量
# 见 dependencies.STOCK_CODE_PATTERN
# 有效K线周期 - 已迁移到 dependencies.VALID_KLINE_PERIODS

# 向后兼容别名（保留本模块的引用，避免破坏旧代码）
STOCK_CODE_PATTERN = r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'
VALID_KLINE_PERIODS = {'daily', 'weekly', 'monthly'}


def validate_stock_code(code: str) -> str:
    """校验并规范化股票代码（兼容函数，实际调用 dependencies.validate_stock_code_format）"""
    return validate_stock_code_format(code)


def validate_date(date_str: Optional[str], label: str = "日期") -> Optional[str]:
    """校验日期格式 YYYY-MM-DD 或 YYYYMMDD，返回规范化日期"""
    if not date_str:
        return None
    date_str = date_str.strip()
    # 接受 YYYY-MM-DD 和 YYYYMMDD 两种格式
    try:
        # 尝试 YYYY-MM-DD
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        pass
    try:
        # 尝试 YYYYMMDD
        datetime.strptime(date_str, '%Y%m%d')
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{label}格式错误: '{date_str}'，应为 YYYY-MM-DD 或 YYYYMMDD（如 2026-06-01 或 20260601）"
        )


# validate_date_range 已迁移到 dependencies.py


_kline_service: KlineService = None

def get_kline_service() -> KlineService:
    """获取 K线服务（单例，注入 PostgreSQLStorage 读取真实数据）"""
    global _kline_service
    if _kline_service is None:
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
        _kline_service = KlineService(loader, storage)
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