/**
 * StockDetailView.tsx - 股票详情页（Modal 承载）
 *
 * Phase 4.3 股票详情页：
 * - 4.3.2 骨架 + 入口（URL 同步 ?code=xxx）
 * - 4.3.3 头部 + 基本信息卡 + 行情卡
 * - 4.3.4 K线图集成（klinecharts 9.8 + 周期/复权切换）
 * - 4.3.5 买卖信号叠加（tradeMarker 自定义覆盖物）
 * - 4.3.6 副图指标切换（VOL/MACD/RSI/KDJ）
 * - 4.3.7 异常态（loading / error / 404 / empty + ErrorBoundary 兜底）
 *
 * 设计要点：
 * - 关闭：ESC 键、点击遮罩、关闭按钮（三种方式）
 * - URL 同步：?code=000001，浏览器前进/后退可切换
 * - 数据：USE_MOCK=true 时走 mock，false 时调真实 /api/stocks/{code}/
 * - 容错：SectionBoundary 包装 K线/信号/指标子组件，异常不冒泡到 Modal
 */

import { useEffect, useState, useCallback, useMemo, useRef, Component, type ReactNode, type ErrorInfo } from 'react';
import { fetchStockByCode, fetchKline, fetchSignals, fetchWatchlist, addWatchlist } from '../api';
import type { StockResponse, KLineItem, SignalItem } from '../types';
import { USE_MOCK } from '../config';
import KlineChart from './KlineChart';

// ============================================
// 类型定义
// ============================================

interface StockDetailViewProps {
  /** 股票代码（纯数字 6 位） */
  stockCode: string | null;
  /** 关闭回调 */
  onClose: () => void;
}

// 复权方式
type AdjType = 'none' | 'forward' | 'backward';
// K线周期
type PeriodType = 'daily' | 'weekly' | 'monthly';
// 副图指标
type SubIndicator = 'VOL' | 'MACD' | 'RSI' | 'KDJ';

// ============================================
// 工具函数
// ============================================

/** 数字格式化：保留 2 位小数，null/undefined → '-'
 * 防御性编程：兼容后端 Decimal 序列化为字符串的场景（如 /api/signals/ 的 price 字段）
 */
const fmtNum = (v: number | string | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || v === '') return '-';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isNaN(n)) return '-';
  return n.toFixed(digits);
};

/** 区域级 ErrorBoundary：K线/信号/指标子组件异常时降级为占位卡片，
 *  防止单一子组件崩溃导致整个 Modal 渲染失败（DETAIL-001 REOPENED 修复）
 */
interface SectionBoundaryProps {
  name: string;                  // 区域名（K线/信号/指标）
  children: ReactNode;
}
interface SectionBoundaryState {
  hasError: boolean;
  error: Error | null;
}
class SectionBoundary extends Component<SectionBoundaryProps, SectionBoundaryState> {
  state: SectionBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): SectionBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 4.3.7 异常态：记录到 console，便于排查
    console.error(`[StockDetailView] ${this.props.name} 子组件崩溃:`, error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="bg-bg-secondary border border-border-color rounded-lg p-4">
          <h3 className="text-sm font-medium text-text-primary mb-2">
            {this.props.name}区域加载失败
          </h3>
          <p className="text-xs text-text-muted">
            {this.state.error?.message || '未知错误'}
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}

/** 百分比格式化 */
const fmtPct = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return '-';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(digits)}%`;
};

/** 大数字格式化（万/亿） */
const fmtLarge = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return v.toFixed(0);
};

/** 上市板块枚举转中文 */
const boardName = (b?: string | null): string => {
  if (!b) return '-';
  // ListedBoard 本身就是中文（'上海主板' / '深圳主板' / '创业板' / '科创板' / '北交所'）
  return b;
};

// ============================================
// Mock 数据（开发态用）
// ============================================

const mockStockDetail: StockResponse = {
  stock_code: '000001',
  stock_name: '平安银行',
  listed_board: '上海主板',
  industry: '银行',
  sub_industry: '股份制银行',
  trade_date: '2026-06-05',
  pre_close: 12.13,
  open: 12.20,
  close: 12.45,
  high: 12.55,
  low: 12.10,
  volume: 854200,
  amount: 1058200000,
  change: 0.32,
  change_pct: 2.64,
  turnover_rate: 0.44,
  volume_ratio: 1.20,
  pe: 5.2,
  pb: 0.55,
  pe_ttm: 4.8,
  ps: 0.95,
  ps_ttm: 0.92,
  dv_ratio: 5.20,
  dv_ttm: 5.15,
  market_cap: 241500000000,
  circ_mv: 241500000000,
  float_share: 19406000000,
  ma5: 12.30,
  ma10: 12.25,
  ma20: 12.18,
  v_ma5: 820000,
  rsi_6: 58.4,
  rsi_12: 55.2,
  rsi_24: 52.8,
  macd: 0.05,
  boll_upper: 12.65,
  boll_mid: 12.18,
  boll_lower: 11.71,
  vol_ratio_5: 1.15,
  kdj_k: 62.5,
  kdj_d: 55.8,
  kdj_j: 75.9,
  cci: 35.2,
  consec_up_days: 2,
  is_st: false,
  is_new: false,
  limit_up: false,
  limit_down: false,
};

// ============================================
// 子组件：头部
// ============================================

interface HeaderProps {
  stock: StockResponse;
  onClose: () => void;
  onAddToWatchlist?: () => void;
  isInWatchlist?: boolean;
  addingToWatchlist?: boolean;
}

function DetailHeader({ stock, onClose, onAddToWatchlist, isInWatchlist, addingToWatchlist }: HeaderProps) {
  const changePct = stock.change_pct ?? 0;
  const isUp = changePct > 0;
  const isDown = changePct < 0;
  const colorClass = isUp
    ? 'text-up-green'
    : isDown
    ? 'text-down-red'
    : 'text-text-primary';

  return (
    <div className="flex items-start justify-between px-6 py-4 border-b border-border-color bg-bg-secondary">
      {/* 左侧：股票信息 */}
      <div className="flex-1">
        <div className="flex items-baseline gap-3">
          <h2 className="text-2xl font-bold text-text-primary">{stock.stock_name}</h2>
          <span className="text-text-muted text-sm">{stock.stock_code}</span>
          <span className="text-xs px-2 py-0.5 rounded bg-bg-card text-text-secondary border border-border-color">
            {boardName(stock.listed_board)}
          </span>
          {stock.is_st && (
            <span className="text-xs px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/40">
              ST
            </span>
          )}
          {stock.limit_up && (
            <span className="text-xs px-2 py-0.5 rounded bg-up-green/20 text-up-green border border-up-green/40">
              涨停
            </span>
          )}
          {stock.limit_down && (
            <span className="text-xs px-2 py-0.5 rounded bg-down-red/20 text-down-red border border-down-red/40">
              跌停
            </span>
          )}
        </div>

        <div className="flex items-baseline gap-4 mt-2">
          <span className={`text-3xl font-mono font-bold ${colorClass}`}>
            {fmtNum(stock.close)}
          </span>
          <span className={`text-base font-mono ${colorClass}`}>
            {stock.change !== null && stock.change !== undefined
              ? `${stock.change > 0 ? '+' : ''}${fmtNum(stock.change)}`
              : '-'}
          </span>
          <span className={`text-base font-mono ${colorClass}`}>
            {fmtPct(stock.change_pct)}
          </span>
          <span className="text-xs text-text-muted">
            {stock.trade_date} 收盘
          </span>
        </div>
      </div>

      {/* 右侧：加入自选 + 关闭 */}
      <div className="ml-4 flex items-center gap-2">
        {onAddToWatchlist && (
          <button
            onClick={onAddToWatchlist}
            disabled={isInWatchlist || addingToWatchlist}
            data-testid="add-to-watchlist-btn"
            className={`text-xs px-3 py-1.5 rounded border transition-colors ${
              isInWatchlist
                ? 'bg-bg-card border-up-green/40 text-up-green cursor-default'
                : 'bg-up-green text-white border-up-green hover:opacity-90'
            } disabled:opacity-70`}
            title={isInWatchlist ? '已在自选股中' : '加入自选股'}
          >
            {isInWatchlist
              ? '✓ 已自选'
              : addingToWatchlist
                ? '添加中…'
                : '+ 加入自选'}
          </button>
        )}
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded text-text-muted hover:text-text-primary hover:bg-bg-card transition-colors"
          title="关闭（ESC）"
          aria-label="关闭"
        >
          <span className="text-xl leading-none">×</span>
        </button>
      </div>
    </div>
  );
}

// ============================================
// 子组件：信息卡
// ============================================

interface InfoCardProps {
  title: string;
  items: Array<{ label: string; value: string; highlight?: 'up' | 'down' | 'muted' }>;
}

function InfoCard({ title, items }: InfoCardProps) {
  return (
    <div className="bg-bg-secondary border border-border-color rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 border-b border-border-color bg-bg-primary/40">
        <h3 className="text-sm font-medium text-text-primary">{title}</h3>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 p-4">
        {items.map((it) => (
          <div key={it.label} className="flex items-center justify-between text-xs">
            <span className="text-text-muted">{it.label}</span>
            <span
              className={`font-mono ${
                it.highlight === 'up'
                  ? 'text-up-green'
                  : it.highlight === 'down'
                  ? 'text-down-red'
                  : 'text-text-primary'
              }`}
            >
              {it.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================
// 子组件：K线区（4.3.4 集成）
// ============================================

interface KlineAreaProps {
  period: PeriodType;
  adj: AdjType;
  klineData: KLineItem[];
  klineLoading: boolean;
  klineError: string | null;
  signals: SignalItem[];
  subIndicator: SubIndicator;
  onPeriodChange: (p: PeriodType) => void;
  onAdjChange: (a: AdjType) => void;
  onSubIndicatorChange: (s: SubIndicator) => void;
}

function KlineArea({
  period,
  adj,
  klineData,
  klineLoading,
  klineError,
  signals,
  subIndicator,
  onPeriodChange,
  onAdjChange,
  onSubIndicatorChange,
}: KlineAreaProps) {
  return (
    <div className="bg-bg-secondary border border-border-color rounded-lg">
      {/* 工具栏 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-border-color">
        <h3 className="text-sm font-medium text-text-primary">K线图</h3>
        <div className="flex flex-wrap items-center gap-2">
          {/* 周期切换 */}
          <div className="flex items-center bg-bg-primary rounded border border-border-color overflow-hidden">
            {(['daily', 'weekly', 'monthly'] as PeriodType[]).map((p) => (
              <button
                key={p}
                onClick={() => onPeriodChange(p)}
                className={`text-xs px-2.5 py-1 transition-colors ${
                  period === p
                    ? 'bg-up-green text-white'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {p === 'daily' ? '日' : p === 'weekly' ? '周' : '月'}
              </button>
            ))}
          </div>
          {/* 复权切换 */}
          <div className="flex items-center bg-bg-primary rounded border border-border-color overflow-hidden">
            {(['none', 'forward', 'backward'] as AdjType[]).map((a) => (
              <button
                key={a}
                onClick={() => onAdjChange(a)}
                className={`text-xs px-2.5 py-1 transition-colors ${
                  adj === a
                    ? 'bg-up-green text-white'
                    : 'text-text-muted hover:text-text-primary'
                }`}
                title={
                  a === 'none' ? '不复权' : a === 'forward' ? '前复权' : '后复权'
                }
              >
                {a === 'none' ? '不复权' : a === 'forward' ? '前复权' : '后复权'}
              </button>
            ))}
          </div>
          {/* 副图指标切换（4.3.6） */}
          <div className="flex items-center bg-bg-primary rounded border border-border-color overflow-hidden">
            {(['VOL', 'MACD', 'RSI', 'KDJ'] as SubIndicator[]).map((s) => (
              <button
                key={s}
                onClick={() => onSubIndicatorChange(s)}
                className={`text-xs px-2.5 py-1 transition-colors ${
                  subIndicator === s
                    ? 'bg-up-green text-white'
                    : 'text-text-muted hover:text-text-primary'
                }`}
                title={`副图指标：${s}`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* K线主体 */}
      <div className="relative" style={{ minHeight: '420px' }}>
        {klineLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-bg-primary/60">
            <div className="flex flex-col items-center text-text-muted">
              <div className="w-8 h-8 border-2 border-up-green border-t-transparent rounded-full animate-spin mb-2" />
              <div className="text-xs">加载 K线数据...</div>
            </div>
          </div>
        )}
        {klineError && !klineLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-bg-primary/60">
            <div className="text-center text-text-muted">
              <div className="text-3xl mb-2 opacity-40">⚠️</div>
              <div className="text-sm text-down-red">{klineError}</div>
            </div>
          </div>
        )}
        <KlineChart
          data={klineData}
          signals={signals}
          period={period}
          adj={adj}
          subIndicator={subIndicator}
          height={400}
        />
      </div>
    </div>
  );
}

// ============================================
// 子组件：技术指标快照（4.3.6 - 仅数值快照，副图已移到 K线区）
// ============================================

interface IndicatorAreaProps {
  stock: StockResponse;
}

function IndicatorArea({ stock }: IndicatorAreaProps) {
  const latestIndicators = useMemo(
    () => [
      { label: 'MA5', value: fmtNum(stock.ma5) },
      { label: 'MA10', value: fmtNum(stock.ma10) },
      { label: 'MA20', value: fmtNum(stock.ma20) },
      { label: 'RSI6', value: fmtNum(stock.rsi_6, 1) },
      { label: 'MACD', value: fmtNum(stock.macd, 3) },
      { label: 'BOLL上', value: fmtNum(stock.boll_upper) },
      { label: 'BOLL中', value: fmtNum(stock.boll_mid) },
      { label: 'BOLL下', value: fmtNum(stock.boll_lower) },
      { label: 'KDJ_K', value: fmtNum(stock.kdj_k, 1) },
      { label: 'KDJ_D', value: fmtNum(stock.kdj_d, 1) },
      { label: 'KDJ_J', value: fmtNum(stock.kdj_j, 1) },
      { label: '连涨', value: stock.consec_up_days !== null ? `${stock.consec_up_days}天` : '-' },
    ],
    [stock]
  );

  return (
    <div className="bg-bg-secondary border border-border-color rounded-lg">
      <div className="px-4 py-2.5 border-b border-border-color">
        <h3 className="text-sm font-medium text-text-primary">技术指标快照</h3>
      </div>

      {/* 指标数值（当前快照） */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2 p-3">
        {latestIndicators.map((it) => (
          <div
            key={it.label}
            className="flex items-center justify-between bg-bg-primary/40 rounded px-3 py-2"
          >
            <span className="text-xs text-text-muted">{it.label}</span>
            <span className="text-xs font-mono text-text-primary">{it.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================
// 子组件：信号区（4.3.5 实现）
// ============================================

interface SignalAreaProps {
  signals: SignalItem[];
}

function SignalArea({ signals }: SignalAreaProps) {
  if (!signals || signals.length === 0) {
    return (
      <div className="bg-bg-secondary border border-border-color rounded-lg">
        <div className="px-4 py-2.5 border-b border-border-color">
          <h3 className="text-sm font-medium text-text-primary">买卖信号</h3>
        </div>
        <div className="h-[120px] flex items-center justify-center text-text-muted text-sm">
          <div className="text-center">
            <div className="text-3xl mb-2 opacity-40">📊</div>
            <div>该股票近期无买卖信号</div>
            <div className="text-xs mt-1 text-text-muted/60">
              信号已通过 tradeMarker 叠加到 K线图上
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 按日期倒序
  const sorted = [...signals].sort((a, b) =>
    b.trade_date.localeCompare(a.trade_date)
  );

  return (
    <div className="bg-bg-secondary border border-border-color rounded-lg">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-color">
        <h3 className="text-sm font-medium text-text-primary">买卖信号</h3>
        <span className="text-xs text-text-muted">共 {signals.length} 条</span>
      </div>
      <div className="max-h-[180px] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg-primary/80 backdrop-blur-sm">
            <tr className="text-text-muted">
              <th className="text-left px-3 py-1.5 font-medium">日期</th>
              <th className="text-left px-3 py-1.5 font-medium">类型</th>
              <th className="text-right px-3 py-1.5 font-medium">价格</th>
              <th className="text-left px-3 py-1.5 font-medium">原因</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-color/30">
            {sorted.map((sig, idx) => {
              // P2-SCHEMA-20260609: 后端已提供 direction 字段
              const isBuy = sig.direction === 'buy';
              return (
                <tr
                  key={`${sig.trade_date}-${idx}`}
                  className="hover:bg-bg-primary/30 transition-colors"
                >
                  <td className="px-3 py-1.5 font-mono text-text-secondary">
                    {sig.trade_date}
                  </td>
                  <td className="px-3 py-1.5">
                    <span
                      className={`inline-flex items-center gap-1 text-xs ${
                        isBuy ? 'text-up-green' : 'text-down-red'
                      }`}
                    >
                      <span>{isBuy ? '▲' : '▼'}</span>
                      <span>{isBuy ? '买入' : '卖出'}</span>
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-right text-text-primary">
                    {fmtNum(sig.price)}
                  </td>
                  <td className="px-3 py-1.5 text-text-muted truncate max-w-[200px]" title={sig.reason}>
                    {sig.reason}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================
// 主组件
// ============================================

export default function StockDetailView({ stockCode, onClose }: StockDetailViewProps) {
  const [stock, setStock] = useState<StockResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<PeriodType>('daily');
  const [adj, setAdj] = useState<AdjType>('forward');
  const [subIndicator, _setSubIndicator] = useState<SubIndicator>('VOL');
  // K线/信号（4.3.4/4.3.5）
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [klineLoading, setKlineLoading] = useState(false);
  const [klineError, setKlineError] = useState<string | null>(null);
  const [_signals, setSignals] = useState<SignalItem[]>([]);
  // 自选股（4.4.5 E2E 闭环）
  const [isInWatchlist, setIsInWatchlist] = useState(false);
  const [addingToWatchlist, setAddingToWatchlist] = useState(false);
  const [watchlistToast, setWatchlistToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const klineAbortRef = useRef<AbortController | null>(null);

  // toast 自动消失
  useEffect(() => {
    if (!watchlistToast) return;
    const t = setTimeout(() => setWatchlistToast(null), 2500);
    return () => clearTimeout(t);
  }, [watchlistToast]);

  // ========== 数据加载 ==========
  useEffect(() => {
    if (!stockCode) {
      setStock(null);
      setIsInWatchlist(false);
      return;
    }

    // 取消上一次请求
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    const load = async () => {
      // 开发态（USE_MOCK=true 且启用了 VITE_ENABLE_MOCK）走 mock
      if (USE_MOCK) {
        await new Promise((r) => setTimeout(r, 300)); // 模拟网络延迟
        setStock({ ...mockStockDetail, stock_code: stockCode });
        setIsInWatchlist(false);
        setLoading(false);
        return;
      }

      try {
        // 并行：拉详情 + 查自选状态
        const [resp, wlResp] = await Promise.all([
          fetchStockByCode(stockCode, controller.signal),
          fetchWatchlist('default', controller.signal).catch(() => null),
        ]);
        if (controller.signal.aborted) return; // aborted
        if (resp && resp.code === 200 && resp.data) {
          setStock(resp.data);
          setError(null);
        } else if (resp && resp.code === 404) {
          setError(`股票代码 ${stockCode} 不存在`);
          setStock(null);
        } else {
          setError(resp?.message || '获取股票详情失败');
          setStock(null);
        }
        // 自选状态：检查当前 stockCode 是否在用户自选中
        if (wlResp && wlResp.code === 200 && Array.isArray(wlResp.data)) {
          setIsInWatchlist(wlResp.data.some((w) => w.code === stockCode));
        } else {
          setIsInWatchlist(false);
        }
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : '网络错误');
        setStock(null);
        setIsInWatchlist(false);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    load();

    return () => controller.abort();
  }, [stockCode]);

  /**
   * 加入自选股（4.4.5 E2E 闭环）
   */
  const handleAddToWatchlist = useCallback(async () => {
    if (!stockCode || isInWatchlist || addingToWatchlist) return;
    setAddingToWatchlist(true);
    try {
      const resp = await addWatchlist(stockCode, '默认分组');
      if (resp.code === 200) {
        setIsInWatchlist(true);
        setWatchlistToast({ type: 'success', msg: `已添加 ${stockCode} 到自选` });
      } else if (resp.code === 409) {
        setIsInWatchlist(true); // 后端认为已在
        setWatchlistToast({ type: 'success', msg: `${stockCode} 已在自选股中` });
      } else {
        setWatchlistToast({ type: 'error', msg: resp.message || '添加失败' });
      }
    } catch (e) {
      setWatchlistToast({ type: 'error', msg: e instanceof Error ? e.message : '网络错误' });
    } finally {
      setAddingToWatchlist(false);
    }
  }, [stockCode, isInWatchlist, addingToWatchlist]);

  // ========== K线数据加载（4.3.4） ==========
  useEffect(() => {
    if (!stockCode) {
      setKlineData([]);
      return;
    }

    // 取消上一次 K线请求
    klineAbortRef.current?.abort();
    const controller = new AbortController();
    klineAbortRef.current = controller;

    setKlineLoading(true);
    setKlineError(null);

    const loadKline = async () => {
      // 开发态：生成 mock K线
      if (USE_MOCK) {
        await new Promise((r) => setTimeout(r, 400));
        if (controller.signal.aborted) return;
        // 生成 120 根 mock K线
        const mockKline: KLineItem[] = [];
        const baseDate = new Date('2026-06-05');
        let lastClose = 12.0;
        for (let i = 0; i < 120; i++) {
          const d = new Date(baseDate);
          d.setDate(d.getDate() - i);
          // 跳过周末（简单模拟）
          while (d.getDay() === 0 || d.getDay() === 6) {
            d.setDate(d.getDate() - 1);
          }
          const dateStr = d.toISOString().slice(0, 10);
          const change = (Math.random() - 0.48) * 0.4;
          const open = lastClose;
          const close = lastClose + change;
          const high = Math.max(open, close) + Math.random() * 0.2;
          const low = Math.min(open, close) - Math.random() * 0.2;
          const volume = 500000 + Math.random() * 800000;
          mockKline.push({
            trade_date: dateStr,
            open: parseFloat(open.toFixed(2)),
            close: parseFloat(close.toFixed(2)),
            high: parseFloat(high.toFixed(2)),
            low: parseFloat(low.toFixed(2)),
            volume: Math.floor(volume),
            amount: Math.floor(volume * close),
          });
          lastClose = close;
        }
        setKlineData(mockKline);
        setKlineLoading(false);
        return;
      }

      try {
        const resp = await fetchKline(
          stockCode,
          period,
          undefined,
          undefined,
          200,
          controller.signal
        );
        if (resp === null) return; // aborted
        if (resp.data && resp.data.length > 0) {
          setKlineData(resp.data);
          setKlineError(null);
        } else {
          setKlineData([]);
          setKlineError('暂无 K线数据');
        }
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') return;
        setKlineError(e instanceof Error ? e.message : 'K线加载失败');
        setKlineData([]);
      } finally {
        if (!controller.signal.aborted) {
          setKlineLoading(false);
        }
      }
    };

    loadKline();

    return () => controller.abort();
  }, [stockCode, period]); // 注：adj 由后端计算，前端不传

  // ========== 买卖信号加载（4.3.5 准备） ==========
  useEffect(() => {
    if (!stockCode) {
      setSignals([]);
      return;
    }

    // 信号暂用 mock，正式版会从 fetchSignals 接入
    if (USE_MOCK) {
      const mockSignals: SignalItem[] = [
        {
          trade_date: '2026-05-28',
          signal_type: 'macd_cross',
          direction: 'buy',
          price: 11.85,
          reason: 'MACD金叉 + BOLL下轨反弹',
        },
        {
          trade_date: '2026-06-02',
          signal_type: 'bollinger_breakout',
          direction: 'sell',
          price: 12.55,
          reason: 'BOLL上轨压力 + RSI超买',
        },
        {
          trade_date: '2026-06-04',
          signal_type: 'kdj_golden_cross',
          direction: 'buy',
          price: 12.20,
          reason: 'KDJ金叉',
        },
      ];
      setSignals(mockSignals);
      return;
    }

    const controller = new AbortController();
    fetchSignals(stockCode, undefined, undefined, undefined, 50, controller.signal)
      .then((resp) => {
        setSignals(resp.signals || []);
      })
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
        console.warn('[StockDetailView] signals load failed:', e);
        setSignals([]);
      });

    return () => controller.abort();
  }, [stockCode]);

  // ========== ESC 关闭 ==========
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // ========== 阻止 body 滚动 ==========
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // ========== 遮罩点击关闭（仅点击外层遮罩时） ==========
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  // ========== 渲染 ==========
  if (!stockCode) return null;

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={handleBackdropClick}
      data-testid="stock-detail-modal"
    >
      <div className="bg-bg-primary border border-border-color rounded-lg shadow-2xl w-full max-w-7xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* 头部 */}
        {stock ? (
          <DetailHeader
            stock={stock}
            onClose={onClose}
            onAddToWatchlist={handleAddToWatchlist}
            isInWatchlist={isInWatchlist}
            addingToWatchlist={addingToWatchlist}
          />
        ) : (
          <div className="flex items-center justify-between px-6 py-4 border-b border-border-color bg-bg-secondary">
            <h2 className="text-xl font-bold text-text-primary">股票详情</h2>
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded text-text-muted hover:text-text-primary hover:bg-bg-card"
              aria-label="关闭"
            >
              <span className="text-xl leading-none">×</span>
            </button>
          </div>
        )}

        {/* 主体内容 */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* 加载态 */}
          {loading && (
            <div className="flex flex-col items-center justify-center h-64 text-text-muted">
              <div className="w-10 h-10 border-2 border-up-green border-t-transparent rounded-full animate-spin mb-3" />
              <div className="text-sm">正在加载 {stockCode} 详情...</div>
            </div>
          )}

          {/* 错误态 */}
          {!loading && error && (
            <div className="flex flex-col items-center justify-center h-64 text-text-muted">
              <div className="text-5xl mb-3 opacity-40">⚠️</div>
              <div className="text-sm text-down-red">{error}</div>
              <button
                onClick={() => stockCode && setStock(null)}
                className="mt-3 text-xs text-text-muted hover:text-text-primary"
              >
                重试
              </button>
            </div>
          )}

          {/* 正常态 */}
          {!loading && !error && stock && (
            <>
              {/* 左侧：K线 + 信号 + 副图（用 SectionBoundary 隔离子组件异常） */}
              <div className="space-y-4">
                <SectionBoundary name="K线图">
                  <KlineArea
                    period={period}
                    adj={adj}
                    klineData={klineData}
                    klineLoading={klineLoading}
                    klineError={klineError}
                    signals={_signals}
                    subIndicator={subIndicator}
                    onPeriodChange={setPeriod}
                    onAdjChange={setAdj}
                    onSubIndicatorChange={_setSubIndicator}
                  />
                </SectionBoundary>
                <SectionBoundary name="买卖信号">
                  <SignalArea signals={_signals} />
                </SectionBoundary>
                <SectionBoundary name="技术指标">
                  <IndicatorArea stock={stock} />
                </SectionBoundary>
              </div>

              {/* 右侧：基本信息 + 行情（移动端上下堆叠） */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
                <InfoCard
                  title="基本信息"
                  items={[
                    { label: '行业', value: stock.industry ?? '-' },
                    { label: '细分行业', value: stock.sub_industry ?? '-' },
                    { label: '上市板块', value: boardName(stock.listed_board) },
                    { label: '总股本(万股)', value: stock.float_share ? fmtLarge(stock.float_share) : '-' },
                    { label: '流通股(万股)', value: stock.float_share ? fmtLarge(stock.float_share) : '-' },
                    { label: '交易日期', value: stock.trade_date },
                  ]}
                />
                <InfoCard
                  title="行情数据"
                  items={[
                    { label: '开盘', value: fmtNum(stock.open) },
                    { label: '最高', value: fmtNum(stock.high) },
                    { label: '最低', value: fmtNum(stock.low) },
                    { label: '昨收', value: fmtNum(stock.pre_close) },
                    { label: '成交量(手)', value: stock.volume ? fmtLarge(stock.volume) : '-' },
                    { label: '成交额', value: stock.amount ? fmtLarge(stock.amount) : '-' },
                  ]}
                />
                <InfoCard
                  title="估值与换手"
                  items={[
                    { label: '市盈率', value: fmtNum(stock.pe) },
                    { label: '市净率', value: fmtNum(stock.pb) },
                    { label: 'PE-TTM', value: fmtNum(stock.pe_ttm) },
                    { label: '总市值', value: stock.market_cap ? fmtLarge(stock.market_cap) : '-' },
                    { label: '流通市值', value: stock.circ_mv ? fmtLarge(stock.circ_mv) : '-' },
                    {
                      label: '换手率',
                      value: stock.turnover_rate !== null ? `${fmtNum(stock.turnover_rate)}%` : '-',
                    },
                  ]}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
