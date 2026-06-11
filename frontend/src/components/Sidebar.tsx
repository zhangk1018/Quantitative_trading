import { type ViewType } from "./ViewTabs";
import { useState, useEffect } from "react";
import TechnicalIndicatorDialog, {
  DEFAULT_TECHNICAL_CONFIG,
  type TechnicalIndicator,
  type IndicatorConfig,
} from "./TechnicalIndicatorDialog";
import ConditionBuilder, {
  type FilterTree,
} from "./ConditionBuilder";

/**
 * 行情/财务指标范围回调：
 * - key 是后端数据库字段名（如 circ_mv、close、net_profit）
 * - value 是 min/max 范围（between 操作）
 *
 * 父组件拿到后可与 ConditionBuilder 的 rangeFilters 合并
 */
export type IndicatorRangeValue = { min?: number; max?: number };

interface SidebarProps {
  currentView: ViewType;
  /**
   * 行情指标范围变化回调（min/max，按后端字段名）— 由父组件传入，
   * 用于将范围条件合并到表格查询
   */
  onMarketIndicatorRangesChange?: (ranges: Record<string, IndicatorRangeValue>) => void;
  /**
   * 财务指标范围变化回调（min/max，按后端字段名）— 由父组件传入，
   * 用于将范围条件合并到表格查询
   */
  onFinancialIndicatorRangesChange?: (ranges: Record<string, IndicatorRangeValue>) => void;
  // ========== 条件构建器（Phase 6.1.a 提升到左侧功能区）==========
  /** 条件树（受控） */
  conditionTree?: FilterTree;
  onConditionTreeChange?: (tree: FilterTree) => void;
  /** 折叠态 */
  builderCollapsed?: boolean;
  onToggleBuilderCollapsed?: () => void;
  // 「开始选股」按钮：手动触发选股
  onStartScreener?: () => void;
}

export default function Sidebar({
  currentView,
  onMarketIndicatorRangesChange,
  onFinancialIndicatorRangesChange,
  conditionTree,
  onConditionTreeChange,
  builderCollapsed,
  onToggleBuilderCollapsed,
  onStartScreener,
}: SidebarProps) {
  return (
    <aside className="w-[280px] h-full bg-bg-secondary border-r border-border-color flex flex-col flex-shrink-0 overflow-hidden">
      {currentView === "stock-picker" && (
        <StockPickerSidebar
          onMarketIndicatorRangesChange={onMarketIndicatorRangesChange}
          onFinancialIndicatorRangesChange={onFinancialIndicatorRangesChange}
          conditionTree={conditionTree}
          onConditionTreeChange={onConditionTreeChange}
          builderCollapsed={builderCollapsed}
          onToggleBuilderCollapsed={onToggleBuilderCollapsed}
          onStartScreener={onStartScreener}
        />
      )}
      {currentView === "watchlist" && <WatchlistSidebar />}
      {currentView === "backtest" && <BacktestSidebar />}
      {currentView === "settings" && <SettingsSidebar />}
    </aside>
  );
}

function WatchlistSidebar() {
  const groups = [
    "全部自选",
    "金融股",
    "科技股",
    "消费股",
    "自定义分组1",
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">分组管理</h4>
        <div className="space-y-1">
          {groups.map((group, index) => (
            <button
              key={group}
              className={`w-full text-left px-3 py-2 text-xs rounded transition-colors ${
                index === 0
                  ? "bg-bg-primary text-text-primary font-medium"
                  : "text-text-secondary hover:bg-bg-card"
              }`}
            >
              {group}
            </button>
          ))}
        </div>
        <button className="w-full mt-3 bg-bg-card border border-border-color text-text-primary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">
          + 新建分组
        </button>
      </div>

      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">快捷筛选</h4>
        <div className="space-y-2">
          <button className="w-full bg-up-green/10 border border-up-green/30 text-up-green text-xs px-3 py-2 rounded hover:bg-up-green/20 transition-colors">
            今日上涨
          </button>
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">
            今日下跌
          </button>
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">
            涨幅超5%
          </button>
        </div>
      </div>

      <div className="p-3">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">统计</h4>
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-text-muted">自选数量</span>
            <span className="text-text-primary">12</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">今日上涨</span>
            <span className="text-up-green">8</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">今日下跌</span>
            <span className="text-down-red">4</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function StockPickerSidebar({
  onMarketIndicatorRangesChange,
  onFinancialIndicatorRangesChange,
  conditionTree,
  onConditionTreeChange,
  builderCollapsed,
  onToggleBuilderCollapsed,
  onStartScreener,
}: {
  onMarketIndicatorRangesChange?: (
    ranges: Record<string, IndicatorRangeValue>
  ) => void;
  onFinancialIndicatorRangesChange?: (
    ranges: Record<string, IndicatorRangeValue>
  ) => void;
  // 条件构建器 props（Phase 6.1.a：条件构建器已加入左侧功能区）
  conditionTree?: FilterTree;
  onConditionTreeChange?: (tree: FilterTree) => void;
  builderCollapsed?: boolean;
  onToggleBuilderCollapsed?: () => void;
  // 「开始选股」按钮（手动触发选股；条件构建器内部已有「重置」按钮）
  onStartScreener?: () => void;
}) {
  const [isRangeExpanded, setIsRangeExpanded] = useState(true);
  // 行情指标 / 财务指标 / 技术指标 折叠状态
  const [isMarketIndicatorsExpanded, setIsMarketIndicatorsExpanded] = useState(true);
  const [isFinancialExpanded, setIsFinancialExpanded] = useState(true);
  const [isTechnicalExpanded, setIsTechnicalExpanded] = useState(true);
  // 选中状态
  const [selectedMarketIndicators, setSelectedMarketIndicators] = useState<string[]>(["成交额"]);
  // 行情指标的范围（min/max）— 点击指标后输入"~"分隔的范围，作为后续筛选条件
  const [marketIndicatorRanges, setMarketIndicatorRanges] = useState<
    Record<string, { min?: number; max?: number }>
  >({});
  const [selectedFinancialIndicators, setSelectedFinancialIndicators] = useState<string[]>([]);
  // 财务指标的范围（min/max）— 同行情指标逻辑
  const [financialIndicatorRanges, setFinancialIndicatorRanges] = useState<
    Record<string, { min?: number; max?: number }>
  >({});
  // 技术指标：已选中的指标名（MA/MACD/BOLL）— 点击按钮后弹窗保存即加入
  const [selectedTechnicalIndicators, setSelectedTechnicalIndicators] = useState<string[]>([]);
  // 技术指标配置（每个指标的完整配置，独立存储）
  const [technicalConfig, setTechnicalConfig] = useState<typeof DEFAULT_TECHNICAL_CONFIG>(
    () => ({
      MA: { conditions: DEFAULT_TECHNICAL_CONFIG.MA.conditions.map((c) => ({ ...c })) },
      MACD: { ...DEFAULT_TECHNICAL_CONFIG.MACD },
      BOLL: { ...DEFAULT_TECHNICAL_CONFIG.BOLL },
    })
  );
  // 当前打开的弹窗对应的指标（null = 关闭）
  const [activeTechDialog, setActiveTechDialog] = useState<TechnicalIndicator | null>(null);
  const [listingPlaces, setListingPlaces] = useState<string[]>([
    "全部", "上海主板", "深证主板", "创业板", "科创板"
  ]);
  const [isListingPlacesOpen, setIsListingPlacesOpen] = useState(false);
  // 所属市场（港股/美股/沪深）：单选
  const [selectedMarket, setSelectedMarket] = useState<"港股" | "美股" | "沪深">("沪深");
  // 股票范围：单选（全部/仅看自选）
  const [selectedScope, setSelectedScope] = useState<"全部" | "仅看自选">("全部");

  const allListingPlaces = [
    { label: "全部", value: "全部" },
    { label: "上海主板", value: "上海主板" },
    { label: "深证主板", value: "深证主板" },
    { label: "创业板", value: "创业板" },
    { label: "科创板", value: "科创板" },
  ];

  // 行情指标 → 后端字段映射
  // 振幅 / 每手价格 / 委比 三个因后端无字段已从前端移除（详见协作单 [6.1-INDICATOR-20260611]）
  // 后端字段名见 types.ts 中 StockResponse
  const MARKET_INDICATOR_FIELD_MAP: Record<
    string,
    { field: string; unit?: string } | null
  > = {
    "市值": { field: "circ_mv", unit: "万" },
    "价格": { field: "close", unit: "元" },
    "涨跌幅": { field: "change_pct", unit: "%" },
    "市盈率(静)": { field: "pe", unit: "倍" },
    "市盈率(TTM)": { field: "pe_ttm", unit: "倍" },
    "市净率": { field: "pb", unit: "倍" },
    "量比": { field: "volume_ratio", unit: "倍" },
    "成交额": { field: "amount", unit: "元" },
    "成交量": { field: "volume", unit: "手" },
    "换手率": { field: "turnover_rate", unit: "%" },
  };

  // 财务指标 → 后端字段映射
  // 净利润/营业收入/净资产收益率 字段在 stock_fundamental_pit 表中，待后端导出 parquet 后才能生效
  // 净利润增长率/营收增长率/毛利率/净利率/资产负债率 因后端无字段已从前端移除
  // （详见协作单 [6.1-INDICATOR-20260611]）
  const FINANCIAL_INDICATOR_FIELD_MAP: Record<
    string,
    { field: string; unit?: string; note?: string } | null
  > = {
    "净利润": { field: "net_profit", unit: "元" },
    "营业收入": { field: "revenue", unit: "元" },
    "净资产收益率": { field: "roe", unit: "%" },
  };

  // 更新某个行情指标的范围（min 或 max）
  const updateIndicatorRange = (
    ind: string,
    key: "min" | "max",
    value: string
  ) => {
    setMarketIndicatorRanges((prev) => {
      const cur = prev[ind] || {};
      const next: { min?: number; max?: number } = { ...cur };
      if (value === "" || value === undefined) {
        delete next[key];
      } else {
        const num = Number(value);
        if (Number.isFinite(num)) next[key] = num;
      }
      if (Object.keys(next).length === 0) {
        const { [ind]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [ind]: next };
    });
  };

  // 更新某个财务指标的范围
  const updateFinancialRange = (
    ind: string,
    key: "min" | "max",
    value: string
  ) => {
    setFinancialIndicatorRanges((prev) => {
      const cur = prev[ind] || {};
      const next: { min?: number; max?: number } = { ...cur };
      if (value === "" || value === undefined) {
        delete next[key];
      } else {
        const num = Number(value);
        if (Number.isFinite(num)) next[key] = num;
      }
      if (Object.keys(next).length === 0) {
        const { [ind]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [ind]: next };
    });
  };

  // 监听范围变化，向上回调
  // 把"行情指标"的中文标签范围转换为"后端字段名"范围后再回调
  // 父组件只需要关心数据库字段，与 ConditionBuilder 的 FlatFilters.rangeFilters 保持一致
  useEffect(() => {
    const out: Record<string, IndicatorRangeValue> = {};
    for (const [label, range] of Object.entries(marketIndicatorRanges)) {
      const meta = MARKET_INDICATOR_FIELD_MAP[label];
      if (!meta) continue;
      out[meta.field] = range;
    }
    onMarketIndicatorRangesChange?.(out);
  }, [marketIndicatorRanges, onMarketIndicatorRangesChange]);

  useEffect(() => {
    const out: Record<string, IndicatorRangeValue> = {};
    for (const [label, range] of Object.entries(financialIndicatorRanges)) {
      const meta = FINANCIAL_INDICATOR_FIELD_MAP[label];
      if (!meta) continue;
      out[meta.field] = range;
    }
    onFinancialIndicatorRangesChange?.(out);
  }, [financialIndicatorRanges, onFinancialIndicatorRangesChange]);

  const toggleListingPlace = (place: string) => {
    if (place === "全部") {
      if (listingPlaces.length === allListingPlaces.length) {
        setListingPlaces([]);
      } else {
        setListingPlaces(allListingPlaces.map((p) => p.value));
      }
    } else {
      if (listingPlaces.includes(place)) {
        const newPlaces = listingPlaces.filter((p) => p !== place && p !== "全部");
        setListingPlaces(newPlaces);
      } else {
        const newPlaces = [...listingPlaces.filter((p) => p !== "全部"), place];
        setListingPlaces(newPlaces.length === allListingPlaces.length - 1 
          ? allListingPlaces.map((p) => p.value) 
          : newPlaces);
      }
    }
  };

  const getDisplayText = () => {
    if (listingPlaces.length === 0) return "全部";
    if (listingPlaces.includes("全部")) return "全部";
    if (listingPlaces.length === allListingPlaces.length - 1) return "全部";
    if (listingPlaces.length <= 2) return listingPlaces.join(",");
    return `已选 ${listingPlaces.length}项`;
  };

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (_event: MouseEvent) => {
      if (isListingPlacesOpen) {
        setIsListingPlacesOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [isListingPlacesOpen]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 滚动区：范围(3) + 指标 + 因子配置 整体共用 1 个滚动条（左面设置项） */}
      <div className="flex-1 overflow-y-auto">
      {/* 范围(3) — 顶部，参与整体滚动 */}
      <div className="px-3 py-2 border-b border-border-color relative z-50">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-text-secondary font-semibold text-xs">范围(3)</h4>
          <button
            className="text-text-muted text-xs hover:text-text-primary transition-colors"
            onClick={() => setIsRangeExpanded(!isRangeExpanded)}
          >
            {isRangeExpanded ? "▼" : "▶"}
          </button>
        </div>

        {isRangeExpanded && (
          <>
            {/* 所属市场 — 单选（港股/美股暂无数据，仅占位） */}
            <div className="mb-2.5">
              <label className="block text-text-secondary mb-1.5 text-xs">所属市场</label>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer opacity-50" title="暂无数据">
                  <input
                    type="radio"
                    name="market"
                    checked={selectedMarket === "港股"}
                    onChange={() => setSelectedMarket("港股")}
                    className="accent-up-green"
                  />
                  <span className="text-text-primary text-xs">港股</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer opacity-50" title="暂无数据">
                  <input
                    type="radio"
                    name="market"
                    checked={selectedMarket === "美股"}
                    onChange={() => setSelectedMarket("美股")}
                    className="accent-up-green"
                  />
                  <span className="text-text-primary text-xs">美股</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="market"
                    checked={selectedMarket === "沪深"}
                    onChange={() => setSelectedMarket("沪深")}
                    className="accent-up-green"
                  />
                  <span className="text-text-primary text-xs">沪深</span>
                </label>
              </div>
            </div>

            {/* 上市地 - 多选下拉 */}
            <div className="mb-2.5">
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-text-secondary text-xs">上市地</label>
                <div className="relative">
                  <button
                    className="bg-bg-card border border-border-color text-text-primary text-xs px-2 py-1 rounded flex items-center gap-2"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsListingPlacesOpen(!isListingPlacesOpen);
                    }}
                  >
                    <span>{getDisplayText()}</span>
                    <span className="text-text-muted">▼</span>
                  </button>

                  {isListingPlacesOpen && (
                    <div className="absolute z-[60] mt-1 right-0 bg-bg-card border border-border-color rounded shadow-lg w-48" onClick={(e) => e.stopPropagation()}>
                      {allListingPlaces.map((place) => (
                        <label
                          key={place.value}
                          className="flex items-center gap-2 px-3 py-2 hover:bg-bg-primary cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={listingPlaces.includes(place.value)}
                            onChange={() => toggleListingPlace(place.value)}
                            className="accent-up-green"
                          />
                          <span className="text-text-primary text-xs">{place.label}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 股票范围 — 与上市地是 AND 关系（同时满足两个条件才返回） */}
            <div className="mb-1">
              <div className="flex items-center gap-4">
                <label className="text-text-secondary text-xs">股票范围</label>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="stockScope"
                      checked={selectedScope === "全部"}
                      onChange={() => setSelectedScope("全部")}
                      className="accent-up-green"
                    />
                    <span className="text-text-primary text-xs">全部</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="stockScope"
                      checked={selectedScope === "仅看自选"}
                      onChange={() => setSelectedScope("仅看自选")}
                      className="accent-up-green"
                    />
                    <span className="text-text-primary text-xs">仅看自选</span>
                  </label>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

        {/* 行情指标(1) */}
        <div className="border-b border-border-color">
          <div className="px-3 py-1.5 flex items-center justify-between">
            <h4 className="text-text-secondary text-xs font-semibold">行情指标({selectedMarketIndicators.length})</h4>
            <button
              className="text-text-muted text-xs hover:text-text-primary transition-colors"
              onClick={() => setIsMarketIndicatorsExpanded(!isMarketIndicatorsExpanded)}
            >
              {isMarketIndicatorsExpanded ? "▼" : "▶"}
            </button>
          </div>
          {isMarketIndicatorsExpanded && (
            <div className="px-3 pb-2">
              <div className="grid grid-cols-2 gap-1.5">
                {["市值", "价格", "涨跌幅", "市盈率(静)", "市盈率(TTM)", "市净率", "量比", "成交额", "成交量", "换手率"].map((ind) => {
                  const selected = selectedMarketIndicators.includes(ind);
                  const meta = MARKET_INDICATOR_FIELD_MAP[ind];
                  const disabled = meta === null;
                  return (
                    <button
                      key={ind}
                      onClick={() => {
                        if (disabled) return;
                        setSelectedMarketIndicators((prev) =>
                          prev.includes(ind) ? prev.filter((x) => x !== ind) : [...prev, ind]
                        );
                      }}
                      title={disabled ? "暂缺数据字段" : (selected ? "点击取消" : "点击添加范围筛选")}
                      className={`text-xs px-2 py-1.5 rounded transition-colors ${
                        disabled
                          ? "bg-bg-card border border-border-color text-text-muted opacity-40 cursor-not-allowed"
                          : selected
                          ? "bg-up-green text-white"
                          : "bg-bg-card border border-border-color text-text-secondary hover:bg-bg-secondary"
                      }`}
                    >
                      {ind}
                    </button>
                  );
                })}
              </div>
              {/* 选中指标的范围输入（min ~ max） */}
              {selectedMarketIndicators.length > 0 && (
                <div className="mt-2 space-y-1.5" data-testid="indicator-ranges">
                  <div className="text-text-muted text-xs">📊 范围条件：</div>
                  {selectedMarketIndicators.map((ind) => {
                    const meta = MARKET_INDICATOR_FIELD_MAP[ind];
                    if (!meta) return null;
                    const range = marketIndicatorRanges[ind] || {};
                    return (
                      <div
                        key={ind}
                        className="flex items-center gap-1.5"
                        data-testid={`range-${ind}`}
                      >
                        <span className="text-text-secondary text-xs w-20 truncate" title={ind}>
                          {ind}({meta.unit || ''})
                        </span>
                        <input
                          type="number"
                          inputMode="decimal"
                          value={range.min ?? ""}
                          placeholder="min"
                          onChange={(e) => updateIndicatorRange(ind, "min", e.target.value)}
                          data-testid={`range-${ind}-min`}
                          className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded"
                        />
                        <span className="text-text-muted text-xs">~</span>
                        <input
                          type="number"
                          inputMode="decimal"
                          value={range.max ?? ""}
                          placeholder="max"
                          onChange={(e) => updateIndicatorRange(ind, "max", e.target.value)}
                          data-testid={`range-${ind}-max`}
                          className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded"
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 财务指标 */}
        <div className="border-b border-border-color">
          <div className="px-3 py-1.5 flex items-center justify-between">
            <h4 className="text-text-secondary text-xs font-semibold">财务指标({selectedFinancialIndicators.length})</h4>
            <button
              className="text-text-muted text-xs hover:text-text-primary transition-colors"
              onClick={() => setIsFinancialExpanded(!isFinancialExpanded)}
            >
              {isFinancialExpanded ? "▼" : "▶"}
            </button>
          </div>
          {isFinancialExpanded && (
            <div className="px-3 pb-2">
              {/* 财务指标 2列网格 — 点击按钮添加范围筛选（min ~ max） */}
              <div className="grid grid-cols-2 gap-1.5">
                {["净利润", "营业收入", "净资产收益率"].map((ind) => {
                  const selected = selectedFinancialIndicators.includes(ind);
                  const meta = FINANCIAL_INDICATOR_FIELD_MAP[ind];
                  const disabled = meta === null;
                  return (
                    <button
                      key={ind}
                      onClick={() => {
                        if (disabled) return;
                        setSelectedFinancialIndicators((prev) =>
                          prev.includes(ind) ? prev.filter((x) => x !== ind) : [...prev, ind]
                        );
                      }}
                      title={disabled ? "暂缺数据字段" : (selected ? "点击取消" : "点击添加范围筛选")}
                      className={`text-xs px-2 py-1.5 rounded transition-colors ${
                        disabled
                          ? "bg-bg-card border border-border-color text-text-muted opacity-40 cursor-not-allowed"
                          : selected
                          ? "bg-up-green text-white"
                          : "bg-bg-card border border-border-color text-text-secondary hover:bg-bg-secondary"
                      }`}
                    >
                      {ind}
                    </button>
                  );
                })}
              </div>
              {/* 选中财务指标的范围输入（min ~ max） */}
              {selectedFinancialIndicators.length > 0 && (
                <div className="mt-2 space-y-1.5" data-testid="financial-indicator-ranges">
                  <div className="text-text-muted text-xs">📊 范围条件：</div>
                  {selectedFinancialIndicators.map((ind) => {
                    const meta = FINANCIAL_INDICATOR_FIELD_MAP[ind];
                    if (!meta) return null;
                    const range = financialIndicatorRanges[ind] || {};
                    return (
                      <div
                        key={ind}
                        className="flex items-center gap-1.5"
                        data-testid={`financial-range-${ind}`}
                      >
                        <span className="text-text-secondary text-xs w-20 truncate" title={ind}>
                          {ind}({meta.unit || ''})
                        </span>
                        <input
                          type="number"
                          inputMode="decimal"
                          value={range.min ?? ""}
                          placeholder="min"
                          onChange={(e) => updateFinancialRange(ind, "min", e.target.value)}
                          data-testid={`financial-range-${ind}-min`}
                          className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded"
                        />
                        <span className="text-text-muted text-xs">~</span>
                        <input
                          type="number"
                          inputMode="decimal"
                          value={range.max ?? ""}
                          placeholder="max"
                          onChange={(e) => updateFinancialRange(ind, "max", e.target.value)}
                          data-testid={`financial-range-${ind}-max`}
                          className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded"
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 技术指标 */}
        <div className="border-b border-border-color">
          <div className="px-3 py-1.5 flex items-center justify-between">
            <h4 className="text-text-secondary text-xs font-semibold">技术指标({selectedTechnicalIndicators.length})</h4>
            <button
              className="text-text-muted text-xs hover:text-text-primary transition-colors"
              onClick={() => setIsTechnicalExpanded(!isTechnicalExpanded)}
            >
              {isTechnicalExpanded ? "▼" : "▶"}
            </button>
          </div>
          {isTechnicalExpanded && (
            <div className="px-3 pb-2">
              {/* 仅 MA / MACD / BOLL 三个技术指标，点击弹出配置弹窗 */}
              <div className="grid grid-cols-2 gap-1.5">
                {(["MA", "MACD", "BOLL"] as const).map((ind) => {
                  const selected = selectedTechnicalIndicators.includes(ind);
                  return (
                    <button
                      key={ind}
                      onClick={() => setActiveTechDialog(ind)}
                      title={selected ? "已添加，点击修改配置" : "点击配置并添加筛选"}
                      data-testid={`tech-btn-${ind}`}
                      className={`text-xs px-2 py-1.5 rounded transition-colors ${
                        selected
                          ? "bg-up-green text-white"
                          : "bg-bg-card border border-border-color text-text-secondary hover:bg-bg-secondary"
                      }`}
                    >
                      {ind}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* 条件构建器（Phase 6.1.a：从 StockPickerView 顶部移入左侧功能区） */}
        {conditionTree && onConditionTreeChange && (
          <div className="border-b border-border-color">
            <ConditionBuilder
              tree={conditionTree}
              onChange={onConditionTreeChange}
              collapsed={builderCollapsed ?? false}
              onToggleCollapsed={onToggleBuilderCollapsed}
            />
          </div>
        )}

        <div className="px-3 py-2 border-b border-border-color">
          <h4 className="text-text-secondary text-xs mb-1.5 font-semibold">⚖️ 因子打分配置</h4>
          <div className="space-y-1.5 text-xs">
            <div>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-text-secondary">换手率</span>
                <span className="text-text-primary">30%</span>
              </div>
              <input
                type="range"
                defaultValue={30}
                className="w-full accent-up-green"
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-text-secondary">MA趋势</span>
                <span className="text-text-primary">40%</span>
              </div>
              <input
                type="range"
                defaultValue={40}
                className="w-full accent-up-green"
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-text-secondary">成交量</span>
                <span className="text-text-primary">30%</span>
              </div>
              <input
                type="range"
                defaultValue={30}
                className="w-full accent-up-green"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 固定底部：「开始选股」— 「重置」按钮已移入条件构建器内部 */}
      <div className="px-3 py-2 border-t border-border-color flex-shrink-0 bg-bg-secondary">
        <button
          onClick={onStartScreener}
          data-testid="start-screener"
          className="w-full bg-up-green text-white text-sm font-medium px-4 py-2 rounded hover:opacity-90 transition-opacity"
        >
          ▶ 开始选股
        </button>
      </div>

      {/* 技术指标配置弹窗（MA / MACD / BOLL） */}
      {activeTechDialog && (
        <TechnicalIndicatorDialog
          indicator={activeTechDialog}
          initialConfig={technicalConfig[activeTechDialog]}
          onConfirm={(config: IndicatorConfig) => {
            // 1) 把当前编辑结果写入对应指标的配置
            setTechnicalConfig((prev) => ({
              ...prev,
              [activeTechDialog]: config as typeof prev[typeof activeTechDialog],
            }));
            // 2) 把该指标加入"已选"列表（确保"参与后续运算"）
            setSelectedTechnicalIndicators((prev) =>
              prev.includes(activeTechDialog) ? prev : [...prev, activeTechDialog]
            );
            // 3) 关闭弹窗
            setActiveTechDialog(null);
          }}
          onCancel={() => setActiveTechDialog(null)}
        />
      )}
    </div>
  );
}

function BacktestSidebar() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">🎯 标的列表</h4>
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2 text-text-primary">
            <input type="radio" name="backtest-stock" defaultChecked className="accent-up-green" />
            <span>000001 平安银行</span>
          </div>
          <div className="flex items-center gap-2 text-text-primary">
            <input type="radio" name="backtest-stock" className="accent-up-green" />
            <span>000002 万科A</span>
          </div>
        </div>
        <button className="w-full mt-3 bg-bg-card border border-border-color text-text-primary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">
          [+ 添加标的]
        </button>
      </div>

      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">📅 时间周期</h4>
        <div className="space-y-2 text-xs">
          <div className="flex gap-1">
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">
              1分
            </button>
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">
              5分
            </button>
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">
              15分
            </button>
          </div>
          <div className="flex gap-1">
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">
              1小时
            </button>
            <button className="flex-1 bg-up-green text-white text-xs px-2 py-1 rounded">
              日线
            </button>
          </div>
        </div>
      </div>

      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">⚙️ 策略控制</h4>
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2">
            <input type="checkbox" defaultChecked className="accent-up-green" />
            <span className="text-text-secondary">启用策略</span>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" className="accent-up-green" />
            <span className="text-text-secondary">仅查看K线</span>
          </div>
          <button className="w-full mt-2 bg-up-green text-white text-xs font-medium px-3 py-2 rounded hover:opacity-90 transition-opacity">
            ▶ 重新回测
          </button>
        </div>
      </div>

      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">📊 图表显示</h4>
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2">
            <input type="checkbox" defaultChecked className="accent-up-green" />
            <span className="text-text-secondary">显示MA均线</span>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" defaultChecked className="accent-up-green" />
            <span className="text-text-secondary">显示MACD</span>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" defaultChecked className="accent-up-green" />
            <span className="text-text-secondary">显示买卖信号</span>
          </div>
        </div>
      </div>

      <div className="p-3">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">📋 辅助功能</h4>
        <div className="space-y-2 text-xs">
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">
            查看回测日志
          </button>
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">
            导出数据
          </button>
        </div>
      </div>
    </div>
  );
}

function SettingsSidebar() {
  const sections = [
    "账户设置",
    "交易成本",
    "指标参数",
    "风控规则",
    "高级选项",
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-2">
        {sections.map((section, index) => (
          <button
            key={section}
            className={`w-full text-left px-3 py-2 text-xs rounded transition-colors ${
              index === 0
                ? "bg-bg-primary text-text-primary font-medium"
                : "text-text-secondary hover:bg-bg-card"
            }`}
          >
            {index === 0 ? `[● ${section}]` : `[  ${section}]`}
          </button>
        ))}
      </div>
    </div>
  );
}
