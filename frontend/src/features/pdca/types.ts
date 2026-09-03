/** PDCA 交易自律系统 — 类型定义 */

// --- 枚举 ---
export type InstrumentType = 'stock' | 'futures' | 'forex' | 'option';
export type LongShort = 'long' | 'short';
export type OrderType = 'limit' | 'market' | 'stop';
export type TradeGrade = 'A' | 'B' | 'C';
export type ExitReason = 'take_profit' | 'stop_loss' | 'impulsive' | 'plan_expired' | 'others';
export type TriggerSource = 'system_plan' | 'news' | 'impulse' | 'scanner' | 'manual';
export type CycleStatus = 'PLAN' | 'DO' | 'CHECK' | 'ACT' | 'DONE';
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
  remain_qty: number | null;   // 新增：剩余持仓量
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
  exit_slips?: ExitSlip[];     // 新增：卖出子单列表（展开时加载）
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
  stamp_duty?: number;
  transfer_fee?: number;
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

// --- 卖出子单（一买多卖） ---
export interface ExitSlip {
  id: number;
  record_id: number;
  exit_date: string;
  exit_price: number;
  quantity: number;
  commission: number;
  stamp_duty: number;
  transfer_fee: number;
  exit_reason: ExitReason | null;
  exit_score: number | null;
  actual_stop_loss: number | null;
  slip_point: number;
  created_at: string;
  updated_at: string;
}

export interface ExitSlipFormData {
  exit_date: string;
  exit_price: number;
  quantity: number;
  commission?: number;
  stamp_duty?: number;
  transfer_fee?: number;
  exit_reason?: ExitReason;
  exit_score?: number;
  actual_stop_loss?: number;
  slip_point?: number;
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
/** 自动计算净值曲线点（基于股票买卖 + 未平仓浮盈） */
export interface EquityCurveAutoPoint {
  date: string;
  equity: number;
  realized: number;
  unrealized: number;
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
export type CycleType = 'day' | 'week' | 'month' | 'quarter' | 'year';

export const CYCLE_TYPE_LABELS: Record<CycleType, string> = {
  day: '日周期',
  week: '周周期',
  month: '月周期',
  quarter: '季周期',
  year: '年周期',
};

export const CYCLE_TYPE_OPTIONS = Object.entries(CYCLE_TYPE_LABELS).map(([value, label]) => ({ value, label }));

export interface PDCACycle {
  id: number;
  account_id: number;
  prev_cycle_id: number | null;
  cycle_type: CycleType;
  cycle_name: string;
  status: CycleStatus;
  start_date: string;
  end_date: string;
  goal_text: string | null;
  created_at: string;
  updated_at: string;
}

// --- 交易计划 ---
export type PlanStatus = 'draft' | 'active' | 'executed' | 'cancelled';
/** 计划派生状态（后端 derived_status，需求④）：按关联交易记录自动派生 */
export type DerivedPlanStatus = 'pending' | 'holding' | 'closed' | 'cancelled' | 'draft';
export type PlanTemplateType = 'short_term' | 'mid_term' | 'long_term';

export interface PlanTemplate {
  id: number;
  template_name: string;
  template_type: PlanTemplateType;
  required_fields: string[];
  default_values: Record<string, unknown> | null;
  is_system: boolean;
}

export interface TradingPlan {
  id: number;
  account_id: number;
  pdca_cycle_id: number;
  template_id: number | null;
  code: string;
  security_name: string | null;
  instrument_type: InstrumentType;
  long_short: LongShort;
  plan_status: PlanStatus;
  /** 派生状态（后端按关联交易记录计算：pending/holding/closed/cancelled/draft） */
  derived_status?: DerivedPlanStatus;
  weekly_view: string;
  daily_view: string;
  entry_price: number;
  stop_loss_price: number;
  target_price: number | null;
  max_risk_rate: number;
  plan_quantity: number;
  abort_condition: string | null;
  is_valid: boolean;
  cycle_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TradingPlanFormData {
  pdca_cycle_id: number;
  template_id?: number | null;
  code: string;
  security_name?: string | null;
  long_short: LongShort;
  weekly_view: string;
  daily_view: string;
  entry_price: number;
  stop_loss_price: number;
  target_price?: number | null;
  max_risk_rate: number;
  plan_quantity: number;
  abort_condition?: string | null;
}

export const PLAN_TEMPLATE_TYPE_LABELS: Record<PlanTemplateType, string> = {
  short_term: '短线模板',
  mid_term: '中线模板',
  long_term: '长线模板',
};

export const PLAN_TEMPLATE_TYPE_OPTIONS = Object.entries(PLAN_TEMPLATE_TYPE_LABELS).map(([value, label]) => ({ value, label }));

// --- 执行跟踪（Do 模块增强） ---
export interface ExecutionPlanDetail {
  plan_id: number;
  code: string;
  security_name: string | null;
  long_short: string;
  plan_entry_price: number;
  plan_stop_loss: number;
  plan_quantity: number;
  plan_status: string;
  execution_status: 'executed' | 'pending';
  actual_entry_price: number | null;
  actual_quantity: number;
  fill_rate: number;
  matched_records: number;
  first_entry_date: string | null;
  price_deviation: number | null;
}

export interface NakedTradeDetail {
  record_id: number;
  code: string;
  security_name: string | null;
  entry_date: string;
  entry_price: number;
  quantity: number;
  trigger_source: string | null;
}

export interface ExecutionSummary {
  cycle_id: number;
  cycle_name: string;
  cycle_status: string;
  total_plans: number;
  executed_plans: number;
  pending_plans: number;
  total_trades: number;
  naked_trades: number;
  fill_rate: number;
  details: ExecutionPlanDetail[];
  naked_trade_details: NakedTradeDetail[];
}

// --- 标的 ABC 分类 ---
export type SecurityTagValue = 'A' | 'B' | 'C';

export interface SecurityTag {
  id: number;
  account_id: number;
  code: string;
  security_name: string | null;
  tag: SecurityTagValue;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export const SECURITY_TAG_LABELS: Record<SecurityTagValue, string> = {
  A: 'A类（熟悉且验证）',
  B: 'B类（一般熟悉）',
  C: 'C类（不熟悉或验证失败）',
};

export const SECURITY_TAG_OPTIONS = (
  Object.entries(SECURITY_TAG_LABELS) as [SecurityTagValue, string][]
).map(([value, label]) => ({ value, label }));

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

/** 非分页列表响应（后端统一返回 {items: T[]}） */
export interface ListData<T> {
  items: T[];
}

// ============================================================
// Check 模块 — 复盘报告
// ============================================================

export type ReportStatus = 'draft' | 'published';

export interface CheckReport {
  id: number;
  account_id: number;
  pdca_cycle_id: number;
  report_status: ReportStatus;
  total_trade_count: number | null;
  complete_by_plan_count: number | null;
  execution_rate: number | null;
  win_rate: number | null;
  profit_loss_ratio: number | null;
  avg_entry_score: number | null;
  avg_exit_score: number | null;
  avg_trade_score: number | null;
  max_drawdown: number | null;
  violation_total: number | null;
  report_content: string | null;
  created_at: string;
  updated_at: string;
}

export interface CheckReportFormData {
  pdca_cycle_id: number;
  report_status?: string | null;
  total_trade_count?: number | null;
  complete_by_plan_count?: number | null;
  execution_rate?: number | null;
  win_rate?: number | null;
  profit_loss_ratio?: number | null;
  avg_entry_score?: number | null;
  avg_exit_score?: number | null;
  avg_trade_score?: number | null;
  max_drawdown?: number | null;
  violation_total?: number | null;
  report_content?: string | null;
}

// ============================================================
// Act 模块 — 迭代处理记录
// ============================================================

export interface ActRecord {
  id: number;
  account_id: number;
  pdca_cycle_id: number;
  problem_list: string[] | null;
  rectify_plan: string;
  bind_next_cycle_goal: string | null;
  is_freeze_experience: boolean;
  new_config_version: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActRecordFormData {
  pdca_cycle_id: number;
  problem_list?: string[];
  rectify_plan: string;
  bind_next_cycle_goal?: string | null;
  is_freeze_experience?: boolean;
  new_config_version?: string | null;
}

// ============================================================
// 经验知识库 — 冻结经验条目
// ============================================================

export interface TradeExperience {
  id: number;
  account_id: number;
  trading_record_id: number | null;
  title: string;
  content: string;
  tags: string[] | null;
  source_act_record_id: number | null;
  created_at: string;
  updated_at: string;
}

/** 经验知识库查询参数（对应 GET /pdca/experiences） */
export interface ExperienceQueryParams {
  /** 标签筛选（全部命中） */
  tags?: string[];
  /** 标题/内容关键词模糊搜索 */
  keyword?: string;
  page?: number;
  page_size?: number;
}

// ============================================================
// Behavior Log — 行为 & 违规日志
// ============================================================

export type LogType = 'normal' | 'violation';

export interface BehaviorLog {
  id: number;
  account_id: number;
  pdca_cycle_id: number;
  trading_record_id: number | null;
  log_type: LogType;
  violation_type: ViolationType | null;
  severity: string;
  log_content: string;
  happened_at: string;
  created_at: string;
}

export interface BehaviorLogFormData {
  pdca_cycle_id: number;
  trading_record_id?: number | null;
  log_type: LogType;
  violation_type?: ViolationType | null;
  severity?: string;
  log_content: string;
  happened_at?: string;
}

// --- 常量（标签映射、下拉选项）已迁移至 constants.ts ---
// 向后兼容导入：import { INSTRUMENT_TYPE_OPTIONS } from '../constants';