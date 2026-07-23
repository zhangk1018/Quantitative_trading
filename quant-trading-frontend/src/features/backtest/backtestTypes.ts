// backtestTypes.ts — 回测分析模块全部类型定义

import type { Dayjs } from 'dayjs';
import type { KlineBar } from '../../lib/indicators/indicators';

// ==================== 条件定义 ====================

/**
 * 回测买入条件：仅支持自编指标。
 * 脚本约定：返回每日信号数组，1 表示满足买入，0 表示不满足。
 */
export interface BacktestCondition {
  /** 自编指标 ID */
  indicatorId: string;
  /** 自编指标名称（用于 UI 展示和日志） */
  indicatorName: string;
  /** 自编指标脚本公式（Worker 内无法访问 localStorage，必须随配置传入） */
  formula: string;
}

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

export interface BacktestConfig {
  stockCode: string;
  stockName: string;
  startDate: string;
  endDate: string;
  capital: number;
  /** 买入条件：仅允许一个自编指标 */
  buyCondition: BacktestCondition;
  indicatorParams: IndicatorParams;
  executionPrice: 'next_open' | 'next_close';
  maxDeferDays: number;
  feeRate: number;
  slippage: number;
  riskFreeRate: number;
}

export const DEFAULT_BACKTEST_CONFIG: Partial<BacktestConfig> = {
  capital: 100000,
  executionPrice: 'next_open',
  maxDeferDays: 3,
  feeRate: 0,
  slippage: 0,
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
export interface BacktestFormValues extends Omit<BacktestConfig, 'buyCondition'> {
  indicatorId?: string;
  dateRange?: [Dayjs, Dayjs];
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
    | 'unexecuted_buy' | 'script_error';
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