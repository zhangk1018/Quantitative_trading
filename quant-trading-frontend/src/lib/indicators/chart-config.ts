// lib/indicators/chart-config.ts
// 图表视觉与指标配置 — 集中管理，便于主题切换和参数调整

export const CHART_THEME = {
  bg: '#131722',
  grid: 'rgba(42,46,57,0.5)',
  text: '#848E9C',
  bgHeader: '#1E222D',
  border: '#2A2E39',
  green: '#00d4aa',
  red: '#f23645',
  refLine: 'rgba(255,255,255,0.2)',
  crosshair: 'rgba(255,255,255,0.2)',
} as const;

export const MA_COLORS = {
  ma5: '#ff9800',
  ma10: '#2196f3',
  ma20: '#f5a623',
  ma60: '#9c27b0',
} as const;

export const BOLL_COLORS = {
  upper: '#4a90e2',
  mid: '#ffffff',
  lower: '#ef5350',
} as const;

export const MACD_COLORS = {
  dif: '#ffffff',
  dea: '#f5d900',
} as const;

export const RSI_COLORS = {
  rsi6: '#ff6b6b',
  rsi12: '#4ecdc4',
  rsi24: '#ffe66d',
} as const;

export const KDJ_COLORS = {
  k: '#ff9800',
  d: '#2196f3',
  j: '#9c27b0',
} as const;

/** 成交量颜色：开盘即涨（close >= open）为绿色，反之为红色 */
export const VOLUME_COLORS = {
  up: 'rgba(0,212,170,0.6)',
  down: 'rgba(242,54,69,0.6)',
} as const;

/** 自编指标颜色 */
export const CUSTOM_INDICATOR_COLORS = {
  line: '#ff6b6b',
} as const;

/** 参考线参数（RSI 的 30/70，KDJ 的 20/80） */
export const REF_LINES = {
  rsi: { low: 30, high: 70 },
  kdj: { low: 20, high: 80 },
} as const;

/** 各副图占主图的比例（top / bottom 为 scaleMargins 值） */
export const PANE_RATIOS = {
  main: { top: 0.02, bottom: 0.48 },
  volume: { top: 0.55, bottom: 0.31 },
  macd: { top: 0.72, bottom: 0.18 },
  osc: { top: 0.85, bottom: 0.05 },
} as const;

/** 指标默认周期 */
export const INDICATOR_PERIODS = {
  ma: [5, 10, 20, 60] as number[],
  boll: { period: 20, stdDev: 2 },
  macd: { fast: 12, slow: 26, signal: 9 },
  rsi: [6, 12, 24] as number[],
  kdj: { n: 9, m1: 3, m2: 3 },
} as const;

/** 蜡烛图颜色 */
export const CANDLE_COLORS = {
  up: CHART_THEME.green,
  down: CHART_THEME.red,
} as const;