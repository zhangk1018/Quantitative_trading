// src/features/backtest/strategyBacktestTypes.ts
// V4 终稿类型定义 | 对应方案：策略回测方案设计-v4.md

/**
 * ============================================
 * 1. 枚举 & 联合类型 (UI / 引擎共用)
 * ============================================
 */

/** 卖出原因（7种分类，用于交易日志彩色Tag） */
export type SellReason =
  | 'rebalance'      // 调仓换股
  | 'stop_loss'      // 止损
  | 'take_profit'    // 止盈
  | 'timeout'        // 超时平仓
  | 'portfolio_risk' // 组合级风控（单日亏损/最大回撤）
  | 'delisted'       // 退市强平
  | 'end';           // 期末清仓

/** 调仓频率（底层交易日间隔） */
export type RebalanceInterval = 1 | 5 | 21; // 1=每日, 5=每周, 21=每月

/** 仓位分配方式 */
export type PositionAlloc = 'equal' | 'marketCap';

/** 剩余现金处理方式 */
export type IdleCashReturn = 'none' | 'moneyMarket';

/** 顺延超时失败处理 */
export type DeferFailAction = 'abandon' | 'atClose';

/** 技术形态类型（引擎支持的4种基础形态） */
export type TechPattern = 'ma_bullish' | 'macd_golden_cross' | 'rsi_golden_cross' | 'boll_break_upper';

/** K线形态类型（后端 pattern_markers 提供） */
export type KlinePattern = 'morning_star' | 'hammer' | 'bullish_engulfing' | 'piercing_line' | 'three_white_soldiers';

/** 行情指标范围字段（选股器常用） */
export type RangeField =
  | 'market_cap'     // 市值（亿元）
  | 'close'          // 收盘价
  | 'change_pct'     // 涨跌幅
  | 'pe'             // 市盈率（静态）
  | 'pe_ttm'         // 市盈率（TTM）
  | 'pb'             // 市净率
  | 'turnover_rate'  // 换手率
  | 'vol_ratio_5';   // 量比（5日）

/**
 * ============================================
 * 2. 系统设置 Storage 接口 (策略回测默认值)
 * ============================================
 */

export interface StrategyBacktestDefaults {
  // ---------- Card 1: 基础参数 ----------
  /** 初始资金（单位：分），如 100万 = 100_000_000 分 */
  initialCapital: number;
  /** 基准指数代码，如 '000300.SH' */
  benchmarkCode: string;
  /** 是否使用全收益指数（如 H00300.CSI），需后端支持 */
  benchmarkTotalReturn: boolean;
  /** 无风险利率（年化），如 0.03 = 3% */
  riskFreeRate: number;
  /** 预热天数（指标冷启动），默认 60 天（受后端数据量限制） */
  warmupDays: number;

  // ---------- Card 2: 调仓与仓位 ----------
  /** 调仓频率（交易日间隔），1/5/21 */
  rebalanceInterval: RebalanceInterval;
  /** 最大持仓数量（3~50只） */
  maxPositions: number;
  /** 仓位分配方式 */
  positionAlloc: PositionAlloc;
  /** 单股最大仓位比例，1.0 = 100%（即不限制），0.15 = 15% */
  singleStockMaxPct: number;
  /** 剩余现金处理方式 */
  idleCashReturn: IdleCashReturn;
  /** 货币基金年化收益率（如 0.02），仅当 idleCashReturn='moneyMarket' 时生效 */
  idleCashRate: number;

  // ---------- Card 3: 交易成本 ----------
  /** 手续费率（双边），如 0.00025 = 万2.5 */
  feeRate: number;
  /** 滑点（成交价偏移），如 0.0001 = 万1 */
  slippage: number;
  /** 印花税（仅卖出），如 0.001 = 千1 */
  stampDuty: number;
  /** 单笔最低佣金（单位：分），如 500 = 5元 */
  minCommission: number;

  // ---------- Card 4: 风险控制（个股风控） ----------
  /** 止损比例，如 -0.08 = -8% */
  stopLossPct: number;
  /** 止盈比例，如 0.25 = 25% */
  takeProfitPct: number;
  /** 最大持仓天数，超时强制平仓 */
  maxHoldDays: number;
  /** 最大顺延天数（涨跌停/停牌最多等待天数） */
  maxDeferDays: number;
  /** 顺延超时处理方式 */
  deferFailAction: DeferFailAction;

  // ---------- Card 4: 组合级风控（默认关闭） ----------
  /** 是否启用单日最大亏损风控（默认 false） */
  dailyLossLimitEnabled: boolean;
  /** 单日最大亏损阈值（如 -0.05 = -5%），仅 enabled=true 时生效 */
  dailyLossLimitPct: number;
  /** 是否启用最大回撤止损（默认 false） */
  maxDrawdownStopEnabled: boolean;
  /** 最大回撤阈值（如 -0.15 = -15%），仅 enabled=true 时生效 */
  maxDrawdownStopPct: number;
}

/**
 * ============================================
 * 3. AST 条件过滤器（选股器 → 回测引擎）
 * ============================================
 */

export type FilterNode =
  | { type: 'and'; children: FilterNode[] }
  | { type: 'or'; children: FilterNode[] }
  | { type: 'not'; child: FilterNode }
  | { type: 'range'; field: RangeField; min?: number; max?: number }
  | { type: 'pattern'; pattern: TechPattern }
  | { type: 'kline'; pattern: KlinePattern; lookbackDays: number }
  | { type: 'market'; boards?: string[]; watchlistOnly?: boolean }
  | { type: 'custom_indicator'; scriptId: string; version: number; min?: number; max?: number };

/**
 * ============================================
 * 4. 数据实体（引擎输入 / 中间状态）
 * ============================================
 */

/** OHLCV 单条数据（后端返回为 number[] 数组，此接口用于引擎内部可读性） */
export interface OhlcvBar {
  ts: number;        // 时间戳（或 YYYYMMDD 数字）
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  preClose?: number; // 昨收价（前复权口径），由后端提供或引擎用上一根 close 兜底
}

/** 股票快照（含最新日基本面/状态，用于回测时近似） */
export interface StockSnapshot {
  code: string;
  name: string;
  listedBoard: string;   // 'main', 'gem', 'star', 'beijing' 等
  isSt: boolean;          // 是否 ST（用于 5% 涨跌停）
  marketCap: number;      // 市值（亿元）
  pe: number;            // 市盈率（静态）
  peTtm: number;         // 市盈率（TTM）
  pb: number;            // 市净率
  turnoverRate: number;  // 换手率
  // ... 其他基本面字段按需扩展
}

/** 持仓状态（引擎内部维护） */
export interface Position {
  code: string;
  shares: number;        // 持股数量（股）
  avgCost: number;       // 持仓成本（元/股，复权口径）
  entryDateIdx: number;  // 建仓日在 tradeDates 中的索引
  holdDays: number;      // 已持有交易日数
}

/** 交易记录（引擎输出） */
export interface Trade {
  code: string;
  name: string;
  entryDate: string;      // YYYY-MM-DD
  exitDate: string;       // YYYY-MM-DD
  entryPrice: number;
  exitPrice: number;
  shares: number;
  pnl: number;            // 盈亏金额（元）
  pnlPct: number;         // 盈亏比例
  holdDays: number;
  sellReason: SellReason; // 卖出原因（7分类）
}

/** 每日净值点（引擎输出） */
export interface EquityPoint {
  date: string;           // YYYY-MM-DD
  totalEquity: number;    // 总资产（元）
  cash: number;           // 现金（元）
  marketValue: number;    // 持仓市值（元）
  returnPct: number;      // 当日收益率（已扣费）
  drawdownPct: number;    // 回撤比例（相对于历史峰值）
  benchmark?: number;     // 基准指数当日点位（如有）
}

/**
 * ============================================
 * 5. 回测结果（引擎输出）
 * ============================================
 */

export interface StrategyBacktestResult {
  /** 回测配置快照（便于结果溯源） */
  config: StrategyBacktestDefaults;
  /** 策略净值曲线（每日） */
  equityCurve: EquityPoint[];
  /** 交易记录列表 */
  trades: Trade[];
  /** 每日持仓明细（用于持仓明细表展示） */
  holdings: Array<{ date: string; positions: Position[] }>;
  /** 绩效指标汇总 */
  metrics: StrategyMetrics;
  /** 引擎运行时警告（如现金拖累、截断、ST标识近似等） */
  warnings: string[];
  /** 各阶段耗时（毫秒），用于性能分析 */
  timings: {
    dataLoad: number;
    indicatorCalc: number;
    simulation: number;
    total: number;
  };
}

/**
 * ============================================
 * 6. 绩效指标（含V1已有 + V2新增）
 * ============================================
 */

export interface StrategyMetrics {
  // ----- 基础指标（无基准依赖） -----
  totalReturn: number;          // 总收益率
  annualReturn: number;         // 年化收益率
  sharpeRatio: number;          // 夏普比率
  maxDrawdown: number;          // 最大回撤
  winRate: number;              // 胜率 (0~1)
  profitLossRatio: number;      // 盈亏比
  maxConsecutiveLosses: number; // 最大连亏次数
  avgHoldDays: number;          // 平均持仓天数
  totalTrades: number;          // 总交易次数
  monthlyWinRate: number;       // 月度胜率 (0~1)
  calmarRatio: number;          // 卡玛比率

  // ----- 扩展指标（依赖基准数据，不可用时为 null） -----
  benchmarkReturn: number | null;   // 基准收益率
  alpha: number | null;             // 超额收益 (Alpha)
  beta: number | null;              // 贝塔
  informationRatio: number | null;  // 信息比率 (IR)
}

/**
 * ============================================
 * 7. 技术指标缓存（引擎核心数据结构）
 * ============================================
 */

/**
 * IndicatorCache 类用于存储单只股票全周期的技术指标。
 * 使用 Float64Array 保证内存效率和访问速度。
 * 配合 readyFlags 避免有效值（0/负数）被误判为未就绪。
 */
export class IndicatorCache {
  readonly length: number;

  // MA 系列
  ma5: Float64Array;
  ma10: Float64Array;
  ma20: Float64Array;
  ma60: Float64Array;

  // MACD 系列
  macdDif: Float64Array;
  macdDea: Float64Array;
  macdHist: Float64Array;

  // RSI 系列
  rsi6: Float64Array;
  rsi12: Float64Array;
  rsi24: Float64Array;

  // BOLL 系列
  bollUpper: Float64Array;
  bollMid: Float64Array;
  bollLower: Float64Array;

  // 量比（5日）
  volRatio5: Float64Array;

  // 就绪标记（1=有效，0=预热期/无效）
  private readyFlags: Map<string, Uint8Array>;

  constructor(length: number) {
    this.length = length;
    this.ma5 = new Float64Array(length);
    this.ma10 = new Float64Array(length);
    this.ma20 = new Float64Array(length);
    this.ma60 = new Float64Array(length);
    this.macdDif = new Float64Array(length);
    this.macdDea = new Float64Array(length);
    this.macdHist = new Float64Array(length);
    this.rsi6 = new Float64Array(length);
    this.rsi12 = new Float64Array(length);
    this.rsi24 = new Float64Array(length);
    this.bollUpper = new Float64Array(length);
    this.bollMid = new Float64Array(length);
    this.bollLower = new Float64Array(length);
    this.volRatio5 = new Float64Array(length);

    this.readyFlags = new Map();
    // 为每个指标初始化 Uint8Array
    const keys = [
      'ma5', 'ma10', 'ma20', 'ma60',
      'macdDif', 'macdDea', 'macdHist',
      'rsi6', 'rsi12', 'rsi24',
      'bollUpper', 'bollMid', 'bollLower',
      'volRatio5'
    ];
    for (const key of keys) {
      this.readyFlags.set(key, new Uint8Array(length));
    }
  }

  /** 标记某指标在指定索引位置为就绪 */
  setReady(key: string, idx: number): void {
    const flag = this.readyFlags.get(key);
    if (flag) flag[idx] = 1;
  }

  /** 检查某指标在指定索引位置是否就绪 */
  isReady(key: string, idx: number): boolean {
    const flag = this.readyFlags.get(key);
    return flag ? flag[idx] === 1 : false;
  }

  /** 获取 MA 值，未就绪返回 null */
  getMA(period: 5 | 10 | 20 | 60, idx: number): number | null {
    const key = `ma${period}`;
    if (!this.isReady(key, idx)) return null;
    switch (period) {
      case 5: return this.ma5[idx];
      case 10: return this.ma10[idx];
      case 20: return this.ma20[idx];
      case 60: return this.ma60[idx];
    }
  }

  /** 获取 MACD 值，未就绪返回 null */
  getMACD(component: 'dif' | 'dea' | 'hist', idx: number): number | null {
    const key = `macd${component.charAt(0).toUpperCase() + component.slice(1)}`; // macdDif, macdDea, macdHist
    if (!this.isReady(key, idx)) return null;
    switch (component) {
      case 'dif': return this.macdDif[idx];
      case 'dea': return this.macdDea[idx];
      case 'hist': return this.macdHist[idx];
    }
  }

  /** 获取 RSI 值，未就绪返回 null */
  getRSI(period: 6 | 12 | 24, idx: number): number | null {
    const key = `rsi${period}`;
    if (!this.isReady(key, idx)) return null;
    switch (period) {
      case 6: return this.rsi6[idx];
      case 12: return this.rsi12[idx];
      case 24: return this.rsi24[idx];
    }
  }

  /** 获取 BOLL 值，未就绪返回 null */
  getBOLL(band: 'upper' | 'mid' | 'lower', idx: number): number | null {
    const key = `boll${band.charAt(0).toUpperCase() + band.slice(1)}`; // bollUpper, bollMid, bollLower
    if (!this.isReady(key, idx)) return null;
    switch (band) {
      case 'upper': return this.bollUpper[idx];
      case 'mid': return this.bollMid[idx];
      case 'lower': return this.bollLower[idx];
    }
  }

  /** 获取量比值，未就绪返回 null */
  getVolRatio5(idx: number): number | null {
    if (!this.isReady('volRatio5', idx)) return null;
    return this.volRatio5[idx];
  }
}
