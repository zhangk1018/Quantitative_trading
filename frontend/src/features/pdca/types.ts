/** PDCA 交易自律系统 — 类型定义 */

// --- 枚举 ---
export type InstrumentType = 'stock' | 'futures' | 'forex' | 'option';
export type LongShort = 'long' | 'short';
export type OrderType = 'limit' | 'market' | 'stop';
export type TradeGrade = 'A' | 'B' | 'C';
export type ExitReason = 'take_profit' | 'stop_loss' | 'impulsive' | 'plan_expired' | 'others';
export type TriggerSource = 'system_plan' | 'news' | 'impulse' | 'scanner' | 'manual';
export type CycleStatus = 'PLAN' | 'DO' | 'CHECK' | 'ACT';
export type ViolationType = 'C_class_trade' | 'over_position' | 'no_plan_trade' | 'cancel_stop_loss';
export type Severity = 'low' | 'medium' | 'high' | 'critical';

// --- 交易记录 ---
export interface TradingRecord {
  id: number;
  account_id: number;
  pdca_cycle_id: number;
  trading_plan_id: number | null;
  code: string;
  security_name: string;
  instrument_type: InstrumentType;
  long_short: LongShort;
  order_type: OrderType;
  entry_date: string;
  exit_date: string | null;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  commission_entry: number;
  commission_exit: number;
  slip_point: number;
  channel_height: number | null;
  gross_profit: number | null;
  entry_score: number | null;
  exit_score: number | null;
  trade_score: number | null;
  trade_grade: TradeGrade | null;
  trigger_source: TriggerSource | null;
  actual_stop_loss: number | null;
  exit_reason: ExitReason | null;
  settlement_currency: string;
  created_at: string;
  updated_at: string;
}

export interface TradingRecordFormData {
  code: string;
  security_name: string;
  instrument_type: InstrumentType;
  long_short: LongShort;
  order_type: OrderType;
  entry_date: string;
  exit_date?: string;
  entry_price: number;
  exit_price?: number;
  quantity: number;
  commission_entry: number;
  commission_exit: number;
  slip_point: number;
  channel_height?: number;
  gross_profit?: number;
  entry_score?: number;
  exit_score?: number;
  trade_score?: number;
  trade_grade?: TradeGrade;
  trigger_source?: TriggerSource;
  actual_stop_loss?: number;
  exit_reason?: ExitReason;
  pdca_cycle_id?: number;
}

// --- 交易日记 ---
export interface TradingDiary {
  id: number;
  account_id: number;
  trading_record_id: number | null;
  pdca_cycle_id: number;
  emotion_note: string | null;
  review_text: string;
  attach_file_paths: string[];
  three_month_review_done: boolean;
  created_at: string;
  updated_at: string;
}

export interface TradingDiaryFormData {
  trading_record_id?: number;
  pdca_cycle_id?: number;
  emotion_note?: string;
  review_text: string;
}

// --- 资金快照 ---
export interface AccountSnapshot {
  id: number;
  account_id: number;
  snapshot_date: string;
  total_asset: number;
  available_cash: number;
  position_value: number;
  deposit: number;
  withdrawal: number;
  net_deposit: number;
  realized_pnl: number;
  adjusted_nav: number | null;
  created_at: string;
}

export interface AccountSnapshotFormData {
  snapshot_date: string;
  total_asset: number;
  available_cash: number;
  position_value: number;
  deposit: number;
  withdrawal: number;
  realized_pnl: number;
}

// --- 资金曲线 ---
export interface CapitalCurvePoint {
  date: string;
  total_asset: number;
  adjusted_nav: number | null;
  deposit: number;
  withdrawal: number;
  realized_pnl: number;
}

// --- 系统配置 ---
export interface SystemConfigItem {
  id: number;
  config_key: string;
  config_value: string;
  numeric_value: number | null;
  bool_value: boolean | null;
  description: string | null;
  version: string;
  modified_at: string;
  modified_by: string | null;
  modify_reason: string;
}

// --- 股票搜索 ---
export interface StockSearchResult {
  code: string;
  name: string;
  listed_board: string | null;
}

// --- PDCA 周期 ---
export interface PDCACycle {
  id: number;
  account_id: number;
  prev_cycle_id: number | null;
  cycle_type: 'week' | 'month';
  cycle_name: string;
  status: CycleStatus;
  start_date: string;
  end_date: string;
  goal_text: string | null;
  created_at: string;
  updated_at: string;
}

// --- 券商适配器 ---
export interface BrokerAdapter {
  id: number;
  broker_name: string;
  display_name: string;
  is_active: boolean;
  column_mapping: Record<string, string>;
  date_format: string;
  skip_rows: number;
}

// --- 导入解析结果 ---
export interface ImportParseResult {
  broker_name: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  records: TradingRecordFormData[];
  errors: { row: number; message: string }[];
}

// --- API 响应 ---
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// --- 枚举标签映射 ---
export const INSTRUMENT_TYPE_LABELS: Record<InstrumentType, string> = {
  stock: '股票',
  futures: '期货',
  forex: '外汇',
  option: '期权',
};

export const LONG_SHORT_LABELS: Record<LongShort, string> = {
  long: '做多',
  short: '做空',
};

export const ORDER_TYPE_LABELS: Record<OrderType, string> = {
  limit: '限价',
  market: '市价',
  stop: '止损',
};

export const TRADE_GRADE_LABELS: Record<TradeGrade, string> = {
  A: 'A级',
  B: 'B级',
  C: 'C级',
};

export const EXIT_REASON_LABELS: Record<ExitReason, string> = {
  take_profit: '止盈出场',
  stop_loss: '止损出场',
  impulsive: '冲动出场',
  plan_expired: '计划到期',
  others: '其他',
};

export const TRIGGER_SOURCE_LABELS: Record<TriggerSource, string> = {
  system_plan: '系统计划',
  news: '新闻驱动',
  impulse: '盘中冲动',
  scanner: '选股器',
  manual: '手动',
};

// --- 预计算 Select options 数组，避免组件内重复 Object.entries 转换 ---
export const INSTRUMENT_TYPE_OPTIONS = Object.entries(INSTRUMENT_TYPE_LABELS).map(([value, label]) => ({ value, label }));
export const LONG_SHORT_OPTIONS = Object.entries(LONG_SHORT_LABELS).map(([value, label]) => ({ value, label }));
export const ORDER_TYPE_OPTIONS = Object.entries(ORDER_TYPE_LABELS).map(([value, label]) => ({ value, label }));
export const TRADE_GRADE_OPTIONS = Object.entries(TRADE_GRADE_LABELS).map(([value, label]) => ({ value, label }));
export const EXIT_REASON_OPTIONS = Object.entries(EXIT_REASON_LABELS).map(([value, label]) => ({ value, label }));
export const TRIGGER_SOURCE_OPTIONS = Object.entries(TRIGGER_SOURCE_LABELS).map(([value, label]) => ({ value, label }));