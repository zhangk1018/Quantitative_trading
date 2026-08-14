/**
 * scoreCalculator.ts — 《走进我的交易室》进场得分、出场得分、交易总得分计算
 *
 * 全部公式依据原著第8章「交易者电子表格」字段说明实现。
 * 核心思想：打分评估的是执行质量，不是预测未来盈亏。
 */

import type { LongShort, TradeGrade } from '../types';

// ─── 阈值（原著标准） ───
const GRADE_A_THRESHOLD = 30; // A级：总得分 > 30
const GRADE_B_THRESHOLD = 10; // B级：10 ≤ 总得分 ≤ 30
// C级：总得分 < 10

// ─── 1. 进场得分 ───

/**
 * 计算进场得分
 * 多头公式：(entry_price - day_low) / (day_high - day_low) × 100
 * 空头公式：(day_high - entry_price) / (day_high - day_low) × 100
 *
 * 分数越低越好，0=最优（最低点买入/最高点卖出），100=最差（追高/杀跌）。
 * 一字板（high===low）→ 0 分。
 */
export function calcEntryScore(
  entryPrice: number,
  dayHigh: number,
  dayLow: number,
  longShort: LongShort,
): number {
  if (dayHigh === dayLow) return 0; // 一字板

  const range = dayHigh - dayLow;
  const score = longShort === 'short'
    ? ((dayHigh - entryPrice) / range) * 100
    : ((entryPrice - dayLow) / range) * 100;

  return Math.max(0, Math.min(100, score));
}

// ─── 2. 出场得分 ───

/**
 * 计算出场得分
 * 多头公式：(exit_price - day_low) / (day_high - day_low) × 100
 * 空头公式：(day_high - exit_price) / (day_high - day_low) × 100
 *
 * 分数越高越好，100=最优（最高点卖出/最低点买回），0=最差。
 * 一字板（high===low）→ 100 分。
 */
export function calcExitScore(
  exitPrice: number,
  dayHigh: number,
  dayLow: number,
  longShort: LongShort,
): number {
  if (dayHigh === dayLow) return 100; // 一字板

  const range = dayHigh - dayLow;
  const score = longShort === 'short'
    ? ((dayHigh - exitPrice) / range) * 100
    : ((exitPrice - dayLow) / range) * 100;

  return Math.max(0, Math.min(100, score));
}

// ─── 3. 价格通道高度 ───

/**
 * 价格通道高度 = 进场当日日线振幅
 * 用于计算交易总得分。
 */
export function calcChannelHeight(dayHigh: number, dayLow: number): number {
  return dayHigh - dayLow;
}

// ─── 4. 交易总得分 ───

/**
 * 计算交易总得分
 * 多头公式：(exit_price - entry_price) / channel_height × 100
 * 空头公式：(entry_price - exit_price) / channel_height × 100
 *
 * 结果 > 100 封顶 100；负数保留（亏损）。
 * 等级：A > 30, B ≥ 10, C < 10
 */
export function calcTradeScore(
  entryPrice: number,
  exitPrice: number,
  channelHeight: number,
  longShort: LongShort,
): number {
  if (channelHeight === 0) return 0;

  let score: number;
  if (longShort === 'short') {
    score = ((entryPrice - exitPrice) / channelHeight) * 100;
  } else {
    score = ((exitPrice - entryPrice) / channelHeight) * 100;
  }

  return Math.min(score, 100); // 封顶 100
}

// ─── 5. 交易等级 ───

/**
 * 根据交易总得分划分等级
 * A > 30, B ≥ 10, C < 10
 */
export function calcTradeGrade(tradeScore: number): TradeGrade {
  if (tradeScore > GRADE_A_THRESHOLD) return 'A';
  if (tradeScore >= GRADE_B_THRESHOLD) return 'B';
  return 'C';
}

// ─── 按原著标准四舍五入到整数 ───

/**
 * 原著中得分示例都是整数，结果四舍五入到整数位。
 * 但保留原始精度便于后续聚合统计平均值。
 */
export function roundScore(score: number): number {
  return Math.round(score);
}