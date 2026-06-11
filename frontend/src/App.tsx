import { useState, useEffect, useCallback, useRef } from "react";
import StatusBar from "./components/StatusBar";
import ViewTabs, { type ViewType } from "./components/ViewTabs";
import Sidebar, { type IndicatorRangeValue } from "./components/Sidebar";
import StockPickerView from "./components/StockPickerView";
import WatchlistView from "./components/WatchlistView";
import BacktestView from "./components/BacktestView";
import SettingsView from "./components/SettingsView";
import StockDetailView from "./components/StockDetailView";
import { useUrlCode } from "./hooks/useUrlCode";
import {
  createGroup,
  flattenFilters,
  type FilterTree,
  type FlatFilters,
} from "./components/ConditionBuilder";
import type { ScreenerFilters, StockResponse } from "./types";
import { fetchStocks, fetchMeta } from "./api";

/**
 * 跨视图共享的"当前选中股票"
 * - 选股视图点击 → setSelectedCode → 打开详情 Modal
 * - 自选股点击 → setSelectedCode → 打开详情 Modal
 * - 详情页关闭 → 清空
 * - URL ?code= → 同步进来
 */
export type SelectedCodeContext = {
  selectedCode: string | null;
  setSelectedCode: (code: string | null) => void;
};

const DEFAULT_FILTERS: ScreenerFilters = {
  boards: ["all"],
  industries: [],
  patterns: [],
  sortBy: "score",
  sortOrder: "desc",
  topN: 20,
};

export default function App() {
  const [currentView, setCurrentView] = useState<ViewType>("stock-picker");
  const { code: urlCode, setCode: setUrlCode } = useUrlCode();
  // 选中态：Modal 始终以 urlCode 为准（URL 是唯一真相源）
  const [selectedCode, setSelectedCodeState] = useState<string | null>(urlCode);

  // 侧边栏"行情指标 / 财务指标"范围（按后端字段名）
  // 提升到 App.tsx 同时驱动 Sidebar 输入与 StockPickerView 列表查询
  const [marketIndicatorRanges, setMarketIndicatorRanges] = useState<
    Record<string, IndicatorRangeValue>
  >({});
  const [financialIndicatorRanges, setFinancialIndicatorRanges] = useState<
    Record<string, IndicatorRangeValue>
  >({});

  // ========== 条件构建器状态（已提升到顶层，Sidebar 与 StockPickerView 共享）==========
  const [conditionTree, setConditionTree] = useState<FilterTree>(() =>
    createGroup("AND")
  );
  const [builderCollapsed, setBuilderCollapsed] = useState(false);
  // 选股列表筛选条件（TopN / 排序）
  const [filters, setFilters] = useState<ScreenerFilters>(DEFAULT_FILTERS);

  // 数据状态
  const [stocks, setStocks] = useState<StockResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tradeDate, setTradeDate] = useState<string>("");
  const [total, setTotal] = useState<number>(0);

  const abortRef = useRef<AbortController | null>(null);

  // URL 变化 → 同步到 selectedCode
  useEffect(() => {
    setSelectedCodeState(urlCode);
  }, [urlCode]);

  // 选中态变化 → 同步到 URL
  const setSelectedCode = (code: string | null) => {
    setSelectedCodeState(code);
    setUrlCode(code);
  };

  // 加载元数据（trade_date）
  useEffect(() => {
    const ctrl = new AbortController();
    fetchMeta(ctrl.signal)
      .then((resp) => {
        if (resp.code === 200 && resp.data) {
          const raw = resp.data.trade_date;
          const formatted =
            raw && raw.length === 8
              ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
              : raw;
          setTradeDate(formatted);
        }
      })
      .catch((e) => {
        if (e instanceof Error && e.name === "AbortError") return;
        console.warn("[App] fetchMeta failed:", e);
      });
    return () => ctrl.abort();
  }, []);

  /**
   * 合并"条件构建器"的 rangeFilters 与"侧边栏指标"范围字典
   */
  function buildMergedRangeFilters(
    builderRanges: FlatFilters["rangeFilters"],
    sidebarMarket?: Record<string, IndicatorRangeValue>,
    sidebarFinancial?: Record<string, IndicatorRangeValue>
  ): FlatFilters["rangeFilters"] {
    const result: FlatFilters["rangeFilters"] = [...builderRanges];
    const builderFields = new Set(builderRanges.map((r) => r.field));
    const appendFromDict = (
      dict: Record<string, IndicatorRangeValue> | undefined,
      fallbackLabel: string
    ) => {
      if (!dict) return;
      for (const [field, range] of Object.entries(dict)) {
        if (builderFields.has(field)) continue;
        result.push({
          field,
          label: `${fallbackLabel}·${field}`,
          op: "between",
          min: range.min,
          max: range.max,
        });
      }
    };
    appendFromDict(sidebarMarket, "行情指标");
    appendFromDict(sidebarFinancial, "财务指标");
    return result;
  }

  /**
   * 客户端 range 过滤（后端暂不支持 range 条件时的兜底）
   */
  function applyRangeFilters(
    items: StockResponse[],
    ranges: FlatFilters["rangeFilters"]
  ): StockResponse[] {
    return items.filter((s) => {
      for (const r of ranges) {
        const v = (s as unknown as Record<string, number | null | undefined>)[r.field];
        if (v === null || v === undefined || typeof v !== "number") continue;
        if (r.op === "between") {
          if (r.min !== undefined && v < r.min) return false;
          if (r.max !== undefined && v > r.max) return false;
        } else if (r.op === "gt" && r.min !== undefined && !(v > r.min)) return false;
        else if (r.op === "gte" && r.min !== undefined && !(v >= r.min)) return false;
        else if (r.op === "lt" && r.min !== undefined && !(v < r.min)) return false;
        else if (r.op === "lte" && r.min !== undefined && !(v <= r.min)) return false;
        else if (r.op === "eq" && r.min !== undefined && v !== r.min) return false;
      }
      return true;
    });
  }

  // sortBy 前端 → 后端字段映射
  const SORT_FIELD_MAP: Record<string, string> = {
    score: "change_pct",
    turnover: "turnover_rate",
    maTrend: "ma20",
    volume: "volume",
  };

  // 加载股票列表（由"开始选股"按钮手动触发）
  // 读取当前最新的 conditionTree + 侧边栏范围，不再通过 appliedFlat 中转
  const loadStocks = useCallback(async () => {
    if (!tradeDate) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // 从 conditionTree 实时扁平化
    const flat = flattenFilters(conditionTree);
    const mergedRanges = buildMergedRangeFilters(
      flat.rangeFilters,
      marketIndicatorRanges,
      financialIndicatorRanges
    );

    setLoading(true);
    setError(null);
    try {
      const sortBy = SORT_FIELD_MAP[filters.sortBy] ?? "change_pct";
      const filtersParam =
        flat.boolFilters.length > 0 ? flat.boolFilters.join(",") : undefined;
      const hasRange = mergedRanges.length > 0;
      const fetchLimit = hasRange ? 200 : filters.topN;
      const resp = await fetchStocks(
        {
          sort_by: sortBy,
          sort_asc: filters.sortOrder === "asc",
          offset: 0,
          limit: fetchLimit,
          as_of_date: tradeDate,
          filters: filtersParam,
        },
        { signal: ctrl.signal }
      );
      if (ctrl.signal.aborted) return;
      if (resp.code === 200 && resp.data) {
        const rawItems = resp.data.items;
        const rangeFiltered = hasRange
          ? applyRangeFilters(rawItems, mergedRanges)
          : rawItems;
        const finalItems = hasRange
          ? rangeFiltered.slice(0, filters.topN)
          : rangeFiltered;
        setStocks(finalItems);
        setTotal(
          typeof resp.data.total === "number" ? resp.data.total : rangeFiltered.length
        );
      } else {
        setError(resp.message || "加载失败");
        setStocks([]);
      }
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      setError(e instanceof Error ? e.message : "网络错误");
      setStocks([]);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [
    tradeDate,
    filters.sortBy,
    filters.sortOrder,
    filters.topN,
    conditionTree,
    marketIndicatorRanges,
    financialIndicatorRanges,
  ]);

  // 卸载时取消
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // 「开始选股」按钮：手动触发选股
  const handleStartScreener = useCallback(() => {
    loadStocks();
  }, [loadStocks]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg-primary text-text-primary dark">
      {/* 顶部状态栏 */}
      <StatusBar />

      {/* 视图标签 */}
      <ViewTabs currentView={currentView} onViewChange={setCurrentView} />

      {/* 主体区域 — min-h-0 是关键，让 flex 子项可被压缩到内容以下，
          避免被内容撑高后导致 aside/main 撑出视口产生页面级滚动 */}
      <div className="flex flex-1 min-h-0">
        {/* 左侧功能区 */}
        <Sidebar
          currentView={currentView}
          onMarketIndicatorRangesChange={setMarketIndicatorRanges}
          onFinancialIndicatorRangesChange={setFinancialIndicatorRanges}
          conditionTree={conditionTree}
          onConditionTreeChange={setConditionTree}
          builderCollapsed={builderCollapsed}
          onToggleBuilderCollapsed={() => setBuilderCollapsed((c) => !c)}
          onStartScreener={handleStartScreener}
        />

        {/* 右侧主工作区 */}
        <main className="flex flex-col flex-1 overflow-hidden relative">
          {currentView === "stock-picker" && (
            <StockPickerView
              selectedCode={selectedCode}
              onSelectCode={setSelectedCode}
              marketIndicatorRanges={marketIndicatorRanges}
              financialIndicatorRanges={financialIndicatorRanges}
              stocks={stocks}
              loading={loading}
              error={error}
              tradeDate={tradeDate}
              total={total}
              filters={filters}
              onFiltersChange={setFilters}
              onRefresh={loadStocks}
              conditionTree={conditionTree}
            />
          )}
          {currentView === "watchlist" && (
            <WatchlistView
              selectedCode={selectedCode}
              onSelectCode={setSelectedCode}
            />
          )}
          {currentView === "backtest" && <BacktestView />}
          {currentView === "settings" && <SettingsView />}
        </main>
      </div>

      {/* 股票详情 Modal（全局唯一） */}
      {selectedCode && (
        <StockDetailView
          stockCode={selectedCode}
          onClose={() => setSelectedCode(null)}
        />
      )}
    </div>
  );
}
