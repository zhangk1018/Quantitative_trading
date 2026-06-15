export interface IndicatorItem {
  id: string
  label: string
  field: string | null
  unit?: string
  disabled?: boolean
  disabledReason?: string
}

export const MARKET_INDICATORS: IndicatorItem[] = [
  { id: 'market_cap', label: '市值', field: 'market_cap', unit: '元' },
  { id: 'price', label: '价格', field: 'close', unit: '元' },
  { id: 'change_pct', label: '涨跌幅', field: 'change_pct', unit: '%' },
  { id: 'pe_static', label: '市盈率(静)', field: 'pe', unit: '' },
  { id: 'pe_ttm', label: '市盈率(TTM)', field: 'pe_ttm', unit: '' },
  { id: 'pb', label: '市净率', field: 'pb', unit: '' },
  { id: 'volume_ratio', label: '量比', field: 'volume_ratio', unit: '' },
  { id: 'amount', label: '成交额', field: 'amount', unit: '元' },
  { id: 'volume', label: '成交量', field: 'volume', unit: '股' },
  { id: 'turnover', label: '换手率', field: 'turnover_rate', unit: '%' },
]

export const FINANCIAL_INDICATORS: IndicatorItem[] = [
  { id: 'net_profit', label: '净利润', field: 'net_profit', unit: '元' },
  { id: 'revenue', label: '营业收入', field: 'revenue', unit: '元' },
  { id: 'roe', label: '净资产收益率', field: 'roe', unit: '%' },
]

export const TECHNICAL_INDICATORS: IndicatorItem[] = [
  { id: 'ma', label: 'MA', field: null, disabled: false },
  { id: 'macd', label: 'MACD', field: null, disabled: false },
  { id: 'boll', label: 'BOLL', field: null, disabled: false },
]

export interface FactorItem {
  id: string
  label: string
  defaultWeight: number
  color: string
}

export const FACTOR_CONFIG: FactorItem[] = [
  { id: 'turnover', label: '换手率', defaultWeight: 30, color: '#26A69A' },
  { id: 'ma_trend', label: 'MA趋势', defaultWeight: 40, color: '#2962FF' },
  { id: 'volume', label: '成交量', defaultWeight: 30, color: '#FFD700' },
]
