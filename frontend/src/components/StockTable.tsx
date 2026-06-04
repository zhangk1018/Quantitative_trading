import { useState } from 'react'
import type { StockResponse } from '../types'

/**
 * 默认显示的列配置
 * 包含股票基本信息和核心指标
 */
const DEFAULT_COLS: { key: keyof StockResponse; label: string; align?: 'right' }[] = [
  { key: 'stock_code',       label: '代码' },
  { key: 'stock_name',       label: '名称' },
  { key: 'industry',         label: '行业' },
  { key: 'change_pct',       label: '涨跌幅', align: 'right' },
  { key: 'close',            label: '收盘价', align: 'right' },
  { key: 'pe',               label: 'PE',      align: 'right' },
  { key: 'pb',               label: 'PB',      align: 'right' },
  { key: 'market_cap',       label: '总市值(亿)', align: 'right' },
  { key: 'amount',           label: '成交额(亿)', align: 'right' },
  { key: 'turnover_rate',    label: '换手率', align: 'right' },
  { key: 'volume_ratio',     label: '量比',   align: 'right' },
  { key: 'net_mf_amount',    label: '净流入(万)', align: 'right' },
]

/**
 * 支持排序的字段集合
 * 只有这些字段可以点击表头进行排序
 * 对应后端 ALLOWED_SORT_FIELDS
 */
const SORTABLE_KEYS = new Set([
  'change_pct', 'close', 'volume', 'amount',
  'turnover_rate', 'pe', 'pb', 'market_cap',
  'circ_mv', 'ma5', 'ma10', 'ma20', 'rsi_6', 'macd',
  'boll_upper', 'boll_mid', 'boll_lower',
  'high', 'low', 'change', 'pe_ttm', 'ps', 'ps_ttm',
  'dv_ratio', 'dv_ttm', 'float_share', 'volume_ratio',
  'net_mf_amount', 'break_high_20', 'break_high_60', 'vol_ratio_5'
])

/**
 * 格式化数值显示
 * @param key - 字段名
 * @param val - 原始值
 * @returns 格式化后的字符串
 * 
 * 格式化规则：
 * - null/undefined → '-'
 * - 股票代码 → 直接返回字符串
 * - 涨跌幅 → '+X.XX%' 或 '-X.XX%'
 * - 换手率 → 'X.XX%'
 * - 总市值/流通市值 → 万元转亿（除以10000）
 * - 成交额 → 元转亿（除以100000000）
 * - 成交量 → 手保持不变
 * - 资金流向字段（万元）→ 保持原值
 * - 流通股 → 保持原值（万股）
 * - 布尔值（新高）→ '是' 或 ''
 * - 其他数值 → 保留两位小数
 */
function fmt(key: string, val: unknown): string {
  // 空值处理
  if (val === null || val === undefined) return '-'
  
  // 股票代码：直接返回字符串，不进行数字转换
  if (key === 'stock_code') return String(val)
  
  const n = Number(val)
  // 非数字直接返回字符串
  if (isNaN(n)) return String(val)
  
  // 涨跌幅：添加正负号和百分号
  if (key === 'change_pct') return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
  
  // 换手率：添加百分号
  if (key === 'turnover_rate') return n.toFixed(2) + '%'
  
  // 市值类字段：万元转换为亿
  if (key === 'market_cap' || key === 'circ_mv') return (n / 10000).toFixed(2)
  
  // 成交额：元转换为亿
  if (key === 'amount') return (n / 100000000).toFixed(2)
  
  // 成交量：保持原样（手）
  if (key === 'volume') return n.toLocaleString()
  
  // 5日均量：保持原样（手）
  if (key === 'v_ma5') return n.toLocaleString()
  
  // 流通股：保持原样（万股）
  if (key === 'float_share') return n.toFixed(0)
  
  // 资金流向字段（万元）：保持原值
  if (key === 'net_mf_amount' || key === 'buy_sm_amount' || key === 'sell_sm_amount' ||
      key === 'buy_md_amount' || key === 'sell_md_amount' || key === 'buy_lg_amount' ||
      key === 'sell_lg_amount' || key === 'buy_elg_amount' || key === 'sell_elg_amount') {
    return n.toFixed(0)
  }
  
  // 20日新高、60日新高：布尔值转换为文字
  if (key === 'break_high_20' || key === 'break_high_60') {
    return Boolean(n) ? '是' : ''
  }
  
  // 默认：保留两位小数
  return n.toFixed(2)
}

/**
 * 确定单元格颜色（红涨绿跌）
 * @param key - 字段名
 * @param val - 原始值
 * @returns TailwindCSS 颜色类名
 * 
 * 着色规则：
 * - 涨跌幅 > 0 → 红色（text-red-400）
 * - 涨跌幅 < 0 → 绿色（text-green-400）
 * - 涨跌额 > 0 → 红色
 * - 涨跌额 < 0 → 绿色
 * - 净流入 > 0 → 红色
 * - 净流入 < 0 → 绿色
 */
function cellColor(key: string, val: unknown): string {
  // 空值不着色
  if (val === null || val === undefined) return ''
  
  // 涨跌幅和涨跌额着色
  if (key === 'change_pct' || key === 'change') {
    const n = Number(val)
    if (!isNaN(n)) {
      if (n > 0) return 'text-red-400'   // 红色表示上涨
      if (n < 0) return 'text-green-400' // 绿色表示下跌
    }
  }
  
  // 净流入着色
  if (key === 'net_mf_amount') {
    const n = Number(val)
    if (!isNaN(n)) {
      if (n > 0) return 'text-red-400'   // 红色表示净流入
      if (n < 0) return 'text-green-400' // 绿色表示净流出
    }
  }
  
  return ''
}

/**
 * 股票表格组件属性接口
 */
interface Props {
  /** 股票数据行数组 */
  rows: StockResponse[]
  /** 总记录数 */
  total: number
  /** 当前页偏移量 */
  offset: number
  /** 每页数量 */
  limit: number
  /** 当前排序字段 */
  sortBy: string
  /** 是否升序排列 */
  sortAsc: boolean
  /** 激活的筛选条件数组 */
  activeFilters: string[]
  /** 排序回调函数 */
  onSort: (key: string) => void
  /** 分页变化回调函数 */
  onPageChange: (offset: number) => void
  /** 行点击回调（为后续 K线联动预留） */
  onRowClick?: (code: string) => void
}

/**
 * 股票表格组件
 * 
 * 功能：
 * 1. 显示股票列表（默认12列，可展开至完整字段）
 * 2. 支持点击列头排序（升序/降序切换）
 * 3. 支持分页（上一页/下一页）
 * 4. 涨跌幅和净流入颜色标记（红涨绿跌）
 * 5. 股票代码可点击跳转到同花顺页面
 * 6. 支持行点击回调（用于 K线联动）
 * 
 * @param props - 组件属性
 */
export default function StockTable({
  rows, total, offset, limit, sortBy, sortAsc, /* activeFilters */ onSort, onPageChange, onRowClick,
}: Props & { activeFilters?: string[] }) {
  // 控制是否展开额外字段
  const [expanded, setExpanded] = useState(false)

  /**
   * 展开时显示的额外列配置
   * 包含：开盘价、最高价、最低价、昨收、技术指标、资金流向、估值指标等字段
   */
  const extraCols: { key: keyof StockResponse; label: string; align?: 'right' }[] = [
    { key: 'open',             label: '开盘', align: 'right' },
    { key: 'high',             label: '最高', align: 'right' },
    { key: 'low',              label: '最低', align: 'right' },
    { key: 'pre_close',        label: '昨收', align: 'right' },
    { key: 'change',           label: '涨跌额', align: 'right' },
    { key: 'volume',           label: '成交量', align: 'right' },
    { key: 'pe_ttm',           label: 'PE-TTM', align: 'right' },
    { key: 'ps',               label: 'PS',    align: 'right' },
    { key: 'ps_ttm',           label: 'PS-TTM', align: 'right' },
    { key: 'dv_ratio',         label: '股息率', align: 'right' },
    { key: 'dv_ttm',           label: '股息率TTM', align: 'right' },
    { key: 'circ_mv',          label: '流通市值(亿)', align: 'right' },
    { key: 'float_share',      label: '流通股(万)', align: 'right' },
    { key: 'buy_sm_amount',    label: '小单买', align: 'right' },
    { key: 'sell_sm_amount',   label: '小单卖', align: 'right' },
    { key: 'buy_md_amount',    label: '中单买', align: 'right' },
    { key: 'sell_md_amount',   label: '中单卖', align: 'right' },
    { key: 'buy_lg_amount',    label: '大单买', align: 'right' },
    { key: 'sell_lg_amount',   label: '大单卖', align: 'right' },
    { key: 'buy_elg_amount',   label: '特大买', align: 'right' },
    { key: 'sell_elg_amount',  label: '特大卖', align: 'right' },
    { key: 'break_high_20',    label: '20日新高', align: 'right' },
    { key: 'break_high_60',    label: '60日新高', align: 'right' },
    { key: 'vol_ratio_5',      label: '5日量比', align: 'right' },
    { key: 'v_ma5',            label: '5日均量', align: 'right' },
    { key: 'ma5',              label: 'MA5',   align: 'right' },
    { key: 'ma10',             label: 'MA10',  align: 'right' },
    { key: 'ma20',             label: 'MA20',  align: 'right' },
    { key: 'rsi_6',            label: 'RSI6',  align: 'right' },
    { key: 'macd',             label: 'MACD',  align: 'right' },
    { key: 'boll_upper',       label: '布林上轨', align: 'right' },
    { key: 'boll_mid',         label: '布林中轨', align: 'right' },
    { key: 'boll_lower',       label: '布林下轨', align: 'right' },
  ]

  // 根据展开状态决定显示哪些列
  const allCols = expanded ? [...DEFAULT_COLS, ...extraCols] : DEFAULT_COLS
  
  // 计算总页数（至少为1）
  const totalPages = Math.max(1, Math.ceil(total / limit))
  
  // 计算当前页码（从1开始）
  const currentPage = Math.floor(offset / limit) + 1

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* 表格区域 */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs text-gray-300 border-collapse">
          {/* 表头：使用 sticky 实现滚动时固定 */}
          <thead className="sticky top-0 bg-gray-900 z-10">
            <tr>
              {allCols.map(col => (
                <th
                  key={String(col.key)}
                  // 仅可排序字段可以点击
                  onClick={SORTABLE_KEYS.has(String(col.key)) ? () => onSort(String(col.key)) : undefined}
                  className={[
                    'px-2 py-2 font-medium text-gray-400 border-b border-gray-700 whitespace-nowrap',
                    col.align === 'right' ? 'text-right' : 'text-left',
                    SORTABLE_KEYS.has(String(col.key)) ? 'cursor-pointer hover:text-white' : '',
                  ].join(' ')}
                >
                  {col.label}
                  {/* 显示排序箭头 */}
                  {sortBy === String(col.key) && (
                    <span className="ml-1">{sortAsc ? '↑' : '↓'}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          
          {/* 表格主体 */}
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.stock_code}
                // 行点击事件（如果提供了回调）
                onClick={() => onRowClick?.(row.stock_code)}
                className={[
                  // 偶数行和奇数行背景色交替
                  i % 2 === 0 ? 'bg-gray-800/50 hover:bg-gray-700' : 'bg-gray-800 hover:bg-gray-700',
                  // 如果有行点击回调，显示手型光标
                  onRowClick ? 'cursor-pointer' : '',
                ].join(' ')}
              >
                {allCols.map(col => (
                  <td
                    key={String(col.key)}
                    className={[
                      'px-2 py-1.5 border-b border-gray-700/50 whitespace-nowrap',
                      col.align === 'right' ? 'text-right font-mono' : '',
                      // 股票代码列使用蓝色
                      String(col.key) === 'ts_code' ? 'text-blue-400' : '',
                      // 应用颜色（红涨绿跌）
                      cellColor(String(col.key), row[col.key as keyof StockResponse]),
                    ].join(' ')}
                  >
                    {/* 股票代码列：显示为链接 */}
                    {String(col.key) === 'stock_code' ? (
                      <a
                        href={`https://stockpage.10jqka.com.cn/${String(row.stock_code).slice(0, 6)}/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {fmt(String(col.key), row[col.key as keyof StockResponse])}
                      </a>
                    ) : fmt(String(col.key), row[col.key as keyof StockResponse])}
                  </td>
                ))}
              </tr>
            ))}
            
            {/* 空数据提示 */}
            {rows.length === 0 && (
              <tr>
                <td colSpan={allCols.length} className="text-center py-12 text-gray-500">
                  暂无匹配数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 底部工具栏：展开按钮 + 分页控件 */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-gray-700 bg-gray-900 text-xs text-gray-400">
        {/* 展开/收起按钮 */}
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="hover:text-white border border-gray-600 hover:border-gray-400 px-2 py-1 rounded"
        >
          {expanded ? '收起 ▲' : '查看更多字段 ▼'}
        </button>

        {/* 分页控件 */}
        <div className="flex items-center gap-2">
          <span>第 {currentPage} / {totalPages} 页 ({total.toLocaleString()} 只)</span>
          
          {/* 上一页按钮：第一页时禁用 */}
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            className="px-2 py-1 border border-gray-600 rounded disabled:opacity-30 hover:enabled:border-gray-400"
          >
            上一页
          </button>
          
          {/* 下一页按钮：最后一页时禁用 */}
          <button
            type="button"
            disabled={offset + limit >= total}
            onClick={() => onPageChange(offset + limit)}
            className="px-2 py-1 border border-gray-600 rounded disabled:opacity-30 hover:enabled:border-gray-400"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}
