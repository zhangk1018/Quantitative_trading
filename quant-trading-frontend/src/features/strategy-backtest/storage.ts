// src/features/strategy-backtest/storage.ts
// 策略回测默认设置存储层 | 迁移自 features/backtest/strategyBacktestSettingsStorage.ts
// 新增：配置迁移器（Migration Runner）+ 回滚安全网（Phase 2）

import type { StrategyBacktestDefaults } from './types';

const STORAGE_PREFIX = 'strategy-backtest/';
const STORAGE_KEY = `${STORAGE_PREFIX}defaults`;

// ==================== 旧键迁移（K审阅V3#4） ====================
const OLD_KEYS = ['backtest-defaults', 'backtest-defaults-v2'];

/**
 * 配置迁移器 — 检测旧存储键，迁移至新命名空间
 * 安全网：迁移前将旧配置备份至 backup/ 命名空间，保留时间戳
 */
function migrateConfig(): void {
  for (const oldKey of OLD_KEYS) {
    const oldValue = localStorage.getItem(oldKey);
    if (oldValue === null) continue;
    try {
      // 备份旧值（用于回滚）
      const backupKey = `${STORAGE_PREFIX}backup/${oldKey}_${Date.now()}`;
      localStorage.setItem(backupKey, oldValue);

      // 解析旧值并映射至新结构
      const oldConfig = JSON.parse(oldValue);
      const newConfig = mapOldToNew(oldConfig);

      // 写入新命名空间
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newConfig));

      // 删除旧键（Phase 2 改为等待稳定期后删除）
      localStorage.removeItem(oldKey);

      console.info(`[ConfigMigration] ${oldKey} → ${STORAGE_KEY} (OK, backup: ${backupKey})`);
    } catch (e) {
      console.warn(`[ConfigMigration] ${oldKey} 迁移失败，保留旧值`, e);
    }
  }
}

/** 旧配置 → 新配置的字段映射 */
function mapOldToNew(old: Record<string, unknown>): Record<string, unknown> {
  // 字段名映射表（旧字段名 → 新字段名）
  const fieldMap: Record<string, string> = {
    initial_capital: 'initialCapital',
    benchmark_code: 'benchmarkCode',
    benchmark_total_return: 'benchmarkTotalReturn',
    risk_free_rate: 'riskFreeRate',
    warmup_days: 'warmupDays',
    rebalance_interval: 'rebalanceInterval',
    max_positions: 'maxPositions',
    position_alloc: 'positionAlloc',
    single_stock_max_pct: 'singleStockMaxPct',
    idle_cash_return: 'idleCashReturn',
    idle_cash_rate: 'idleCashRate',
    fee_rate: 'feeRate',
    slippage: 'slippage',
    stamp_duty: 'stampDuty',
    min_commission: 'minCommission',
    stop_loss_pct: 'stopLossPct',
    take_profit_pct: 'takeProfitPct',
    max_hold_days: 'maxHoldDays',
    max_defer_days: 'maxDeferDays',
    defer_fail_action: 'deferFailAction',
    daily_loss_limit_enabled: 'dailyLossLimitEnabled',
    daily_loss_limit_pct: 'dailyLossLimitPct',
    max_drawdown_stop_enabled: 'maxDrawdownStopEnabled',
    max_drawdown_stop_pct: 'maxDrawdownStopPct',
  };

  const result: Record<string, unknown> = {};
  for (const [oldKey, value] of Object.entries(old)) {
    const newKey = fieldMap[oldKey] ?? oldKey;
    result[newKey] = value;
  }
  return result;
}

/**
 * ============================================
 * 默认值
 * ============================================
 */

export const DEFAULT_STRATEGY_BACKTEST_DEFAULTS: StrategyBacktestDefaults = {
  // ---------- Card 1: 基础参数 ----------
  initialCapital: 100_000_000, // 100万 = 100_000_000 分
  benchmarkCode: '000300.SH',
  benchmarkTotalReturn: false,
  riskFreeRate: 0.03, // 3%
  warmupDays: 60,

  // ---------- Card 2: 调仓与仓位 ----------
  rebalanceInterval: 5, // 每周（5个交易日）
  maxPositions: 10,
  positionAlloc: 'equal',
  singleStockMaxPct: 1.0, // 100% = 不限制
  idleCashReturn: 'none',
  idleCashRate: 0.02, // 2% 年化

  // ---------- Card 3: 交易成本 ----------
  feeRate: 0.00025, // 万2.5
  slippage: 0.0001, // 万1
  stampDuty: 0.001, // 千1
  minCommission: 500, // 5元 = 500分

  // ---------- Card 4: 风险控制（个股风控） ----------
  stopLossPct: -0.08, // -8%
  takeProfitPct: 0.25, // 25%
  maxHoldDays: 20,
  maxDeferDays: 3,
  deferFailAction: 'abandon',

  // ---------- Card 4: 组合级风控（默认关闭） ----------
  dailyLossLimitEnabled: false,
  dailyLossLimitPct: -0.05, // -5%
  maxDrawdownStopEnabled: false,
  maxDrawdownStopPct: -0.15, // -15%
};

/**
 * 读取策略回测默认设置
 * 若 localStorage 无数据或解析失败，返回默认值
 */
export function getStrategyBacktestDefaults(): StrategyBacktestDefaults {
  // 首次访问时执行迁移
  migrateConfig();

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS };
    const parsed = JSON.parse(raw);
    return {
      // Card 1
      initialCapital: parsed.initialCapital ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.initialCapital,
      benchmarkCode: parsed.benchmarkCode ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.benchmarkCode,
      benchmarkTotalReturn: parsed.benchmarkTotalReturn ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.benchmarkTotalReturn,
      riskFreeRate: parsed.riskFreeRate ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.riskFreeRate,
      warmupDays: parsed.warmupDays ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.warmupDays,
      // Card 2
      rebalanceInterval: parsed.rebalanceInterval ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.rebalanceInterval,
      maxPositions: parsed.maxPositions ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxPositions,
      positionAlloc: parsed.positionAlloc ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.positionAlloc,
      singleStockMaxPct: parsed.singleStockMaxPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.singleStockMaxPct,
      idleCashReturn: parsed.idleCashReturn ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.idleCashReturn,
      idleCashRate: parsed.idleCashRate ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.idleCashRate,
      // Card 3
      feeRate: parsed.feeRate ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.feeRate,
      slippage: parsed.slippage ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.slippage,
      stampDuty: parsed.stampDuty ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.stampDuty,
      minCommission: parsed.minCommission ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.minCommission,
      // Card 4
      stopLossPct: parsed.stopLossPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.stopLossPct,
      takeProfitPct: parsed.takeProfitPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.takeProfitPct,
      maxHoldDays: parsed.maxHoldDays ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxHoldDays,
      maxDeferDays: parsed.maxDeferDays ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxDeferDays,
      deferFailAction: parsed.deferFailAction ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.deferFailAction,
      dailyLossLimitEnabled: parsed.dailyLossLimitEnabled ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.dailyLossLimitEnabled,
      dailyLossLimitPct: parsed.dailyLossLimitPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.dailyLossLimitPct,
      maxDrawdownStopEnabled: parsed.maxDrawdownStopEnabled ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxDrawdownStopEnabled,
      maxDrawdownStopPct: parsed.maxDrawdownStopPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxDrawdownStopPct,
    };
  } catch {
    return { ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS };
  }
}

/**
 * 保存策略回测默认设置
 */
export function saveStrategyBacktestDefaults(defaults: StrategyBacktestDefaults): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
}

// ==================== 单位转换辅助函数 ====================

/** 分转元（如 10000000 → 100） */
export function fenToYuan(fen: number): number {
  return fen / 100;
}

/** 元转分（如 100 → 10000000） */
export function yuanToFen(yuan: number): number {
  return Math.round(yuan * 100);
}

/** 分转万元显示（如 10000000 → 100） */
export function fenToWanYuan(fen: number): number {
  return fen / 10000;
}

/** 万元转分（如 100 → 10000000） */
export function wanYuanToFen(wan: number): number {
  return Math.round(wan * 10000);
}

/** 手续费率转万分之显示（如 0.00025 → 2.5） */
export function feeRateToDisplay(rate: number): number {
  return Math.round(rate * 10000 * 100) / 100;
}

/** 万分之显示转手续费率（如 2.5 → 0.00025） */
export function displayToFeeRate(display: number): number {
  return display / 10000;
}

/** 印花税率转千分之显示（如 0.001 → 1） */
export function stampDutyToDisplay(rate: number): number {
  return Math.round(rate * 1000 * 100) / 100;
}

/** 千分之显示转印花税率（如 1 → 0.001） */
export function displayToStampDuty(display: number): number {
  return display / 1000;
}

/** 滑点率转万分之显示（如 0.0001 → 1） */
export function slippageToDisplay(rate: number): number {
  return Math.round(rate * 10000 * 100) / 100;
}

/** 万分之显示转滑点率（如 1 → 0.0001） */
export function displayToSlippage(display: number): number {
  return display / 10000;
}

/** 百分比转小数（如 3 → 0.03） */
export function pctToDecimal(pct: number): number {
  return pct / 100;
}

/** 小数转百分比显示（如 0.03 → 3） */
export function decimalToPct(decimal: number): number {
  return Math.round(decimal * 100 * 100) / 100;
}