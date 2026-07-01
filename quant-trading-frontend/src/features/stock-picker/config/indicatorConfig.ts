export interface IndicatorItem {
  id: string
  label: string
  field: string | null
  unit?: string
  disabled?: boolean
  disabledReason?: string
}

export const MARKET_INDICATORS: IndicatorItem[] = [
  { id: 'market_cap', label: '市值', field: 'market_cap', unit: '亿元' },
  { id: 'price', label: '价格', field: 'close', unit: '元' },
  { id: 'change_pct', label: '涨跌幅', field: 'change_pct', unit: '%' },
  { id: 'pe_static', label: '市盈率(静)', field: 'pe', unit: '' },
  { id: 'pe_ttm', label: '市盈率(TTM)', field: 'pe_ttm', unit: '' },
  { id: 'pb', label: '市净率', field: 'pb', unit: '' },
  { id: 'volume_ratio', label: '量比', field: 'volume_ratio', unit: '' },
  { id: 'amount', label: '成交额', field: 'amount', unit: '亿元' },
  { id: 'volume', label: '成交量', field: 'volume', unit: '手' },
  { id: 'turnover', label: '换手率', field: 'turnover_rate', unit: '%' },
]

export const FINANCIAL_INDICATORS: IndicatorItem[] = [
  { id: 'net_profit', label: '净利润', field: 'net_profit', unit: '元' },
  { id: 'revenue', label: '营业收入', field: 'revenue', unit: '元' },
  { id: 'roe', label: '净资产收益率', field: 'roe', unit: '%' },
]

export interface TechnicalOption {
  /** 选项值（序列化为 URL 参数） */
  value: string
  /** 中文标签 */
  label: string
}

export interface TechnicalIndicatorItem extends IndicatorItem {
  /** 弹窗内的固定选项（取消自定义，保持紧凑） */
  options: TechnicalOption[]
}

export const TECHNICAL_INDICATORS: TechnicalIndicatorItem[] = [
  {
    id: 'ma',
    label: 'MA',
    field: null,
    disabled: false,
    options: [
      { value: 'long_align', label: '多头排列' },
      { value: 'short_align', label: '空头排列' },
    ],
  },
  {
    id: 'macd',
    label: 'MACD',
    field: null,
    disabled: false,
    options: [
      { value: 'low_golden_cross', label: '低位金叉' },
      { value: 'bottom_divergence', label: '底背离' },
      { value: 'high_death_cross', label: '高位死叉' },
      { value: 'top_divergence', label: '顶背离' },
    ],
  },
  {
    id: 'boll',
    label: 'BOLL',
    field: null,
    disabled: false,
    options: [
      { value: 'break_upper', label: '升穿上轨' },
      { value: 'break_middle_up', label: '升穿中轨' },
      { value: 'break_middle_down', label: '跌穿中轨' },
      { value: 'break_lower', label: '跌穿下轨' },
    ],
  },
  {
    id: 'rsi',
    label: 'RSI',
    field: null,
    disabled: false,
    options: [
      { value: 'low_golden_cross', label: '低位金叉' },
      { value: 'high_death_cross', label: '高位死叉' },
      { value: 'top_divergence', label: '顶背离' },
      { value: 'bottom_divergence', label: '底背离' },
    ],
  },
]

export interface FactorItem {
  id: string
  label: string
  defaultWeight: number
  color: string
}

// ==================== K 线形态配置 ====================

export interface PatternIndicatorItem {
  id: string;
  label: string;
  /** 对应的 PatternType 值 */
  patternType: string;
  /** 默认回溯天数 */
  defaultLookbackDays: number;
}

export const PATTERN_INDICATORS: PatternIndicatorItem[] = [
  { id: 'hammer', label: '锤子线', patternType: 'hammer', defaultLookbackDays: 3 },
  { id: 'bullish_engulfing', label: '看涨吞没', patternType: 'bullish_engulfing', defaultLookbackDays: 3 },
  { id: 'bearish_engulfing', label: '看跌吞没', patternType: 'bearish_engulfing', defaultLookbackDays: 3 },
  { id: 'morning_star', label: '早晨之星', patternType: 'morning_star', defaultLookbackDays: 5 },
  { id: 'evening_star', label: '黄昏之星', patternType: 'evening_star', defaultLookbackDays: 5 },
];

export const LOOKBACK_OPTIONS = [
  { value: 1, label: '1天' },
  { value: 3, label: '3天' },
  { value: 5, label: '5天' },
  { value: 10, label: '10天' },
];

export const FACTOR_CONFIG: FactorItem[] = [
  { id: 'turnover', label: '换手率', defaultWeight: 30, color: '#26A69A' },
  { id: 'ma_trend', label: 'MA趋势', defaultWeight: 40, color: '#2962FF' },
  { id: 'volume', label: '成交量', defaultWeight: 30, color: '#FFD700' },
]
