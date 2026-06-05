/**
 * klineTheme.ts - K线图表主题配色
 *
 * 设计原则：
 * - 跟随系统 prefers-color-scheme（Light/Dark/Auto）
 * - 涨跌色固定：红涨绿跌（同花顺国际惯例）
 * - MA 颜色与同花顺 000544 参考页一致
 */

export type ThemeMode = 'light' | 'dark'

/** MA 周期（与 indicators.ts 算法保持一致） */
export const MA_PERIODS = [5, 10, 20, 30, 60] as const

/** 单条 MA 配色（Light / Dark 双套） */
export interface MaColorPair {
  light: string
  dark: string
}

/** 5 条 MA 配色：MA5 蓝 / MA10 橙 / MA20 粉 / MA30 青 / MA60 紫（Light） */
export const MA_COLORS: Record<number, MaColorPair> = {
  5:  { light: '#265FFC', dark: '#5B8DEF' },
  10: { light: '#FFAA00', dark: '#FFB940' },
  20: { light: '#F564B9', dark: '#F584C4' },
  30: { light: '#00CCC3', dark: '#33D6CE' },
  60: { light: '#733ED6', dark: '#8E63DE' },
}

/** 单主题完整配色 */
export interface KlineTheme {
  mode: ThemeMode
  /** 主背景 */
  bg: string
  /** 面板背景（K线主图区） */
  panelBg: string
  /** 文字主色 */
  text: string
  /** 文字次色 */
  textMuted: string
  /** 网格线 */
  gridLine: string
  /** 坐标轴线 */
  axisLine: string
  /** 涨色（同花顺红） */
  up: string
  /** 跌色（同花顺绿） */
  down: string
  /** 涨色（带透明度，用于成交量柱） */
  upBar: string
  /** 跌色（带透明度） */
  downBar: string
  /** 十字光标线 */
  crosshair: string
}

export const LIGHT_THEME: KlineTheme = {
  mode: 'light',
  bg: '#f5f5f5',
  panelBg: '#ffffff',
  text: '#1f1f1f',
  textMuted: '#888888',
  gridLine: '#ececec',
  axisLine: '#d9d9d9',
  up: '#ef4444',
  down: '#22c55e',
  upBar: 'rgba(239, 68, 68, 0.65)',
  downBar: 'rgba(34, 197, 94, 0.65)',
  crosshair: '#b0b0b0',
}

export const DARK_THEME: KlineTheme = {
  mode: 'dark',
  bg: '#0d0d0d',
  panelBg: '#1a1a1a',
  text: '#e5e5e5',
  textMuted: '#888888',
  gridLine: '#2a2a2a',
  axisLine: '#3a3a3a',
  up: '#ef4444',
  down: '#22c55e',
  upBar: 'rgba(239, 68, 68, 0.65)',
  downBar: 'rgba(34, 197, 94, 0.65)',
  crosshair: '#555555',
}

/** 根据 mode 取主题 */
export function getTheme(mode: ThemeMode): KlineTheme {
  return mode === 'dark' ? DARK_THEME : LIGHT_THEME
}

/** 取指定 MA 周期在指定主题下的颜色 */
export function getMaColor(period: number, mode: ThemeMode): string {
  const pair = MA_COLORS[period]
  if (!pair) return mode === 'dark' ? '#999999' : '#666666'
  return mode === 'dark' ? pair.dark : pair.light
}

/** MA 图例显示名（统一带 "MA" 前缀） */
export const MA_LEGEND_NAMES: Record<number, string> = {
  5: 'MA5', 10: 'MA10', 20: 'MA20', 30: 'MA30', 60: 'MA60',
}
