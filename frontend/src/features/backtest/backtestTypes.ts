// backtestTypes.ts — 回测分析模块全部类型定义

import type { Dayjs } from 'dayjs';
import type { KlineBar } from '../../lib/indicators/indicators';

// ==================== 卖出策略 ====================

/**
 * 卖出策略类型（基于沪深300成分股2010-2023回测数据筛选）
 *
 * 策略一：高点回落移动止损 — 从持仓最高价回撤8%即卖出
 * 策略二：ATR吊灯止损 — 收盘价跌破(最高价-3×14日ATR)即卖出
 * 策略三：双均线死叉 — 10日EMA下穿30日EMA即卖出
 * custom：自编卖出策略（Python 脚本），配合 customSellStrategy 使用
 * layered_take_profit：分层止盈（分批卖出），配合 layeredTPParams 使用
 */
export type SellStrategy = 'trailing_stop' | 'atr_chandelier' | 'ema_cross' | 'custom' | 'layered_take_profit';

/** 卖出策略显示标签 */
export const SELL_STRATEGY_LABELS: Record<SellStrategy, string> = {
  trailing_stop: '高点回落移动止损（8%回撤）',
  atr_chandelier: 'ATR吊灯止损（3×14日ATR）',
  ema_cross: '双均线死叉（10/30 EMA）',
  custom: '自编卖出策略',
  layered_take_profit: '分层止盈（分批卖出）',
};

// ==================== 分层止盈（分批卖出） ====================

/**
 * 分层止盈参数（对齐「策略回测-选股条件分层止盈」语义，K 审阅 v2）
 * 阶段：建仓期(initial) 初始止损 + 买入失效止损 + TP1 → tp1_done 保本 + TP2 → tp2_done 底仓跟踪止盈 + 均线兜底
 */
export interface LayeredTPParams {
  /** 初始止损比例（-0.05 = -5%） */
  initialStopLossPct: number;
  /** 第一止盈目标涨幅（0.05 = +5%） */
  firstProfitPct: number;
  /** 第一止盈卖出比例（0.25 = 25%） */
  firstSellPct: number;
  /** 第二止盈目标涨幅（0.12 = +12%） */
  secondProfitPct: number;
  /** 第二止盈卖出比例（0.25 = 25%，与 firstSellPct 合计卖出部分） */
  secondSellPct: number;
  /** TP1 后保本止损比例（0.00 = 成本价） */
  breakevenStopPct: number;
  /** TP2 后锁定利润比例（0.04 = +4%，跟踪线下限） */
  lockProfitPct: number;
  /** TP2 后硬性底线安全阀（0.02 = +2%） */
  hardFloorPct: number;
  /** TP2 后峰值回撤阈值（0.04 = 4%） */
  trailingDrawdownPct: number;
  /** 均线兜底周期（20） */
  maPeriod: number;
  /** 均线破位确认天数（2） */
  maConfirmDays: number;
  /** 均线例外单日跌幅（0.06 = 6%） */
  maExceptionDropPct: number;
  /** 建仓期时间止损天数（10） */
  maxHoldDays: number;
  /** 止损成交价滑点（0.005 = 0.5%） */
  stopSlippagePct: number;
}

/** 分层止盈默认参数（与策略回测 DEFAULT_LAYERED_TP_PARAMS 一致） */
export const DEFAULT_LAYERED_TP_PARAMS: LayeredTPParams = {
  initialStopLossPct: -0.05,
  firstProfitPct: 0.05,
  firstSellPct: 0.25,
  secondProfitPct: 0.12,
  secondSellPct: 0.25,
  breakevenStopPct: 0.00,
  lockProfitPct: 0.04,
  hardFloorPct: 0.02,
  trailingDrawdownPct: 0.04,
  maPeriod: 20,
  maConfirmDays: 2,
  maExceptionDropPct: 0.06,
  maxHoldDays: 10,
  stopSlippagePct: 0.005,
};

// ==================== 条件定义 ====================

/** 自编指标条件的算子类型（对齐选股视图 CustomIndicator 的 INDICATOR_OPERATORS） */
export type BacktestIndicatorOperator =
  | '>'
  | '>='
  | '<'
  | '<='
  | '=='
  | 'range'
  | 'cross_up'
  | 'cross_down';

/** 自编指标条件的阈值：单值（如评分≥8）或区间（range 用 [low, high]） */
export type BacktestIndicatorThreshold = number | [number, number];

/** 自编指标条件 */
export interface BacktestCustomCondition {
  type: 'custom';
  /** 自编指标 ID */
  indicatorId: string;
  /** 自编指标名称（用于 UI 展示和日志） */
  indicatorName: string;
  /** 自编指标脚本公式（Worker 内无法访问 localStorage，必须随配置传入） */
  formula: string;
  /**
   * 判定算子（选股视图口径）。缺省兼容旧配置 → 退化为 score !== 0。
   * 可选值含 range（区间）、cross_up/cross_down（上穿/下穿）。
   */
  operator?: BacktestIndicatorOperator;
  /**
   * 判定阈值。单值以 number 表示；range 算子用 [low, high]。
   * 缺省（且 operator 非 range）→ 退化为 score !== 0。
   */
  threshold?: BacktestIndicatorThreshold;
}

/** 系统预设条件 */
export interface BacktestPresetCondition {
  type: 'preset';
  /** 预设条件 ID，如 'morningStarVolumeBreakout' */
  presetId: string;
  /** 预设条件显示名称 */
  presetName: string;
}

/**
 * 自编卖出策略条件（纯信号协议）
 *
 * 脚本复用自编指标 Pyodide 执行管线：输入 OHLCV（+量比）一维数组，
 * 输出每日卖出信号数组；引擎仅在持仓状态（state==='holding'）下消费。
 * 持仓上下文（entry/peak/顺延）由引擎管理，脚本不可见。
 */
export interface BacktestCustomSellCondition {
  type: 'custom';
  /** 自编卖出策略 ID */
  strategyId: string;
  /** 自编卖出策略名称（用于 UI 展示和日志） */
  strategyName: string;
  /** 自编卖出策略脚本公式（Worker 内无法访问 localStorage，必须随配置传入） */
  formula: string;
  /** 判定算子（对齐自编指标口径），缺省 → score !== 0 */
  operator?: BacktestIndicatorOperator;
  /** 判定阈值。单值以 number 表示；range 用 [low, high]。缺省 → score !== 0 */
  threshold?: BacktestIndicatorThreshold;
}

/**
 * 回测买入条件：支持自编指标和系统预设条件。
 * - 自编指标：Python 脚本在 Pyodide Worker 中执行，返回每日信号数组
 * - 系统预设：使用 condition-detector.ts 检测，与选股视图条件构建器逻辑一致
 */
export type BacktestCondition = BacktestCustomCondition | BacktestPresetCondition;

/** 系统预设条件定义 */
export interface PresetConditionDef {
  id: string;
  name: string;
  description: string;
  /** 对应的 condition-detector fieldKey 列表 */
  conditionKeys: string[];
  /**
   * 条件之间的时间窗口（交易日）。
   * 如果设置，表示 conditionKeys 中的条件在 windowDays 天内先后出现即视为满足，
   * 信号日设为最后一个条件出现的日子。
   * 如果不设置，表示所有条件在同一天同时满足。
   */
  windowDays?: number;
}

/** 系统预设条件列表（当前为空：原「晨星放量」预设已按需求移除） */
export const PRESET_CONDITIONS: PresetConditionDef[] = [];

// ==================== 指标参数配置 ====================

export interface IndicatorParams {
  ma5: number;
  ma10: number;
  ma20: number;
  ma60: number;
  bollPeriod: number;
  bollStd: number;
  macdFast: number;
  macdSlow: number;
  macdSignal: number;
  rsiPeriod: number;
  kdjK: number;
  kdjD: number;
  kdjJ: number;
}

export const DEFAULT_INDICATOR_PARAMS: IndicatorParams = {
  ma5: 5,
  ma10: 10,
  ma20: 20,
  ma60: 60,
  bollPeriod: 20,
  bollStd: 2,
  macdFast: 12,
  macdSlow: 26,
  macdSignal: 9,
  rsiPeriod: 6,
  kdjK: 9,
  kdjD: 3,
  kdjJ: 3,
};

// ==================== 回测配置 ====================

/** 回测股票（支持单只或多只批量回测） */
export interface BacktestStock {
  stockCode: string;
  stockName: string;
}

export interface BacktestConfig {
  stockCode: string;
  stockName: string;
  /**
   * 多股票批量回测列表（选择整个自选股分组时使用）。
   * 为空或仅一只时退化为单股回测（使用 stockCode/stockName）。
   */
  stocks?: BacktestStock[];
  startDate: string;
  endDate: string;
  capital: number;
  /** 买入条件：仅允许一个自编指标 */
  buyCondition: BacktestCondition;
  /** 卖出策略 */
  sellStrategy: SellStrategy;
  /**
   * 自编卖出策略条件（仅 sellStrategy==='custom' 时有效）。
   * 旧配置缺省/无效时引擎自动回退内置策略。
   */
  customSellStrategy?: BacktestCustomSellCondition;
  /** 分层止盈参数（仅 sellStrategy==='layered_take_profit' 时有效，缺省用 DEFAULT_LAYERED_TP_PARAMS） */
  layeredTPParams?: LayeredTPParams;
  /** 高点回落比例（仅trailing_stop），如 0.08 = 8% */
  trailingStopPct: number;
  /** ATR周期（仅atr_chandelier），默认14 */
  atrPeriod: number;
  /** ATR倍数（仅atr_chandelier），默认3 */
  atrMultiplier: number;
  /** 短期EMA周期（仅ema_cross），默认10 */
  emaShort: number;
  /** 长期EMA周期（仅ema_cross），默认30 */
  emaLong: number;
  indicatorParams: IndicatorParams;
  executionPrice: 'next_open' | 'next_close';
  maxDeferDays: number;
  feeRate: number;
  slippage: number;
  riskFreeRate: number;
}

export const DEFAULT_BACKTEST_CONFIG: Partial<BacktestConfig> = {
  capital: 100000,
  sellStrategy: 'trailing_stop',
  trailingStopPct: 0.08,
  atrPeriod: 14,
  atrMultiplier: 3,
  emaShort: 10,
  emaLong: 30,
  executionPrice: 'next_open',
  maxDeferDays: 3,
  feeRate: 0.00025,  // 万2.5（A股券商佣金主流费率）
  slippage: 0.0001,   // 万1（默认滑点）
  riskFreeRate: 0.03,
};

/**
 * 回测引擎配置：从 BacktestConfig 派生，包含引擎执行所需字段。
 * startDate/endDate 用于过滤交易日期范围。
 */
export type BacktestEngineConfig = Pick<
  BacktestConfig,
  | 'stockCode'
  | 'startDate'
  | 'endDate'
  | 'capital'
  | 'sellStrategy'
  | 'customSellStrategy'
  | 'layeredTPParams'
  | 'trailingStopPct'
  | 'atrPeriod'
  | 'atrMultiplier'
  | 'emaShort'
  | 'emaLong'
  | 'feeRate'
  | 'slippage'
  | 'riskFreeRate'
  | 'executionPrice'
  | 'maxDeferDays'
  | 'indicatorParams'
>;

/**
 * 回测配置面板表单值：在持久化配置基础上补充临时 UI 字段。
 * - indicatorId: 买入条件选择器当前选中的自编指标 ID（提交时转换为 buyCondition）
 * - dateRange: 日期范围选择器当前值（提交时拆分为 startDate/endDate）
 *
 * 注意：不包含 buyCondition，避免表单值与持久化字段冗余。
 */
export interface BacktestFormValues {
  stockCode?: string;
  stockName?: string;
  /** 批量回测股票列表（选择整个自选股分组时由表单填充） */
  stocks?: BacktestStock[];
  startDate?: string;
  endDate?: string;
  capital?: number;
  indicatorId?: string;
  dateRange?: [Dayjs, Dayjs];
  /** 卖出策略（表单中使用字符串，提交时转为 SellStrategy） */
  sellStrategy?: string;
  /** 分层止盈参数（仅选分层止盈时提交） */
  layeredTPParams?: LayeredTPParams;
  /** 高点回落比例 */
  trailingStopPct?: number;
  /** ATR周期 */
  atrPeriod?: number;
  /** ATR倍数 */
  atrMultiplier?: number;
  /** 短期EMA周期 */
  emaShort?: number;
  /** 长期EMA周期 */
  emaLong?: number;
}

// ==================== 回测引擎输入/输出 ====================

export interface BacktestInput {
  bars: KlineBar[];
  /** 买入条件：仅允许一个自编指标 */
  buyCondition: BacktestCondition;
  config: BacktestEngineConfig;
}

export type TradeDirection = 'buy' | 'sell' | 'close';

export interface Trade {
  id: number;
  direction: TradeDirection;
  entryTime: string;
  exitTime: string;
  entryPrice: number;
  exitPrice: number;
  shares: number;
  profit: number;
  profitPct: number;
  holdDays: number;
  isForcedClose: boolean;
  entryReason: string;
  exitReason: string;
  /**
   * 分组标识：同一笔建仓（一次买入）发生时的 bar index。
   * 用于分层止盈等「一次建仓多次分批卖出」时，把多次卖出聚合为一个完整交易统计。
   */
  groupId?: number;
}

export interface EquityPoint {
  time: string;
  equity: number;
  drawdown: number;
}

export interface BacktestSummary {
  totalReturn: number;
  annualizedReturn: number;
  winRate: number;
  profitLossRatio: number;
  maxDrawdown: number;
  maxConsecutiveLoss: number;
  avgHoldDays: number;
  sharpeRatio: number;
  totalTrades: number;
  forcedCloseCount: number;
  benchmarkReturn: number;
  tradingDays: number;
  warmupDays: number;
}

/** 诊断日志条目：记录回测过程中关键决策点 */
export interface DiagnosticEntry {
  /** 时间（K 线日期） */
  time: string;
  /** 事件类型 */
  event: 'buy_signal' | 'sell_signal' | 'buy_deferred' | 'buy_expired'
    | 'sell_deferred' | 'sell_expired' | 'insufficient_funds'
    | 'buy_executed' | 'sell_executed' | 'forced_close'
    | 'unexecuted_buy' | 'script_error' | 'buy_signal_holding_skip'
    | 'signal_before_range';
  /** 描述信息 */
  reason: string;
  /** 附加数据 */
  data?: Record<string, unknown>;
}

export interface BacktestOutput {
  trades: Trade[];
  equityCurve: EquityPoint[];
  summary: BacktestSummary;
  warnings: string[];
  /** 结构化诊断日志（无交易时用于暴露具体原因） */
  diagnostics: DiagnosticEntry[];
}

/** 批量回测中单只股票的回测结果 */
export interface BacktestUniverseResult {
  stockCode: string;
  stockName: string;
  /** 该股用于图表展示的 K 线数据 */
  bars: KlineBar[];
  output: BacktestOutput;
  /** 该股拉取数据或回测失败时的错误信息（成功时为空） */
  error?: string;
}

// ==================== 回测生命周期状态 ====================

export type BacktestPhase =
  | 'idle'
  | 'fetching'
  | 'calculating'
  | 'finished'
  | 'error'
  | 'cancelled';

export type CalcStage = 'fetching' | 'indicators' | 'signals' | 'simulating' | 'done';

export interface ProgressInfo {
  stage: CalcStage;
  percent: number;
  message: string;
}

// ==================== 存储结果 ====================

export interface StoredBacktestResult {
  id: string;
  createdAt: string;
  /** 存储 schema 版本，用于版本升级时的迁移逻辑 */
  version: number;
  config: BacktestConfig;
  output: BacktestOutput;
}

// ==================== 涨跌停工具 ====================

/** 根据股票代码前缀获取涨跌停比例 */
export function getLimitPctByCode(stockCode: string): number {
  const code = stockCode.trim();
  if (code.startsWith('300') || code.startsWith('688')) {
    return 0.20; // 创业板、科创板 20%
  }
  if (code.startsWith('8') || code.startsWith('43')) {
    return 0.30; // 北交所 30%（简化）
  }
  // ST 股票需额外判断，此处简化，可通过扩展参数覆盖
  return 0.10; // 主板默认 10%
}