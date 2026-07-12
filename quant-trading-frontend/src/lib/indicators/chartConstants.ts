// lib/indicators/chartConstants.ts

import type { PatternType } from './types';

export const CHART_CONFIG = {
  BACKGROUND_COLOR: '#1E222D',
  TEXT_COLOR: '#848E9C',
  GRID_COLOR: '#2A2E39',
  CANDLE_UP_COLOR: '#26A69A',
  CANDLE_DOWN_COLOR: '#EF5350',
  DEFAULT_HEIGHT: 450,
  MIN_WIDTH: 300,
  MIN_HEIGHT: 200,
  RESIZE_DEBOUNCE_MS: 100,
} as const;

export interface DetectionConfig {
  morningStarPenetration: number;
  eveningStarPenetration: number;
  dojiBodyRatio: number;
  largeBodyRatio: number;
  hammerLowerShadowRatio: number;
  hammerUpperShadowRatio: number;
  requireGapForStar: boolean;
  hammerUpperTolerance: number;
}

/** 形态检测默认阈值（所有比例必须 >0，且建议 ≤10） */
export const DETECTION_CONFIG: DetectionConfig = {
  morningStarPenetration: 0.3,
  eveningStarPenetration: 0.3,
  dojiBodyRatio: 0.1,
  largeBodyRatio: 0.6,
  hammerLowerShadowRatio: 2.0,
  hammerUpperShadowRatio: 0.1,
  requireGapForStar: false,
  hammerUpperTolerance: 0.01,
};

/** 配置参数合法范围约束（用于校验） */
export const CONFIG_RANGES = {
  morningStarPenetration: { min: 0.01, max: 1 },
  eveningStarPenetration: { min: 0.01, max: 1 },
  dojiBodyRatio: { min: 0.001, max: 0.5 },
  largeBodyRatio: { min: 0.1, max: 1 },
  hammerLowerShadowRatio: { min: 0.1, max: 10 },
  hammerUpperShadowRatio: { min: 0, max: 1 },
  hammerUpperTolerance: { min: 0, max: 0.1 },
  requireGapForStar: { min: 0, max: 1 }, // boolean，仅校验类型
} as const;

/** 校验配置参数，非法值自动修正为默认 */
export function validateConfig(
  config: Partial<DetectionConfig>
): DetectionConfig {
  const defaultCfg = { ...DETECTION_CONFIG };
  const result = { ...defaultCfg, ...config };
  const mutableResult = result as Record<keyof DetectionConfig, number | boolean>;
  for (const key of Object.keys(defaultCfg) as (keyof DetectionConfig)[]) {
    const value = result[key];
    if (typeof value !== 'boolean' && typeof value !== 'number') {
      console.warn(`[validateConfig] Invalid type for ${key}, reset to default ${defaultCfg[key]}`);
      mutableResult[key] = defaultCfg[key];
      continue;
    }
    if (typeof value === 'number') {
      const range = CONFIG_RANGES[key];
      if (range) {
        if (value < range.min || value > range.max) {
          console.warn(`[validateConfig] ${key}=${value} out of range [${range.min}, ${range.max}], reset to ${defaultCfg[key]}`);
          mutableResult[key] = defaultCfg[key];
        }
      }
    }
    // boolean 类型不额外校验
  }
  return result;
}

export const PATTERN_MARKER_CONFIG: Record<
  PatternType,
  { color: string; text: string; shape: 'arrowUp' | 'arrowDown' }
> = {
  hammer: { color: '#2962FF', text: '锤子线', shape: 'arrowUp' },
  bullish_engulfing: { color: '#26A69A', text: '看涨吞没', shape: 'arrowUp' },
  bearish_engulfing: { color: '#EF5350', text: '看跌吞没', shape: 'arrowDown' },
  morning_star: { color: '#26A69A', text: '早晨之星', shape: 'arrowUp' },
  evening_star: { color: '#EF5350', text: '黄昏之星', shape: 'arrowDown' },
};

export const MA_CONFIG = [
  { key: 'ma5', period: 5, color: '#FBC02D' },
  { key: 'ma10', period: 10, color: '#2962FF' },
  { key: 'ma20', period: 20, color: '#E91E63' },
] as const;

/** 错误类型扩展 */
export enum ChartErrorType {
  INIT_FAILED = 'INIT_FAILED',
  DATA_INVALID = 'DATA_INVALID',
  SERIES_OPERATION_FAILED = 'SERIES_OPERATION_FAILED',
  RESIZE_FAILED = 'RESIZE_FAILED',
  PATTERN_DETECTION_FAILED = 'PATTERN_DETECTION_FAILED',
  CONFIG_INVALID = 'CONFIG_INVALID',
}

export class ChartError extends Error {
  constructor(
    public type: ChartErrorType,
    message: string,
    public cause?: unknown,
  ) {
    super(message);
    this.name = 'ChartError';
  }
}
