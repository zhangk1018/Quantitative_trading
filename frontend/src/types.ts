/**
 * types.ts - TypeScript 类型定义（严格镜像 schemas.py）
 * 
 * 本文件由 schemas.py 自动生成，禁止手动修改字段定义。
 * 任何字段变更必须先修改 schemas.py，然后重新生成此文件。
 * 
 * 生成时间: 2026-05-31
 * 来源: src/api/models/schemas.py
 */

// ============================================
// 枚举定义
// ============================================

/** 上市板块枚举 */
export type ListedBoard = '主板' | '创业板' | '科创板' | '北交所'

// ============================================
// 筛选相关类型（用于 FilterPanel）
// ============================================

/** 筛选项字段 */
export interface FilterField {
  key: string                     // 筛选条件键名
  label: string                   // 显示标签
  count: number                   // 命中数量
}

/** 筛选条件分组 */
export interface FilterGroup {
  id: string                      // 分组ID
  label: string                   // 分组标签
  fields: FilterField[]           // 筛选项列表
}

// ============================================
// 响应模型
// ============================================

/**
 * 股票列表响应模型
 * 
 * 对应后端: StockResponse (schemas.py:48-251)
 */
export interface StockResponse {
  // --- 基础字段 ---
  stock_code: string                    // 股票代码
  stock_name: string                    // 股票名称
  listed_board: ListedBoard             // 上市板块
  industry?: string | null              // 行业分类
  sub_industry?: string | null          // 细分行业
  
  // --- 行情字段 ---
  trade_date: string                    // 交易日期 (YYYY-MM-DD)
  pre_close?: number | null             // 前收盘价
  open?: number | null                  // 开盘价
  close?: number | null                 // 收盘价
  high?: number | null                  // 最高价
  low?: number | null                   // 最低价
  volume?: number | null                // 成交量（手）
  amount?: number | null                // 成交额（元）
  change?: number | null                // 涨跌额（元）
  change_pct?: number | null           // 涨跌幅（%）
  turnover_rate?: number | null         // 换手率（%）
  volume_ratio?: number | null          // 量比
  
  // --- 财务与估值字段 ---
  pe?: number | null                    // 市盈率
  pb?: number | null                    // 市净率
  pe_ttm?: number | null                // 市盈率TTM
  ps?: number | null                    // 市销率
  ps_ttm?: number | null                // 市销率TTM
  dv_ratio?: number | null              // 股息率
  dv_ttm?: number | null                // 股息率TTM
  market_cap?: number | null            // 总市值（万元）
  circ_mv?: number | null               // 流通市值（万元）
  float_share?: number | null           // 流通股（万股）
  
  // --- 技术指标字段 ---
  ma5?: number | null                   // 5日均线价
  ma10?: number | null                  // 10日均线价
  ma20?: number | null                  // 20日均线价
  v_ma5?: number | null                 // 5日均量（手）
  rsi_6?: number | null                 // RSI6（相对强弱指标）
  macd?: number | null                  // MACD值
  boll_upper?: number | null            // 布林带上轨
  boll_mid?: number | null              // 布林带中轨
  boll_lower?: number | null            // 布林带下轨
  vol_ratio_5?: number | null           // 5日量比
  
  // --- 资金流向字段 ---
  net_mf_amount?: number | null         // 净流入（万元）
  buy_sm_amount?: number | null         // 小单买入（万元）
  sell_sm_amount?: number | null        // 小单卖出（万元）
  buy_md_amount?: number | null         // 中单买入（万元）
  sell_md_amount?: number | null       // 中单卖出（万元）
  buy_lg_amount?: number | null         // 大单买入（万元）
  sell_lg_amount?: number | null       // 大单卖出（万元）
  buy_elg_amount?: number | null       // 特大单买入（万元）
  sell_elg_amount?: number | null      // 特大单卖出（万元）
  
  // --- 新高/连涨标记 ---
  break_high_20?: boolean | null        // 20日新高
  break_high_60?: boolean | null        // 60日新高
  
  // --- 状态标记字段（保留但不在前端展示）---
  is_st?: boolean | null                // 是否ST股票
  is_new?: boolean | null               // 是否新股（上市<1年）
  limit_up?: boolean | null             // 是否涨停
  limit_down?: boolean | null           // 是否跌停
}

// ============================================
// 请求模型
// ============================================

/**
 * 股票列表查询请求模型
 * 
 * 对应后端: StocksRequest (schemas.py:258-337)
 * 
 * 硬约束:
 * 1. limit 最大值为 200（防止内存溢出）
 * 2. as_of_date 必须显式传递（防前视偏差）
 * 3. sort_by 需要在 Service 层进行白名单校验
 */
export interface StocksRequest {
  filters?: string | null               // K线形态筛选条件（逗号分隔）
  listed_board?: ListedBoard | null     // 上市板块筛选
  industry?: string | null              // 行业筛选（逗号分隔，OR逻辑）
  area?: string | null                  // 地区筛选（逗号分隔，OR逻辑）
  sort_by: string                       // 排序字段（默认: change_pct）
  sort_asc: boolean                     // 是否升序排列（默认: false）
  offset: number                        // 分页偏移量（默认: 0, >=0）
  limit: number                         // 每页数量（默认: 100, 1-200）
  as_of_date: string                    // 数据截止日期（防前视偏差，必填，格式: YYYY-MM-DD）
}

// ============================================
// 统一响应信封
// ============================================

/**
 * 统一 API 响应信封
 * 
 * 对应后端: ApiResponse (schemas.py:344-376)
 * 
 * 所有 API 接口必须返回此格式，禁止裸返回 DataFrame/Dict
 */
export interface ApiResponse<T = any> {
  code: number                          // HTTP 状态码映射（200/400/404/408/500）
  message: string                       // 响应消息或错误描述
  data: T | null                        // 响应数据（可为对象、数组或 null）
}

// ============================================
// 元数据响应模型（/api/meta）
// ============================================

/**
 * 元数据响应模型
 * 
 * 对应后端: MetaResponse (schemas.py:383-394)
 * 
 * 用于前端初始化筛选面板的行业/地区选项
 */
export interface MetaResponseData {
  trade_date: string                    // 最新交易日期（YYYYMMDD）
  total: number                         // 股票总数
  groups: Array<Record<string, any>>    // 筛选条件分组
  industry_options: string[]            // 行业选项列表
  area_options: string[]                // 地区选项列表
}

// ============================================
// K线数据响应模型（/api/kline/{code}）
// ============================================

/**
 * 单根K线数据
 * 
 * 对应后端: KLineItem (schemas.py:401-413)
 */
export interface KLineItem {
  trade_date: string                    // 交易日期 (YYYY-MM-DD)
  open: number                          // 开盘价
  high: number                          // 最高价
  low: number                           // 最低价
  close: number                         // 收盘价
  volume: number                        // 成交量
  amount: number                        // 成交额
}

/**
 * K线响应模型
 * 
 * 对应后端: KLineResponse (schemas.py:416-421)
 */
export interface KLineResponse {
  stock_code: string                    // 股票代码
  data: KLineItem[]                     // K线数据列表
  count: number                         // 数据条数
}

// ============================================
// 买卖信号响应模型（/api/signals/{code}）
// ============================================

/**
 * 单个买卖信号
 * 
 * 对应后端: SignalItem (schemas.py:428-437)
 */
export interface SignalItem {
  trade_date: string                    // 信号日期 (YYYY-MM-DD)
  signal_type: string                   // 信号类型（buy/sell）
  price: number                         // 信号价格
  reason: string                        // 信号原因（如 MACD金叉）
}

/**
 * 买卖信号响应模型
 * 
 * 对应后端: SignalResponse (schemas.py:440-445)
 */
export interface SignalResponse {
  stock_code: string                    // 股票代码
  signals: SignalItem[]                 // 信号列表
  count: number                         // 信号数量
}