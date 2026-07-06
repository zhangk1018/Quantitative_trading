// condition-detector.ts
// 筛选条件检测引擎 — 将 ConditionBuilder 的条件映射到 K 线日期上的检测事件
// 使用注册表模式，每个 condition fieldKey 对应一个 detectFn

import { cleanBars, calcRSI, sma, ema, type KlineBar } from './indicators';
import { detectAllPatterns } from './patternDetector';
import type { OHLCVArray, PatternType } from './types';

// ==================== 类型定义 ====================

export interface ConditionEvent {
  time: string;           // K 线日期，YYYY-MM-DD
  label: string;          // 条件显示名，如 "RSI超卖"
  fieldKey: string;       // 条件类型
  color: string;          // 标记颜色
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
  direction: 'buy' | 'sell' | 'neutral';
  value?: string;         // 触发时的具体数值，如 "RSI 28.3"
}

export interface ConditionDetectorResult {
  events: ConditionEvent[];
  undetectable: { fieldKey: string; label: string; reason: string }[];
}

// 中间计算结果
interface ComputedCache {
  closes: number[];
  volumes: number[];
  rsi6: (number | null)[];
  dif: (number | null)[];
  dea: (number | null)[];
  volMa5: (number | null)[];
  ohlcvArray: OHLCVArray[];
}

// ==================== 视觉配置 ====================

export const CONDITION_VISUAL_CONFIG: Record<string, {
  color: string;
  shape: ConditionEvent['shape'];
  label: string;
  direction: ConditionEvent['direction'];
  detectable: boolean;
  reason?: string;
}> = {
  rsi_oversold:       { color: '#26A69A', shape: 'arrowUp',  label: 'RSI超卖', direction: 'buy', detectable: true },
  volume_breakout:    { color: '#FF9800', shape: 'circle',   label: '放量突破', direction: 'neutral', detectable: true },
  macd_golden_cross:  { color: '#2196F3', shape: 'arrowUp',  label: 'MACD金叉', direction: 'buy', detectable: true },
  bottom_volume_macd: { color: '#4CAF50', shape: 'square',   label: '底部放量', direction: 'buy', detectable: true },
  consecutive_up:     { color: '#9C27B0', shape: 'square',   label: '连续上涨', direction: 'buy', detectable: true },
  low_valuation:      { color: '#888888', shape: 'circle',   label: '低估值',   direction: 'neutral', detectable: false, reason: '需基本面数据' },
  pattern_morning_star:      { color: '#26A69A', shape: 'arrowUp',  label: '早晨之星', direction: 'buy', detectable: true },
  pattern_evening_star:      { color: '#EF5350', shape: 'arrowDown', label: '黄昏之星', direction: 'sell', detectable: true },
  pattern_bullish_engulfing: { color: '#26A69A', shape: 'arrowUp',  label: '看涨吞没', direction: 'buy', detectable: true },
  pattern_bearish_engulfing: { color: '#EF5350', shape: 'arrowDown', label: '看跌吞没', direction: 'sell', detectable: true },
  pattern_hammer:            { color: '#2962FF', shape: 'arrowUp',  label: '锤子线',   direction: 'buy', detectable: true },
};

const PATTERN_TYPE_MAP: Record<string, PatternType> = {
  pattern_morning_star: 'morning_star',
  pattern_evening_star: 'evening_star',
  pattern_bullish_engulfing: 'bullish_engulfing',
  pattern_bearish_engulfing: 'bearish_engulfing',
  pattern_hammer: 'hammer',
};

// ==================== 指标缓存计算 ====================

function computeCache(bars: KlineBar[]): ComputedCache {
  const cleaned = cleanBars(bars);
  const closes = cleaned.map(b => b.close);
  const volumes = cleaned.map(b => b.volume);
  const rsi6 = calcRSI(closes, 6);
  const volMa5 = sma(volumes, 5);

  // MACD
  const ema12 = ema(closes as (number | null)[], 12);
  const ema26 = ema(closes as (number | null)[], 26);
  const dif: (number | null)[] = new Array(closes.length).fill(null);
  for (let i = 0; i < closes.length; i++) {
    if (ema12[i] !== null && ema26[i] !== null) {
      dif[i] = ema12[i]! - ema26[i]!;
    }
  }
  const dea = ema(dif, 9);

  // OHLCV for pattern detection
  const ohlcvArray: OHLCVArray[] = cleaned.map(b => [
    new Date(b.time.replace(/-/g, '/')).getTime() / 1000,
    b.open, b.high, b.low, b.close, b.volume,
  ]);

  return { closes, volumes, rsi6, dif, dea, volMa5, ohlcvArray };
}

// ==================== 检测函数 ====================

function detectRsiOversold(cache: ComputedCache, bars: KlineBar[]): ConditionEvent[] {
  const events: ConditionEvent[] = [];
  const config = CONDITION_VISUAL_CONFIG.rsi_oversold;
  for (let i = 0; i < cache.rsi6.length; i++) {
    if (cache.rsi6[i] !== null && cache.rsi6[i]! < 30) {
      events.push({
        time: bars[i].time,
        label: config.label,
        fieldKey: 'rsi_oversold',
        color: config.color,
        shape: config.shape,
        direction: config.direction,
        value: `RSI ${cache.rsi6[i]!.toFixed(1)}`,
      });
    }
  }
  return events;
}

function detectVolumeBreakout(cache: ComputedCache, bars: KlineBar[]): ConditionEvent[] {
  const events: ConditionEvent[] = [];
  const config = CONDITION_VISUAL_CONFIG.volume_breakout;
  for (let i = 0; i < cache.volumes.length; i++) {
    if (cache.volMa5[i] !== null && cache.volumes[i] > cache.volMa5[i]! * 2) {
      events.push({
        time: bars[i].time,
        label: config.label,
        fieldKey: 'volume_breakout',
        color: config.color,
        shape: config.shape,
        direction: config.direction,
        value: `量 ${cache.volumes[i].toFixed(0)}`,
      });
    }
  }
  return events;
}

function detectMacdGoldenCross(cache: ComputedCache, bars: KlineBar[]): ConditionEvent[] {
  const events: ConditionEvent[] = [];
  const config = CONDITION_VISUAL_CONFIG.macd_golden_cross;
  for (let i = 1; i < cache.dif.length; i++) {
    if (
      cache.dif[i] !== null && cache.dea[i] !== null &&
      cache.dif[i - 1] !== null && cache.dea[i - 1] !== null &&
      cache.dif[i]! > cache.dea[i]! && cache.dif[i - 1]! <= cache.dea[i - 1]!
    ) {
      events.push({
        time: bars[i].time,
        label: config.label,
        fieldKey: 'macd_golden_cross',
        color: config.color,
        shape: config.shape,
        direction: config.direction,
      });
    }
  }
  return events;
}

function detectBottomVolumeMacd(cache: ComputedCache, bars: KlineBar[]): ConditionEvent[] {
  const events: ConditionEvent[] = [];
  const config = CONDITION_VISUAL_CONFIG.bottom_volume_macd;
  for (let i = 0; i < cache.rsi6.length; i++) {
    if (cache.rsi6[i] !== null && cache.rsi6[i]! < 30 &&
        cache.volMa5[i] !== null && cache.volumes[i] > cache.volMa5[i]! * 2) {
      events.push({
        time: bars[i].time,
        label: config.label,
        fieldKey: 'bottom_volume_macd',
        color: config.color,
        shape: config.shape,
        direction: config.direction,
        value: `RSI ${cache.rsi6[i]!.toFixed(1)}`,
      });
    }
  }
  return events;
}

function detectConsecutiveUp(cache: ComputedCache, bars: KlineBar[]): ConditionEvent[] {
  const events: ConditionEvent[] = [];
  const config = CONDITION_VISUAL_CONFIG.consecutive_up;
  let streak = 0;
  for (let i = 0; i < cache.closes.length; i++) {
    if (i === 0) continue;
    if (cache.closes[i] > cache.closes[i - 1]) {
      streak++;
      if (streak >= 3) {
        const startIdx = i - streak + 1;
        for (let j = startIdx; j <= i; j++) {
          events.push({
            time: bars[j].time,
            label: config.label,
            fieldKey: 'consecutive_up',
            color: config.color,
            shape: config.shape,
            direction: config.direction,
            value: `连涨${streak}天`,
          });
        }
      }
    } else {
      streak = 0;
    }
  }
  return events;
}

// ==================== 检测引擎入口 ====================

/**
 * 对一组 K 线数据执行指定条件的检测
 * @param bars KlineBar[] 原始 K 线数据（按时间升序排列）
 * @param conditions 需要检测的条件列表（含 fieldKey 和 lookbackDays）
 * @returns 检测结果（事件列表 + 不可标注条件列表）
 */
export interface ConditionConfig {
  fieldKey: string;
  lookbackDays?: number;
}

export function detectConditions(
  bars: KlineBar[],
  conditions: ConditionConfig[],
): ConditionDetectorResult {
  const events: ConditionEvent[] = [];
  const undetectable: ConditionDetectorResult['undetectable'] = [];

  if (!bars || bars.length === 0) {
    return { events, undetectable };
  }

  // 计算复用指标缓存
  const cache = computeCache(bars);

  // 收集需要 pattern 检测的 fieldKey
  const patternFieldKeys = conditions
    .map(c => c.fieldKey)
    .filter(k => k.startsWith('pattern_') && CONDITION_VISUAL_CONFIG[k]?.detectable);

  // 批量执行 pattern 检测（全量检测，不做 lookback 截断）
  let patternHitDays: Record<string, number[]> | null = null;
  if (patternFieldKeys.length > 0) {
    const targetPatterns = patternFieldKeys
      .map(k => PATTERN_TYPE_MAP[k])
      .filter(Boolean);
    const patternResult = detectAllPatterns(cache.ohlcvArray, {}, targetPatterns);
    patternHitDays = patternResult.hitDays as Record<string, number[]>;
  }

  // 遍历每个条件执行检测
  for (const { fieldKey, lookbackDays } of conditions) {
    const config = CONDITION_VISUAL_CONFIG[fieldKey];
    if (!config) continue;

    if (!config.detectable) {
      undetectable.push({
        fieldKey,
        label: config.label,
        reason: config.reason || '该条件无法在K线上标注',
      });
      continue;
    }

    // Pattern 类型：展示所有检测到的形态
    // lookbackDays 仅用于后端 DB 筛选，图表标记展示全部形态位置
    // 原因：前端 heuristic 检测与后端 TA-Lib 的检测位置可能不完全对齐，
    // 但 DB 已正确过滤了时间窗口，图表标记作为可视化辅助不限制窗口
    if (fieldKey.startsWith('pattern_') && patternHitDays) {
      const patternType = PATTERN_TYPE_MAP[fieldKey];
      const hitDays = patternHitDays[patternType];
      if (hitDays && hitDays.length > 0) {
        const hitSet = new Set(hitDays);
        for (let i = 0; i < bars.length; i++) {
          if (hitSet.has(i)) {
            events.push({
              time: bars[i].time,
              label: config.label,
              fieldKey,
              color: config.color,
              shape: config.shape,
              direction: config.direction,
            });
          }
        }
      }
      continue;
    }

    // 非 pattern 类型
    let detected: ConditionEvent[];
    switch (fieldKey) {
      case 'rsi_oversold':
        detected = detectRsiOversold(cache, bars);
        break;
      case 'volume_breakout':
        detected = detectVolumeBreakout(cache, bars);
        break;
      case 'macd_golden_cross':
        detected = detectMacdGoldenCross(cache, bars);
        break;
      case 'bottom_volume_macd':
        detected = detectBottomVolumeMacd(cache, bars);
        break;
      case 'consecutive_up':
        detected = detectConsecutiveUp(cache, bars);
        break;
      default:
        detected = [];
    }
    events.push(...detected);
  }

  // 按时间升序排列事件（LWC setMarkers 要求）
  events.sort((a, b) => {
    if (typeof a.time === 'number' && typeof b.time === 'number') return a.time - b.time;
    if (typeof a.time === 'string' && typeof b.time === 'string') return a.time.localeCompare(b.time);
    return String(a.time).localeCompare(String(b.time));
  });
  return { events, undetectable };
}