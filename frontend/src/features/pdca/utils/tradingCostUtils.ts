/**
 * tradingCostUtils.ts — 交易成本计算工具
 *
 * 职责：从系统设置读取交易成本参数，提供费用计算函数
 * 设计：计算函数均为纯函数（所有参数显式传入或通过 getTradingCostSettings 获取）
 * 缓存：getTradingCostSettings 内部缓存配置对象，避免重复 localStorage 读取
 *       缓存仅在 saveBacktestDefaults 被调用时由 BacktestDefaultsPanel 主动清除
 *
 * A股费用结构：
 *   买入：券商佣金（最低5元） + 过户费（十万分之一）
 *   卖出：券商佣金（最低5元） + 印花税（万5，仅卖出） + 过户费（十万分之一）
 *
 * 数据来源：BacktestDefaultsPanel 中的交易成本参数
 * - 手续费率（feeRate）：万分之，默认万2.5
 * - 滑点（slippage）：万分之，默认万1
 * - 印花税（stampDuty）：万分之，默认万5（仅卖出收取）
 * - 过户费（transferFee）：十万分之，默认十万分之一
 * - 最低佣金（minCommission）：A股统一5元
 */

import { getBacktestDefaults } from '@/features/backtest/backtestSettingsStorage';

// ── 缓存（事件驱动，无固定TTL） ────────────────────────────────────────

let cachedConfig: TradingCostSettings | null = null;

// ── 类型 ──────────────────────────────────────────────────────────────

export interface TradingCostSettings {
  /** 手续费率（小数，如 0.00025 = 万分之2.5） */
  feeRate: number;
  /** 滑点率（小数，如 0.0001 = 万分之1） */
  slippage: number;
  /** 印花税率（小数，如 0.0005 = 万5，仅卖出收取） */
  stampDuty: number;
  /** 过户费率（小数，如 0.00001 = 十万分之一） */
  transferFee: number;
  /** 最低佣金（元），A股统一5元 */
  minCommission: number;
}

// ── 输入校验 ──────────────────────────────────────────────────────────

function isValidTradeInput(price: number, quantity: number): boolean {
  return Number.isFinite(price) && price > 0 && Number.isFinite(quantity) && quantity >= 1;
}

function isValidPrice(price: number): boolean {
  return Number.isFinite(price) && price > 0;
}

// ── 配置读取（带缓存，事件驱动失效） ──────────────────────────────────

/**
 * 读取系统设置中的交易成本参数
 * 内部缓存配置对象，避免频繁 localStorage 读取
 * 缓存仅在以下情况刷新：
 *  - 首次调用
 *  - 调用 clearTradingCostCache() 后（由保存配置时触发）
 */
export function getTradingCostSettings(): TradingCostSettings {
  if (cachedConfig) {
    return cachedConfig;
  }

  const defaults = getBacktestDefaults();
  cachedConfig = {
    feeRate: defaults.feeRate || 0.00025,
    slippage: defaults.slippage || 0.0001,
    stampDuty: defaults.stampDuty || 0.0005,
    transferFee: defaults.transferFee || 0.00001,
    minCommission: defaults.minCommission ?? 5,
  };
  return cachedConfig;
}

/**
 * 主动清除交易成本缓存
 * 配置保存后调用此函数，确保下次计算使用最新值
 */
export function clearTradingCostCache(): void {
  cachedConfig = null;
}

/** @deprecated 测试专用，与 clearTradingCostCache 相同，语义更清晰 */
export const resetTradingCostCache = clearTradingCostCache;

// ── 跨标签页缓存同步 ──────────────────────────────────────────────────

// 监听其他标签页的配置变更，自动清除缓存
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key === 'backtest_defaults' && e.newValue !== e.oldValue) {
      cachedConfig = null;
    }
  });
}

// ── 四舍五入辅助 ──────────────────────────────────────────────────────

/** 四舍五入到分（2位小数） */
function roundToCent(amount: number): number {
  return Math.round(amount * 100) / 100;
}

// ── 核心计算函数（公共 API） ──────────────────────────────────────────

/**
 * 计算佣金（券商佣金），买入/卖出通用
 * 公式：max(成交金额 × 手续费率, 最低佣金)，结果四舍五入到分
 * @param price  每股价格（元）
 * @param quantity  数量（股）
 * @returns 佣金金额（元），非法输入返回 0
 */
export function calcCommission(price: number, quantity: number): number {
  if (!isValidTradeInput(price, quantity)) return 0;
  const { feeRate, minCommission } = getTradingCostSettings();
  const raw = price * quantity * feeRate;
  return roundToCent(Math.max(raw, minCommission));
}

/**
 * 计算过户费，买入/卖出通用
 * 公式：成交金额 × 过户费率，结果四舍五入到分
 * @param price  每股价格（元）
 * @param quantity  数量（股）
 * @returns 过户费金额（元），非法输入返回 0
 */
export function calcTransferFee(price: number, quantity: number): number {
  if (!isValidTradeInput(price, quantity)) return 0;
  const { transferFee } = getTradingCostSettings();
  return roundToCent(price * quantity * transferFee);
}

/**
 * 计算印花税（仅卖出收取）
 * 公式：成交金额 × 印花税率，结果四舍五入到分
 * @param price  出场价（元）
 * @param quantity  卖出数量（股）
 * @returns 印花税金额（元），非法输入返回 0
 */
export function calcStampDuty(price: number, quantity: number): number {
  if (!isValidTradeInput(price, quantity)) return 0;
  const { stampDuty } = getTradingCostSettings();
  return roundToCent(price * quantity * stampDuty);
}

/**
 * 计算每股滑点
 * 公式：入场价 × 滑点率，结果四舍五入到分
 * @param price  入场价（元）
 * @returns 每股滑点金额（元/股），非法输入返回 0
 */
export function calcSlippageCost(price: number): number {
  if (!isValidPrice(price)) return 0;
  const { slippage } = getTradingCostSettings();
  return roundToCent(price * slippage);
}

// ── 向后兼容的废弃别名（迁移期保留，后续移除） ────────────────────────

/** @deprecated 使用 calcCommission 替代 */
export const calcEntryCommission = calcCommission;
/** @deprecated 使用 calcCommission 替代 */
export const calcExitCommission = calcCommission;
/** @deprecated 使用 calcTransferFee 替代 */
export const calcEntryTransferFee = calcTransferFee;
/** @deprecated 使用 calcTransferFee 替代 */
export const calcExitTransferFee = calcTransferFee;
/** @deprecated 使用 calcStampDuty 替代 */
export const calcExitStampDuty = calcStampDuty;
/** @deprecated 使用 calcSlippageCost 替代 */
export const calcSlipPoint = calcSlippageCost;