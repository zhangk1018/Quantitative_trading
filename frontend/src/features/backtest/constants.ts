// constants.ts — 回测引擎集中常量定义
// 所有魔法数字统一管理，加注释说明来源

/** A股年交易日数估算（约252个交易日） */
export const TRADING_DAYS_PER_YEAR = 252;

/** A股最小交易单位（1手=100股） */
export const LOT_SIZE = 100;

/**
 * 回测预热下限（K线数据拉取时往前多取的天数，确保指标计算有足够历史数据）。
 *
 * 历史上 60 天曾被证实不足：对 EMA12/26、EMA50、Wilder ADX 这类"无穷记忆"递归指标，
 * 约 66 个预热交易日内无法收敛，导致近起始日信号得分偏低（协作单 36.0：002508 在
 * 2025-02-13 满量程得分 8 / 预热窗口仅 7，信号漏报致 T+1 无买入）。250 天对应约一年
 * 交易日，可覆盖 EMA50/ADX 充分收敛；KLINE_FETCH_LIMIT 保持后端上限 1000，打分口径与选股
 * 视图（全历史计算）一致。
 */
export const PREHEAT_DAYS = 250;

/**
 * K线数据拉取上限。必须 ≤ 后端 `GET /kline/{code}` 的 `limit` 校验上限 `le=1000`
 * （见 `backend/core/api/router/kline.py`），否则返回 422。
 * 1000 根 ≈ 约 4 年日线，足以覆盖默认回测区间（如 2025-01-01→今仅约 580 根）并容纳
 * 250 天预热；需超 1000 根的更长区间需后端放开上限（涉及后台改动，另提单）。
 */
export const KLINE_FETCH_LIMIT = 1000;

/** 预热期计算中兜底的最小天数（确保指标计算窗口足够） */
export const MIN_WARMUP_DAYS = 5;

/** 进度报告间隔（每处理 N 根 K 线报告一次进度） */
export const PROGRESS_REPORT_INTERVAL = 50;

/** 指标参数默认值 — 与 DEFAULT_INDICATOR_PARAMS 保持一致 */
export const DEFAULT_MA5 = 5;
export const DEFAULT_MA10 = 10;
export const DEFAULT_MA20 = 20;
export const DEFAULT_MA60 = 60;
export const DEFAULT_BOLL_PERIOD = 20;
export const DEFAULT_BOLL_STD = 2;
export const DEFAULT_MACD_FAST = 12;
export const DEFAULT_MACD_SLOW = 26;
export const DEFAULT_MACD_SIGNAL = 9;
export const DEFAULT_RSI_PERIOD = 6;

/** 回测配置默认值 */
export const DEFAULT_CAPITAL = 100000;
export const DEFAULT_FEE_RATE = 0;
export const DEFAULT_SLIPPAGE = 0;
export const DEFAULT_RISK_FREE_RATE = 0.03;
export const DEFAULT_MAX_DEFER_DAYS = 3;

/** 参数合法性边界 */
export const MIN_CAPITAL = 1;
export const MAX_CAPITAL = 1_000_000_000;
export const MIN_FEE_RATE = 0;
export const MAX_FEE_RATE = 0.1;
export const MIN_SLIPPAGE = 0;
export const MAX_SLIPPAGE = 0.1;
export const MIN_MAX_DEFER_DAYS = 0;
export const MAX_MAX_DEFER_DAYS = 30;

/** 涨跌停判断阈值（容差） */
export const LIMIT_UP_TOLERANCE = 0.995;
export const LIMIT_DOWN_TOLERANCE = 1.005;

/** IndexedDB 存储 schema 版本（变更时需提供迁移逻辑） */
export const STORAGE_SCHEMA_VERSION = 1;

/** 本地缓存最大回测结果数 */
export const MAX_STORED_RESULTS = 20;