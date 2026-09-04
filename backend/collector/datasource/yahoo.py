#!/usr/bin/env python3
"""
市场特性配置与代码规范化（原 Yahoo 数据源适配器精简版）。

背景：K 2026-09-04 决定弃用 yfinance / Yahoo 财经（限流严重、不稳定），
YahooDataSource 与下游功能（港美股基本面 / 汇率 / 指数探针）已一并删除。
本模块仅保留被 AkShare 行情下载（collector/datasource/akshare.py）复用的
通用市场配置 MarketConfig 与代码规范化 normalize_code。

关键设计：
- MarketConfig 市场特性抽象：避免 `if market=='hk'` 散落业务，扩展日/英只需加配置
- 代码规范化：港股统一 4 位宽（`0700.HK`、`09988.HK`→`9988.HK`），美股原样大写
- 批间随机休眠 2.0~2.4s（对应 25~30 请求/分钟）：供 import_hk/us_daily 的 rate_limit_sleep 使用
"""
from dataclasses import dataclass, field
from typing import Dict


# =====================================================================
# 市场特性配置
# =====================================================================
@dataclass
class MarketConfig:
    """市场特性抽象：集中描述某市场的下载/清洗/存储特性。

    新增市场（如日本 .T / 英国 .L）只需在此加一条配置，业务代码零改动。
    """
    market: str                                    # 市场标识：cn / hk / us ...
    currency: str                                  # 本位币：CNY / HKD / USD
    timezone: str                                  # 默认时区（缺失时用）
    yahoo_suffix: str = ""                          # Yahoo 代码后缀（美股空，港股 .HK）
    has_limit_up_down: bool = False                 # 是否有涨跌停（仅 A 股）
    trading_hours: str = "09:30-16:00"             # 描述用
    default_period: str = "max"                     # --init 全量拉取周期
    incremental_lookback_days: int = 7              # 增量兜底回溯天数（通常从最后交易日+1）
    # 分片与限流参数
    batch_size: int = 20                            # 单批最大标的数
    batch_retry_min_sleep: float = 10.0            # 429 重试随机休眠下限（秒）
    batch_retry_max_sleep: float = 30.0            # 429 重试随机休眠上限（秒）
    # 批间随机休眠下限/上限（秒）：控制请求节拍 25~30 个/分钟（K 2026-09-04 要求统一）。
    # 60s/30=2.0s ~ 60s/25=2.4s，配合请求自身耗时，实际吞吐约 20~30 个/分钟且不会突破上限。
    batch_interval_min_sleep: float = 2.0         # 批间随机休眠下限（秒）
    batch_interval_max_sleep: float = 2.4        # 批间随机休眠上限（秒）
    max_retries: int = 3                            # 单批最大重试次数
    # 停牌处理
    suspended_log_threshold_days: int = 30         # 停牌超过该天数在 ETL 日志记录


# 预置市场配置（仅港/美，后续日/英可追加）
MARKET_CONFIGS: Dict[str, MarketConfig] = {
    'hk': MarketConfig(
        market='hk', currency='HKD', timezone='Asia/Hong_Kong',
        yahoo_suffix='.HK', has_limit_up_down=False, trading_hours='09:30-16:00',
    ),
    'us': MarketConfig(
        market='us', currency='USD', timezone='America/New_York',
        yahoo_suffix='', has_limit_up_down=False, trading_hours='09:30-16:00',
        default_period='max',
    ),
}


def get_market_config(market: str) -> MarketConfig:
    """获取市场配置，未知市场抛 ValueError。"""
    if market not in MARKET_CONFIGS:
        raise ValueError(f"不支持的 market: {market}（支持: {list(MARKET_CONFIGS)}）")
    return MARKET_CONFIGS[market]


# =====================================================================
# 代码规范化
# =====================================================================
def _normalize_hk_code(code: str) -> str:
    """港股代码规范化：规范化为 4 位宽（右对齐，不足补前导零），附带 .HK 后缀。

    实测关键（2026-09-03）：港股代码固定【4 位宽】，不足 4 位须补前导零，
    不能去前导零到短码——否则数据源查不到：
      '0700.HK' -> '0700.HK'（4 位，保留前导零）
      '700'     -> '0700.HK'（不足 4 位补零）
      '09988.HK' -> '9988.HK'（超 4 位去前导零到 4 位：09988→9988）
      '1299.HK' -> '1299.HK'（已是 4 位）
      '1.HK'     -> '0001.HK'（1→0001）
    """
    code = str(code).strip().upper()
    if code.endswith('.HK'):
        num = code[:-3]
    elif '.' in code:  # 其他后缀（.SS/.SZ 等）不属港股，原样返回调用方自行处理
        return code
    else:
        num = code
    # 仅保留数字部分；先取有效整数再去前导零，避免 '00001' 这类
    try:
        num_int = int(num)
    except ValueError:
        return f"{num}.HK"
    # 超 4 位则去前导零（09988→9988）；否则补零到 4 位（700→0700）
    if num_int >= 10000:
        digits = str(num_int)
    else:
        digits = str(num_int).zfill(4)
    return f"{digits}.HK"


def normalize_code(code: str, market: str) -> str:
    """按市场规范化代码（入库统一格式）。

    港股：去前导零 + .HK（`_normalize_hk_code`）
    美股：原样（大写）
    """
    if market == 'hk':
        return _normalize_hk_code(code)
    if market == 'us':
        return str(code).strip().upper()
    return str(code).strip()
