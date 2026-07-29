// constants.ts — 回测引擎集中常量定义
// 所有魔法数字统一管理，加注释说明来源

/** A股年交易日数估算（约252个交易日） */
export const TRADING_DAYS_PER_YEAR = 252;

/** A股最小交易单位（1手=100股） */
export const LOT_SIZE = 100;

/** 回测预热天数（K线数据拉取时往前多取的天数，确保指标计算有足够历史数据） */
export const PREHEAT_DAYS = 60;

/** K线数据拉取上限（后端最大限制） */
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