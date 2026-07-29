// hooks/chartUtils.ts

import { z } from 'zod';
import type { KLineItem, SignalItem, OHLCVArray } from '../../../lib/indicators/types';
import { ChartError, ChartErrorType } from '../../../lib/indicators/chartConstants';

// ---------- Schema 定义（增强校验） ----------
const KLineItemSchema = z.object({
  time: z.string().min(1).refine((s) => !isNaN(Date.parse(s)), {
    message: 'Invalid time string (must be parseable by Date)',
  }),
  open: z.number().positive().max(1e8, 'Price too high (>1e8)'),
  high: z.number().positive().max(1e8),
  low: z.number().positive().max(1e8),
  close: z.number().positive().max(1e8),
  volume: z.number().nonnegative().max(1e12, 'Volume too high').optional(),
}).refine((data) => data.high >= data.low && data.high >= data.open && data.high >= data.close && data.low <= data.open && data.low <= data.close, {
  message: 'High must be >= Low and both must contain Open/Close',
});

const SignalItemSchema = z.object({
  time: z.string().min(1).refine((s) => !isNaN(Date.parse(s)), {
    message: 'Invalid time string (must be parseable by Date)',
  }),
  position: z.enum(['aboveBar', 'belowBar']),
  shape: z.enum(['arrowUp', 'arrowDown', 'circle', 'square']),
  color: z.string().min(1),
  text: z.string().optional(),
});

/**
 * 校验K线数据，过滤无效项
 * @param data - 待校验数据
 * @param strict - 若为true，遇到无效数据抛出 ChartError；否则静默过滤并输出警告
 * @returns 有效K线项数组
 */
export function validateKLineData(data: unknown, strict = false): KLineItem[] {
  if (!Array.isArray(data)) {
    if (strict) throw new ChartError(ChartErrorType.DATA_INVALID, 'KLine data must be an array');
    return [];
  }

  const result: KLineItem[] = [];
  for (const item of data) {
    const parsed = KLineItemSchema.safeParse(item);
    if (parsed.success) {
      result.push(parsed.data);
    } else {
      const errorMsg = parsed.error.issues.map(e => `${e.path.join('.')}: ${e.message}`).join('; ');
      console.warn(`[validateKLineData] Invalid item skipped: ${errorMsg}`, item);
      if (strict) {
        throw new ChartError(ChartErrorType.DATA_INVALID, `Invalid KLine item: ${errorMsg}`, parsed.error);
      }
    }
  }
  return result;
}

export function validateSignals(data: unknown, strict = false): SignalItem[] {
  if (!Array.isArray(data)) {
    if (strict) throw new ChartError(ChartErrorType.DATA_INVALID, 'Signal data must be an array');
    return [];
  }

  const result: SignalItem[] = [];
  for (const item of data) {
    const parsed = SignalItemSchema.safeParse(item);
    if (parsed.success) {
      result.push(parsed.data);
    } else {
      const errorMsg = parsed.error.issues.map(e => `${e.path.join('.')}: ${e.message}`).join('; ');
      console.warn(`[validateSignals] Invalid signal skipped: ${errorMsg}`, item);
      if (strict) {
        throw new ChartError(ChartErrorType.DATA_INVALID, `Invalid signal item: ${errorMsg}`, parsed.error);
      }
    }
  }
  return result;
}

/**
 * 将 KLineItem[] 转换为 OHLCVArray[]（带有效性校验）
 * @param klineData - 已验证的K线数据
 * @param strict - 转换失败时是否抛出异常
 * @returns OHLCV数组
 */
export function toOHLCVArray(klineData: KLineItem[], strict = false): OHLCVArray[] {
  const result: OHLCVArray[] = [];
  for (const k of klineData) {
    const timeMs = Date.parse(k.time);
    if (isNaN(timeMs)) {
      const msg = `Invalid time string: ${k.time}`;
      console.warn(`[toOHLCVArray] ${msg}`);
      if (strict) throw new ChartError(ChartErrorType.DATA_INVALID, msg);
      continue;
    }
    const ts = timeMs / 1000;
    // 额外数值防护（schema已校验，但确保安全）
    if (k.open <= 0 || k.high <= 0 || k.low <= 0 || k.close <= 0 || k.high < k.low) {
      const msg = `Invalid price values: open=${k.open}, high=${k.high}, low=${k.low}, close=${k.close}`;
      console.warn(`[toOHLCVArray] ${msg}`);
      if (strict) throw new ChartError(ChartErrorType.DATA_INVALID, msg);
      continue;
    }
    result.push([ts, k.open, k.high, k.low, k.close, k.volume ?? 0]);
  }
  return result;
}

/**
 * 基于时间有序特性的高效 diff（双指针）
 * 假设两个数组均按 time 升序排列，若未排序则自动降级为 Map 实现
 */
export function diffMarkers<T extends { time: string }>(
  oldArr: T[],
  newArr: T[],
): { added: T[]; removed: T[]; unchanged: T[] } {
  // 检查是否有序（简单抽样检查前几个元素）
  const isSorted = (arr: T[]): boolean => {
    if (arr.length < 2) return true;
    for (let i = 1; i < arr.length; i++) {
      if (arr[i].time < arr[i - 1].time) return false;
    }
    return true;
  };

  // 若任一数组无序，降级为 Map 方式（O(n+m) 但常数较大）
  if (!isSorted(oldArr) || !isSorted(newArr)) {
    console.warn('[diffMarkers] Arrays not sorted, using Map fallback');
    const oldMap = new Map(oldArr.map(item => [item.time, item]));
    const newMap = new Map(newArr.map(item => [item.time, item]));
    const added: T[] = [];
    const removed: T[] = [];
    const unchanged: T[] = [];
    for (const [time, item] of newMap) {
      if (oldMap.has(time)) unchanged.push(item);
      else added.push(item);
    }
    for (const [time, item] of oldMap) {
      if (!newMap.has(time)) removed.push(item);
    }
    return { added, removed, unchanged };
  }

  // 双指针
  const added: T[] = [];
  const removed: T[] = [];
  const unchanged: T[] = [];
  let i = 0, j = 0;
  while (i < oldArr.length && j < newArr.length) {
    const cmp = oldArr[i].time.localeCompare(newArr[j].time);
    if (cmp === 0) {
      unchanged.push(newArr[j]);
      i++; j++;
    } else if (cmp < 0) {
      removed.push(oldArr[i]);
      i++;
    } else {
      added.push(newArr[j]);
      j++;
    }
  }
  while (i < oldArr.length) removed.push(oldArr[i++]);
  while (j < newArr.length) added.push(newArr[j++]);

  return { added, removed, unchanged };
}