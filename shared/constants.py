"""
constants.py - 共享常量定义

【设计目标】
- 字段白名单、枚举等"硬约束"放在这里
- 前后端都引用同一份，避免不一致
- 任何字段新增/删除必须先改这里

【修改纪律】
1. 新增字段 → 同步更新 ALLOWED_SORT_FIELDS / ALLOWED_FILTER_FIELDS
2. 新增枚举值 → 同步更新前端 types.ts
3. 删除字段 → 标注 DEPRECATED，给 2 个版本过渡期再删除
"""

from enum import Enum


# ============================================
# 上市板块枚举
# ============================================

class ListedBoard(str, Enum):
    """上市板块枚举（沪深京三地）"""
    MAIN = "主板"
    CHINEXT = "创业板"
    STAR = "科创板"
    BSE = "北交所"


# ============================================
# 排序字段白名单（防止 SQL 注入）
# ============================================

ALLOWED_SORT_FIELDS = {
    # 基础行情
    'change_pct', 'close', 'volume', 'amount',
    'turnover_rate', 'pe', 'pb', 'market_cap',
    'circ_mv',
    # 价格字段
    'high', 'low', 'open', 'pre_close', 'change',
    # 技术指标
    'ma5', 'ma10', 'ma20',
    'rsi_6', 'rsi_12', 'rsi_24',
    'macd', 'boll_upper', 'boll_mid', 'boll_lower',
    'kdj_k', 'kdj_d', 'kdj_j', 'cci',
    # 财务指标
    'pe_ttm', 'ps', 'ps_ttm', 'dv_ratio', 'dv_ttm',
    'volume_ratio', 'vol_ratio_5',
    'net_mf_amount', 'net_mf_vol',
    'float_share', 'total_share',
    'turnover_rate_f',
    'consec_up_days',
}


# ============================================
# 筛选字段白名单
# ============================================

ALLOWED_FILTER_FIELDS = {
    # K线形态
    'pattern_hammer', 'pattern_bullish_engulfing', 'pattern_bearish_engulfing',
    'pattern_morning_star', 'pattern_evening_star', 'pattern_bull_candle',
    # 突破信号
    'break_high_20', 'break_high_60',
    # 连续走势
    'consec_up_3', 'consec_up_5', 'consec_up_days',
    # 涨跌停
    'limit_up', 'limit_down',
    # 风险标记
    'is_st', 'is_new',
}


# ============================================
# 复权方式枚举
# ============================================

class AdjMethod(str, Enum):
    """
    复权方式（用于 K线 API）
    - none: 不复权
    - forward: 前复权（最新价格为基准，向历史回溯）
    - backward: 后复权（历史价格为基准，向未来推算）
    """
    NONE = "none"
    FORWARD = "forward"
    BACKWARD = "backward"


ALLOWED_ADJ_METHODS = {m.value for m in AdjMethod}
"""复权方式白名单（用于 API 参数校验）"""


# ============================================
# 数据周期枚举
# ============================================

class Cycle(str, Enum):
    """K线周期（与 stock_quotes.cycle 字段对齐）"""
    DAILY = "1d"
    WEEKLY = "1w"
    MONTHLY = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    MIN_60 = "60m"


# ============================================
# 信号类型枚举
# ============================================

class SignalType(str, Enum):
    """买卖信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


# ============================================
# 数据库表名常量
# ============================================

TABLE_STOCK_BASIC = "stock_basic"
TABLE_STOCK_QUOTES = "stock_quotes"
TABLE_STOCK_DAILY_SNAPSHOT = "stock_daily_snapshot"
TABLE_STOCK_INDICATORS = "stock_indicators"


# ============================================
# 数据源标识
# ============================================

DATASOURCE_TUSHARE = "tushare"
DATASOURCE_BAOSTOCK = "baostock"
DATASOURCE_AKSHARE = "akshare"
DATASOURCE_SINA = "sina"
DATASOURCE_TENCENT = "tencent"


# ============================================
# 默认分页
# ============================================

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


# ============================================
# API 响应码（区别于 HTTP 状态码）
# ============================================

class ApiCode(int, Enum):
    """API 业务状态码"""
    SUCCESS = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_ERROR = 500
    SERVICE_UNAVAILABLE = 503
