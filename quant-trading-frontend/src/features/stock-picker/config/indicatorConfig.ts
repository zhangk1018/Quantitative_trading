// ==================== 常量定义 ====================
export const PANEL_KEYS = {
  RANGE: 'range',
  MARKET: 'market',
  FINANCIAL: 'financial',
  TECHNICAL: 'technical',
  FACTOR: 'factor',
  CONDITION: 'condition',
  PATTERN: 'pattern',
} as const;

export type PanelKey = typeof PANEL_KEYS[keyof typeof PANEL_KEYS];

// ==================== 基础类型 ====================
export interface IndicatorItem {
  id: string;
  label: string;
  field?: string;
  unit?: string;
  disabled?: boolean;
  disabledReason?: string;
}

export const MARKET_INDICATORS: readonly IndicatorItem[] = [
  { id: 'market_cap', label: '市值', field: 'market_cap', unit: '亿元' },
  { id: 'price', label: '价格', field: 'close', unit: '元' },
  { id: 'change_pct', label: '涨跌幅', field: 'change_pct', unit: '%' },
  { id: 'pe_static', label: '市盈率(静)', field: 'pe', unit: '倍' },
  { id: 'pe_ttm', label: '市盈率(TTM)', field: 'pe_ttm', unit: '倍' },
  { id: 'pb', label: '市净率', field: 'pb', unit: '倍' },
  { id: 'volume_ratio', label: '量比', field: 'volume_ratio', unit: '倍' },
  { id: 'amount', label: '成交额', field: 'amount', unit: '亿元' },
  { id: 'volume', label: '成交量', field: 'volume', unit: '手' },
  { id: 'turnover', label: '换手率', field: 'turnover_rate', unit: '%' },
] as const;

export const FINANCIAL_INDICATORS: readonly IndicatorItem[] = [
  { id: 'net_profit', label: '净利润', field: 'net_profit', unit: '元' },
  { id: 'revenue', label: '营业收入', field: 'revenue', unit: '元' },
  { id: 'roe', label: '净资产收益率', field: 'roe', unit: '%' },
] as const;

// ==================== 技术指标 ====================
export type TechnicalOptionValue =
  | 'long_align'
  | 'short_align'
  | 'low_golden_cross'
  | 'bottom_divergence'
  | 'high_death_cross'
  | 'top_divergence'
  | 'break_upper'
  | 'break_middle_up'
  | 'break_middle_down'
  | 'break_lower';

export interface TechnicalOption {
  value: TechnicalOptionValue;
  label: string;
}

export interface TechnicalIndicatorItem extends IndicatorItem {
  field?: never;
  options: readonly TechnicalOption[];
}

export const TECHNICAL_INDICATORS: readonly TechnicalIndicatorItem[] = [
  {
    id: 'ma',
    label: 'MA',
    options: [
      { value: 'long_align', label: '多头排列' },
      { value: 'short_align', label: '空头排列' },
    ] as const,
  },
  {
    id: 'macd',
    label: 'MACD',
    options: [
      { value: 'low_golden_cross', label: '低位金叉' },
      { value: 'bottom_divergence', label: '底背离' },
      { value: 'high_death_cross', label: '高位死叉' },
      { value: 'top_divergence', label: '顶背离' },
    ] as const,
  },
  {
    id: 'boll',
    label: 'BOLL',
    options: [
      { value: 'break_upper', label: '升穿上轨' },
      { value: 'break_middle_up', label: '升穿中轨' },
      { value: 'break_middle_down', label: '跌穿中轨' },
      { value: 'break_lower', label: '跌穿下轨' },
    ] as const,
  },
  {
    id: 'rsi',
    label: 'RSI',
    options: [
      { value: 'low_golden_cross', label: '低位金叉' },
      { value: 'bottom_divergence', label: '底背离' },
      { value: 'high_death_cross', label: '高位死叉' },
      { value: 'top_divergence', label: '顶背离' },
    ] as const,
  },
] as const;

// ==================== K 线形态 ====================
export type PatternType =
  | 'hammer'
  | 'bullish_engulfing'
  | 'bearish_engulfing'
  | 'morning_star'
  | 'evening_star';

export interface PatternIndicatorItem {
  id: string;
  label: string;
  patternType: PatternType;
  defaultLookbackDays: number;
}

export const PATTERN_INDICATORS = [
  { id: 'hammer', label: '锤子线', patternType: 'hammer', defaultLookbackDays: 3 },
  { id: 'bullish_engulfing', label: '看涨吞没', patternType: 'bullish_engulfing', defaultLookbackDays: 3 },
  { id: 'bearish_engulfing', label: '看跌吞没', patternType: 'bearish_engulfing', defaultLookbackDays: 3 },
  { id: 'morning_star', label: '早晨之星', patternType: 'morning_star', defaultLookbackDays: 5 },
  { id: 'evening_star', label: '黄昏之星', patternType: 'evening_star', defaultLookbackDays: 5 },
] as const satisfies readonly PatternIndicatorItem[];

// LOOKBACK_OPTIONS value 改为 string，避免 Antd Select 类型问题
/** K线形态筛选默认回溯天数 */
export const DEFAULT_LOOKBACK_DAYS = 3;

export const LOOKBACK_OPTIONS = [
  { value: '1', label: '1天' },
  { value: '3', label: '3天' },
  { value: '5', label: '5天' },
  { value: '10', label: '10天' },
] as const;

// ==================== 因子配置 ====================
export interface FactorItem {
  id: string;
  label: string;
  defaultWeight: number;
  color: string;
}

export const FACTOR_CONFIG = [
  { id: 'turnover', label: '换手率', defaultWeight: 30, color: '#26A69A' },
  { id: 'ma_trend', label: 'MA趋势', defaultWeight: 40, color: '#2962FF' },
  { id: 'volume', label: '成交量', defaultWeight: 30, color: '#FFD700' },
] as const satisfies readonly FactorItem[];
