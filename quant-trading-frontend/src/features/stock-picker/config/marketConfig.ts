export interface MarketBoard {
  value: string
  label: string
}

export interface MarketConfig {
  value: string
  label: string
  boards: MarketBoard[]
  disabled: boolean
}

export const MARKET_CONFIG: Record<string, MarketConfig> = {
  cn: {
    value: 'cn',
    label: '沪深',
    boards: [
      { value: 'sh', label: '上海' },
      { value: 'sz', label: '深圳' },
      { value: 'cyb', label: '创业板' },
      { value: 'kcb', label: '科创板' },
    ],
    disabled: false,
  },
  hk: {
    value: 'hk',
    label: '港股',
    boards: [],
    disabled: true,
  },
  us: {
    value: 'us',
    label: '美股',
    boards: [],
    disabled: true,
  },
}

export const STOCK_RANGE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'watchlist', label: '仅看自选' },
]
