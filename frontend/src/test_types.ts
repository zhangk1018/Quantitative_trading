/**
 * test_types.ts - 类型定义测试文件
 * 
 * 用于验证 types.ts 中的类型定义是否符合预期
 * 此文件不会被编译到生产环境，仅用于开发时类型检查
 */

import type {
  ListedBoard,
  StockResponse,
  StocksRequest,
  ApiResponse,
  MetaResponseData,
  KLineItem,
  KLineResponse,
  SignalItem,
  SignalResponse
} from './types'

// ============================================
// 测试 ListedBoard 枚举
// ============================================

const board1: ListedBoard = '主板'
const board2: ListedBoard = '创业板'
const board3: ListedBoard = '科创板'
const board4: ListedBoard = '北交所'

// 以下代码应该报错（类型不匹配）
// const invalidBoard: ListedBoard = '无效板块'

// ============================================
// 测试 StockResponse
// ============================================

const stock: StockResponse = {
  stock_code: '000001.SZ',
  stock_name: '平安银行',
  listed_board: '主板',
  industry: '银行',
  sub_industry: '股份制银行',
  trade_date: '2026-05-29',
  pre_close: 10.50,
  open: 10.50,
  close: 10.93,
  high: 11.00,
  low: 10.45,
  volume: 1000000,
  amount: 10930000.00,
  change: 0.43,
  change_pct: 4.09,
  turnover_rate: 2.5,
  pe: 5.2,
  pb: 0.8,
  market_cap: 20000000.00,
  circ_mv: 18000000.00,
  ma5: 10.80,
  ma10: 10.70,
  ma20: 10.60,
  v_ma5: 950000,
  rsi_6: 65.5,
  macd: 0.15,
  boll_upper: 11.20,
  boll_mid: 10.80,
  boll_lower: 10.40,
  is_st: false,
  is_new: false,
  limit_up: false,
  limit_down: false
}

// 测试可选字段
const minimalStock: StockResponse = {
  stock_code: '000001.SZ',
  stock_name: '平安银行',
  listed_board: '主板',
  trade_date: '2026-05-29',
  is_st: false,
  is_new: false,
  limit_up: false,
  limit_down: false
}

// ============================================
// 测试 StocksRequest
// ============================================

const request: StocksRequest = {
  filters: 'pattern_bull_candle,pattern_hammer',
  listed_board: '主板',
  industry: '银行,地产',
  area: '北京,上海',
  sort_by: 'change_pct',
  sort_asc: false,
  offset: 0,
  limit: 100,
  as_of_date: '2026-05-29'
}

// 测试最小化请求（仅必填字段）
const minimalRequest: StocksRequest = {
  sort_by: 'change_pct',
  sort_asc: false,
  offset: 0,
  limit: 100,
  as_of_date: '2026-05-29'
}

// ============================================
// 测试 ApiResponse
// ============================================

const successResponse: ApiResponse<StockResponse[]> = {
  code: 200,
  message: 'success',
  data: [stock]
}

const errorResponse: ApiResponse<null> = {
  code: 400,
  message: '参数错误: invalid sort_by',
  data: null
}

// ============================================
// 测试 MetaResponseData
// ============================================

const meta: MetaResponseData = {
  trade_date: '20260529',
  total: 5000,
  groups: [
    {
      id: 'pattern',
      label: 'K线形态',
      fields: [
        { key: 'pattern_bull_candle', label: '阳线', count: 100 }
      ]
    }
  ],
  industry_options: ['银行', '地产', '医药'],
  area_options: ['北京', '上海', '深圳']
}

// ============================================
// 测试 KLineItem 和 KLineResponse
// ============================================

const klineItem: KLineItem = {
  trade_date: '2026-05-29',
  open: 10.50,
  high: 11.00,
  low: 10.45,
  close: 10.93,
  volume: 1000000,
  amount: 10930000.00
}

const klineResponse: KLineResponse = {
  stock_code: '000001.SZ',
  data: [klineItem],
  count: 1
}

// ============================================
// 测试 SignalItem 和 SignalResponse
// ============================================

const signal: SignalItem = {
  trade_date: '2026-05-29',
  signal_type: 'buy',
  price: 10.93,
  reason: 'MACD金叉'
}

const signalResponse: SignalResponse = {
  stock_code: '000001.SZ',
  signals: [signal],
  count: 1
}

// ============================================
// 导出测试（确保没有未使用的变量警告）
// ============================================

export {
  board1,
  board2,
  board3,
  board4,
  stock,
  minimalStock,
  request,
  minimalRequest,
  successResponse,
  errorResponse,
  meta,
  klineItem,
  klineResponse,
  signal,
  signalResponse
}
