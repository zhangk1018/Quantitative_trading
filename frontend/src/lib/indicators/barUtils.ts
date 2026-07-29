// lib/indicators/barUtils.ts

import { OHLCV_OPEN, OHLCV_HIGH, OHLCV_LOW, OHLCV_CLOSE, OHLCV_VOLUME } from './types';
import type { OHLCVArray } from './types';

/** 获取开盘价 */
export function getOpen(bar: OHLCVArray): number {
  return bar[OHLCV_OPEN];
}

/** 获取最高价 */
export function getHigh(bar: OHLCVArray): number {
  return bar[OHLCV_HIGH];
}

/** 获取最低价 */
export function getLow(bar: OHLCVArray): number {
  return bar[OHLCV_LOW];
}

/** 获取收盘价 */
export function getClose(bar: OHLCVArray): number {
  return bar[OHLCV_CLOSE];
}

/** 获取成交量 */
export function getVolume(bar: OHLCVArray): number {
  return bar[OHLCV_VOLUME] ?? 0;
}

/**
 * 校验单根K线有效性（含价格合理性、高低价逻辑、成交量非负）
 */
export function isValidBar(bar: OHLCVArray): boolean {
  if (!bar || bar.length < 6) return false;
  const o = getOpen(bar),
        h = getHigh(bar),
        l = getLow(bar),
        c = getClose(bar),
        v = getVolume(bar);
  return (
    Number.isFinite(o) && Number.isFinite(h) &&
    Number.isFinite(l) && Number.isFinite(c) &&
    Number.isFinite(v) && v >= 0 &&
    o > 0 && h > 0 && l > 0 && c > 0 &&  // 价格必须为正
    h >= l && h >= Math.max(o, c) && l <= Math.min(o, c)
  );
}

/** 获取实体顶部 */
export function getBodyTop(bar: OHLCVArray): number {
  return Math.max(getOpen(bar), getClose(bar));
}

/** 获取实体底部 */
export function getBodyBottom(bar: OHLCVArray): number {
  return Math.min(getOpen(bar), getClose(bar));
}

/** 获取实体大小（绝对值） */
export function getBodySize(bar: OHLCVArray): number {
  return Math.abs(getClose(bar) - getOpen(bar));
}

/** 获取K线振幅（最高-最低） */
export function getRange(bar: OHLCVArray): number {
  return getHigh(bar) - getLow(bar);
}

/** 判断是否为阳线 */
export function isBullish(bar: OHLCVArray): boolean {
  return getClose(bar) > getOpen(bar);
}

/** 判断是否为阴线 */
export function isBearish(bar: OHLCVArray): boolean {
  return getClose(bar) < getOpen(bar);
}

/** 获取上影线长度 */
export function getUpperShadow(bar: OHLCVArray): number {
  return getHigh(bar) - getBodyTop(bar);
}

/** 获取下影线长度 */
export function getLowerShadow(bar: OHLCVArray): number {
  return getBodyBottom(bar) - getLow(bar);
}

/**
 * 预计算K线的核心指标（用于形态检测缓存）
 */
export interface PrecomputedBar {
  index: number;           // 原始数组索引
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;          // 新增成交量
  bodySize: number;
  range: number;
  upperShadow: number;
  lowerShadow: number;
  bullish: boolean;
  bearish: boolean;
  bodyTop: number;
  bodyBottom: number;
}

/**
 * 将OHLCV数组转换为预计算指标数组（跳过无效K线）
 */
export function precomputeBars(ohlcv: OHLCVArray[]): PrecomputedBar[] {
  const result: PrecomputedBar[] = [];
  for (let i = 0; i < ohlcv.length; i++) {
    const bar = ohlcv[i];
    if (!isValidBar(bar)) continue;
    const o = getOpen(bar),
          h = getHigh(bar),
          l = getLow(bar),
          c = getClose(bar),
          v = getVolume(bar);
    const bodySize = Math.abs(c - o);
    const range = h - l;
    const bodyTop = Math.max(o, c);
    const bodyBottom = Math.min(o, c);
    result.push({
      index: i,
      open: o,
      high: h,
      low: l,
      close: c,
      volume: v,
      bodySize,
      range,
      upperShadow: h - bodyTop,
      lowerShadow: bodyBottom - l,
      bullish: c > o,
      bearish: c < o,
      bodyTop,
      bodyBottom,
    });
  }
  return result;
}