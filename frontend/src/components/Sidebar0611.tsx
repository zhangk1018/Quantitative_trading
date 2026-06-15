import { type ViewType } from "./ViewTabs";
import { useState, useEffect, useRef } from "react";
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
  onMarketIndicatorRangesChange?: (ranges: Record<string, IndicatorRangeValue>) => void;
  onFinancialIndicatorRangesChange?: (ranges: Record<string, IndicatorRangeValue>) => void;
  conditionTree?: FilterTree;
  onConditionTreeChange?: (tree: FilterTree) => void;
  builderCollapsed?: boolean;
  onToggleBuilderCollapsed?: () => void;
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
  const groups = ["全部自选", "金融股", "科技股", "消费股", "自定义分组1"];

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
          <button className="w-full bg-up-green/10 border border-up-green/30 text-up-green text-xs px-3 py-2 rounded hover:bg-up-green/20 transition-colors">今日上涨</button>
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">今日下跌</button>
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">涨幅超5%</button>
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
  onMarketIndicatorRangesChange?: (ranges: Record<string, IndicatorRangeValue>) => void;
  onFinancialIndicatorRangesChange?: (ranges: Record<string, IndicatorRangeValue>) => void;
  conditionTree?: FilterTree;
  onConditionTreeChange?: (tree: FilterTree) => void;
  builderCollapsed?: boolean;
  onToggleBuilderCollapsed?: () => void;
  onStartScreener?: () => void;
}) {
  const [isRangeExpanded, setIsRangeExpanded] = useState(true);
  const [isMarketIndicatorsExpanded, setIsMarketIndicatorsExpanded] = useState(true);
  const [isFinancialExpanded, setIsFinancialExpanded] = useState(true);
  const [isTechnicalExpanded, setIsTechnicalExpanded] = useState(true);
  
  const [selectedMarketIndicators, setSelectedMarketIndicators] = useState<string[]>(["成交额"]);
  const [marketIndicatorRanges, setMarketIndicatorRanges] = useState<Record<string, { min?: number; max?: number }>>({});
  
  const [selectedFinancialIndicators, setSelectedFinancialIndicators] = useState<string[]>([]);
  const [financialIndicatorRanges, setFinancialIndicatorRanges] = useState<Record<string, { min?: number; max?: number }>>({});
  
  const [selectedTechnicalIndicators, setSelectedTechnicalIndicators] = useState<string[]>([]);
  const [technicalConfig, setTechnicalConfig] = useState<typeof DEFAULT_TECHNICAL_CONFIG>(
    () => ({
      MA: { conditions: DEFAULT_TECHNICAL_CONFIG.MA.conditions.map((c) => ({ ...c })) },
      MACD: { ...DEFAULT_TECHNICAL_CONFIG.MACD },
      BOLL: { ...DEFAULT_TECHNICAL_CONFIG.BOLL },
    })
  );
  const [activeTechDialog, setActiveTechDialog] = useState<TechnicalIndicator | null>(null);

  const listingChildOptions = ["上海主板", "深圳主板", "创业板", "科创板"];
  const allListingPlaces = [
    { label: "全部", value: "全部" },
    ...listingChildOptions.map(v => ({ label: v, value: v })),
  ];

  const [explicitAll, setExplicitAll] = useState(true);
  const [selectedChildren, setSelectedChildren] = useState<string[]>(() => [...listingChildOptions]);
  const allCheckboxRef = useRef<HTMLInputElement>(null);
  const [isListingPlacesOpen, setIsListingPlacesOpen] = useState(false);
  
  // 业务强制禁用状态
  const [allDisabled, setAllDisabled] = useState(false);
  const [selectedMarket, setSelectedMarket] = useState<"港股" | "美股" | "沪深">("沪深");
  const [selectedScope, setSelectedScope] = useState<"全部" | "仅看自选">("全部");

  // 🌟 核心修复：综合禁用状态（结合 allDisabled 和 股票范围）
  const isListingDisabled = allDisabled || selectedScope === "仅看自选";

  const MARKET_INDICATOR_FIELD_MAP: Record<string, { field: string; unit?: string } | null> = {
    "市值": { field: "circ_mv", unit: "万" }, "价格": { field: "close", unit: "元" },
    "涨跌幅": { field: "change_pct", unit: "%" }, "市盈率(静)": { field: "pe", unit: "倍" },
    "市盈率(TTM)": { field: "pe_ttm", unit: "倍" }, "市净率": { field: "pb", unit: "倍" },
    "量比": { field: "volume_ratio", unit: "倍" }, "成交额": { field: "amount", unit: "元" },
    "成交量": { field: "volume", unit: "手" }, "换手率": { field: "turnover_rate", unit: "%" },
  };

  const FINANCIAL_INDICATOR_FIELD_MAP: Record<string, { field: string; unit?: string } | null> = {
    "净利润": { field: "net_profit", unit: "元" }, "营业收入": { field: "revenue", unit: "元" },
    "净资产收益率": { field: "roe", unit: "%" },
  };

  const updateIndicatorRange = (ind: string, key: "min" | "max", value: string) => {
    setMarketIndicatorRanges((prev) => {
      const cur = prev[ind] || {};
      const next: { min?: number; max?: number } = { ...cur };
      if (value === "" || value === undefined) delete next[key];
      else { const num = Number(value); if (Number.isFinite(num)) next[key] = num; }
      if (Object.keys(next).length === 0) { const { [ind]: _, ...rest } = prev; return rest; }
      return { ...prev, [ind]: next };
    });
  };

  const updateFinancialRange = (ind: string, key: "min" | "max", value: string) => {
    setFinancialIndicatorRanges((prev) => {
      const cur = prev[ind] || {};
      const next: { min?: number; max?: number } = { ...cur };
      if (value === "" || value === undefined) delete next[key];
      else { const num = Number(value); if (Number.isFinite(num)) next[key] = num; }
      if (Object.keys(next).length === 0) { const { [ind]: _, ...rest } = prev; return rest; }
      return { ...prev, [ind]: next };
    });
  };

  useEffect(() => {
    const out: Record<string, IndicatorRangeValue> = {};
    for (const [label, range] of Object.entries(marketIndicatorRanges)) {
      const meta = MARKET_INDICATOR_FIELD_MAP[label]; if (!meta) continue; out[meta.field] = range;
    }
    onMarketIndicatorRangesChange?.(out);
  }, [marketIndicatorRanges, onMarketIndicatorRangesChange]);

  useEffect(() => {
    const out: Record<string, IndicatorRangeValue> = {};
    for (const [label, range] of Object.entries(financialIndicatorRanges)) {
      const meta = FINANCIAL_INDICATOR_FIELD_MAP[label]; if (!meta) continue; out[meta.field] = range;
    }
    onFinancialIndicatorRangesChange?.(out);
  }, [financialIndicatorRanges, onFinancialIndicatorRangesChange]);

  // 🌟 核心修复：重写联动逻辑，彻底解决状态脱节 Bug
  const toggleListingPlace = (place: string) => {
    if (isListingDisabled) return; // 禁用时彻底拦截

    if (place === "全部") {
      if (explicitAll) {
        // 当前是“全选”，点击后变成“全不选”
        setExplicitAll(false);
        setSelectedChildren([]);
      } else {
        // 当前是“半选”或“全不选”，点击后变成“全选”
        setExplicitAll(true);
        setSelectedChildren([...listingChildOptions]);
      }
    } else {
      const isCurrentlySelected = selectedChildren.includes(place);
      if (isCurrentlySelected) {
        // 取消子项：同时取消“显式全选”状态
        setSelectedChildren(selectedChildren.filter(c => c !== place));
        setExplicitAll(false);
      } else {
        // 选中子项：如果全满了，自动勾上“显式全选”
        const nextChildren = [...selectedChildren, place];
        setSelectedChildren(nextChildren);
        if (nextChildren.length === listingChildOptions.length) {
          setExplicitAll(true);
        } else {
          setExplicitAll(false);
        }
      }
    }
  };

  // 同步“半选”横线状态
  useEffect(() => {
    if (allCheckboxRef.current) {
      allCheckboxRef.current.indeterminate = !explicitAll && selectedChildren.length > 0;
    }
  }, [explicitAll, selectedChildren]);

  useEffect(() => {
    if (allDisabled) {
      setExplicitAll(true);
      setSelectedChildren([...listingChildOptions]);
    }
  }, [allDisabled, listingChildOptions]);

  const getDisplayText = () => {
    if (explicitAll || listingChildOptions.every(c => selectedChildren.includes(c))) return "全部";
    if (selectedChildren.length === 0) return "未选";
    if (selectedChildren.length <= 2) return selectedChildren.join(",");
    return `已选 ${selectedChildren.length}项`;
  };

  useEffect(() => {
    const handleClickOutside = () => { if (isListingPlacesOpen) setIsListingPlacesOpen(false); };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [isListingPlacesOpen]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="px-3 py-2 border-b border-border-color relative z-50">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-text-secondary font-semibold text-xs">范围(3)</h4>
            <button className="text-text-muted text-xs hover:text-text-primary transition-colors" onClick={() => setIsRangeExpanded(!isRangeExpanded)}>
              {isRangeExpanded ? "▼" : "▶"}
            </button>
          </div>

          {isRangeExpanded && (
            <>
              <div className="mb-2.5">
                <label className="block text-text-secondary mb-1.5 text-xs">所属市场</label>
                <div className="flex items-center gap-4">
                  {(["港股", "美股", "沪深"] as const).map(m => (
                    <label key={m} className={`flex items-center gap-2 cursor-pointer ${m !== "沪深" ? "opacity-50" : ""}`} title={m !== "沪深" ? "暂无数据" : ""}>
                      <input type="radio" name="market" checked={selectedMarket === m} onChange={() => setSelectedMarket(m)} className="accent-up-green" />
                      <span className="text-text-primary text-xs">{m}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="mb-2.5">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-text-secondary text-xs">上市地</label>
                  <div className="relative">
                    <button
                      className={`bg-bg-card border border-border-color text-text-primary text-xs px-2 py-1 rounded flex items-center gap-2 ${isListingDisabled ? 'opacity-40 cursor-not-allowed' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isListingDisabled) setIsListingPlacesOpen(!isListingPlacesOpen);
                      }}
                      disabled={isListingDisabled}
                    >
                      <span>{getDisplayText()}</span>
                      <span className="text-text-muted">▼</span>
                    </button>

                    {isListingPlacesOpen && !isListingDisabled && (
                      <div className="absolute z-[60] mt-1 right-0 bg-bg-card border border-border-color rounded shadow-lg w-48" onClick={(e) => e.stopPropagation()}>
                        {allListingPlaces.map((place) => {
                          const isChecked = place.value === "全部" ? explicitAll : selectedChildren.includes(place.value);
                          return (
                            <label
                              key={place.value}
                              className={`flex items-center gap-2 px-3 py-2 ${
                                isListingDisabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-bg-primary cursor-pointer'
                              }`}
                              onClick={(e) => {
                                // 🌟 彻底阻断禁用状态下的事件穿透
                                if (isListingDisabled) {
                                  e.preventDefault();
                                  e.stopPropagation();
                                }
                              }}
                            >
                              <input
                                type="checkbox"
                                ref={place.value === "全部" ? allCheckboxRef : null}
                                checked={isChecked}
                                onChange={() => toggleListingPlace(place.value)}
                                className="accent-up-green"
                                disabled={isListingDisabled}
                              />
                              <span className="text-text-primary text-xs">{place.label}</span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="mb-1">
                <div className="flex items-center gap-4">
                  <label className="text-text-secondary text-xs">股票范围</label>
                  <div className="flex items-center gap-2">
                    {(["全部", "仅看自选"] as const).map(s => (
                      <label key={s} className="flex items-center gap-2 cursor-pointer">
                        <input type="radio" name="stockScope" checked={selectedScope === s} onChange={() => setSelectedScope(s)} className="accent-up-green" />
                        <span className="text-text-primary text-xs">{s}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* 行情指标 */}
        <div className="border-b border-border-color">
          <div className="px-3 py-1.5 flex items-center justify-between">
            <h4 className="text-text-secondary text-xs font-semibold">行情指标({selectedMarketIndicators.length})</h4>
            <button className="text-text-muted text-xs hover:text-text-primary transition-colors" onClick={() => setIsMarketIndicatorsExpanded(!isMarketIndicatorsExpanded)}>
              {isMarketIndicatorsExpanded ? "▼" : "▶"}
            </button>
          </div>
          {isMarketIndicatorsExpanded && (
            <div className="px-3 pb-2">
              <div className="grid grid-cols-2 gap-1.5">
                {Object.keys(MARKET_INDICATOR_FIELD_MAP).map((ind) => {
                  const selected = selectedMarketIndicators.includes(ind);
                  const disabled = MARKET_INDICATOR_FIELD_MAP[ind] === null;
                  return (
                    <button key={ind} onClick={() => { if (!disabled) setSelectedMarketIndicators(prev => prev.includes(ind) ? prev.filter(x => x !== ind) : [...prev, ind]); }}
                      title={disabled ? "暂缺数据字段" : (selected ? "点击取消" : "点击添加范围筛选")}
                      className={`text-xs px-2 py-1.5 rounded transition-colors ${disabled ? "bg-bg-card border border-border-color text-text-muted opacity-40 cursor-not-allowed" : selected ? "bg-up-green text-white" : "bg-bg-card border border-border-color text-text-secondary hover:bg-bg-secondary"}`}>
                      {ind}
                    </button>
                  );
                })}
              </div>
              {selectedMarketIndicators.length > 0 && (
                <div className="mt-2 space-y-1.5" data-testid="indicator-ranges">
                  <div className="text-text-muted text-xs">📊 范围条件：</div>
                  {selectedMarketIndicators.map((ind) => {
                    const meta = MARKET_INDICATOR_FIELD_MAP[ind]; if (!meta) return null;
                    const range = marketIndicatorRanges[ind] || {};
                    return (
                      <div key={ind} className="flex items-center gap-1.5" data-testid={`range-${ind}`}>
                        <span className="text-text-secondary text-xs w-20 truncate" title={ind}>{ind}({meta.unit || ''})</span>
                        <input type="number" inputMode="decimal" value={range.min ?? ""} placeholder="min" onChange={(e) => updateIndicatorRange(ind, "min", e.target.value)} className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded" />
                        <span className="text-text-muted text-xs">~</span>
                        <input type="number" inputMode="decimal" value={range.max ?? ""} placeholder="max" onChange={(e) => updateIndicatorRange(ind, "max", e.target.value)} className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded" />
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
            <button className="text-text-muted text-xs hover:text-text-primary transition-colors" onClick={() => setIsFinancialExpanded(!isFinancialExpanded)}>
              {isFinancialExpanded ? "▼" : "▶"}
            </button>
          </div>
          {isFinancialExpanded && (
            <div className="px-3 pb-2">
              <div className="grid grid-cols-2 gap-1.5">
                {Object.keys(FINANCIAL_INDICATOR_FIELD_MAP).map((ind) => {
                  const selected = selectedFinancialIndicators.includes(ind);
                  const disabled = FINANCIAL_INDICATOR_FIELD_MAP[ind] === null;
                  return (
                    <button key={ind} onClick={() => { if (!disabled) setSelectedFinancialIndicators(prev => prev.includes(ind) ? prev.filter(x => x !== ind) : [...prev, ind]); }}
                      title={disabled ? "暂缺数据字段" : (selected ? "点击取消" : "点击添加范围筛选")}
                      className={`text-xs px-2 py-1.5 rounded transition-colors ${disabled ? "bg-bg-card border border-border-color text-text-muted opacity-40 cursor-not-allowed" : selected ? "bg-up-green text-white" : "bg-bg-card border border-border-color text-text-secondary hover:bg-bg-secondary"}`}>
                      {ind}
                    </button>
                  );
                })}
              </div>
              {selectedFinancialIndicators.length > 0 && (
                <div className="mt-2 space-y-1.5" data-testid="financial-indicator-ranges">
                  <div className="text-text-muted text-xs">📊 范围条件：</div>
                  {selectedFinancialIndicators.map((ind) => {
                    const meta = FINANCIAL_INDICATOR_FIELD_MAP[ind]; if (!meta) return null;
                    const range = financialIndicatorRanges[ind] || {};
                    return (
                      <div key={ind} className="flex items-center gap-1.5" data-testid={`financial-range-${ind}`}>
                        <span className="text-text-secondary text-xs w-20 truncate" title={ind}>{ind}({meta.unit || ''})</span>
                        <input type="number" inputMode="decimal" value={range.min ?? ""} placeholder="min" onChange={(e) => updateFinancialRange(ind, "min", e.target.value)} className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded" />
                        <span className="text-text-muted text-xs">~</span>
                        <input type="number" inputMode="decimal" value={range.max ?? ""} placeholder="max" onChange={(e) => updateFinancialRange(ind, "max", e.target.value)} className="w-16 bg-bg-card border border-border-color text-text-primary text-xs px-1.5 py-1 rounded" />
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
            <button className="text-text-muted text-xs hover:text-text-primary transition-colors" onClick={() => setIsTechnicalExpanded(!isTechnicalExpanded)}>
              {isTechnicalExpanded ? "▼" : "▶"}
            </button>
          </div>
          {isTechnicalExpanded && (
            <div className="px-3 pb-2">
              <div className="grid grid-cols-2 gap-1.5">
                {(["MA", "MACD", "BOLL"] as const).map((ind) => {
                  const selected = selectedTechnicalIndicators.includes(ind);
                  return (
                    <button key={ind} onClick={() => setActiveTechDialog(ind)} title={selected ? "已添加，点击修改配置" : "点击配置并添加筛选"}
                      className={`text-xs px-2 py-1.5 rounded transition-colors ${selected ? "bg-up-green text-white" : "bg-bg-card border border-border-color text-text-secondary hover:bg-bg-secondary"}`}>
                      {ind}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {conditionTree && onConditionTreeChange && (
          <div className="border-b border-border-color">
            <ConditionBuilder tree={conditionTree} onChange={onConditionTreeChange} collapsed={builderCollapsed ?? false} onToggleCollapsed={onToggleBuilderCollapsed} />
          </div>
        )}

        <div className="px-3 py-2 border-b border-border-color">
          <h4 className="text-text-secondary text-xs mb-1.5 font-semibold">⚖️ 因子打分配置</h4>
          <div className="space-y-1.5 text-xs">
            {[{l: "换手率", v: 30}, {l: "MA趋势", v: 40}, {l: "成交量", v: 30}].map(i => (
              <div key={i.l}>
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-text-secondary">{i.l}</span>
                  <span className="text-text-primary">{i.v}%</span>
                </div>
                <input type="range" defaultValue={i.v} className="w-full accent-up-green" />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="px-3 py-2 border-t border-border-color flex-shrink-0 bg-bg-secondary flex items-center gap-2">
        <button onClick={onStartScreener} className="flex-1 bg-up-green text-white text-sm font-medium px-4 py-2 rounded hover:opacity-90 transition-opacity">▶ 开始选股</button>
      </div>

      {activeTechDialog && (
        <TechnicalIndicatorDialog
          indicator={activeTechDialog}
          initialConfig={technicalConfig[activeTechDialog]}
          onConfirm={(config: IndicatorConfig) => {
            setTechnicalConfig((prev) => ({ ...prev, [activeTechDialog]: config as typeof prev[typeof activeTechDialog] }));
            setSelectedTechnicalIndicators((prev) => prev.includes(activeTechDialog) ? prev : [...prev, activeTechDialog]);
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
          <div className="flex items-center gap-2 text-text-primary"><input type="radio" name="backtest-stock" defaultChecked className="accent-up-green" /><span>000001 平安银行</span></div>
          <div className="flex items-center gap-2 text-text-primary"><input type="radio" name="backtest-stock" className="accent-up-green" /><span>000002 万科A</span></div>
        </div>
        <button className="w-full mt-3 bg-bg-card border border-border-color text-text-primary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">[+ 添加标的]</button>
      </div>
      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">📅 时间周期</h4>
        <div className="space-y-2 text-xs">
          <div className="flex gap-1">
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">1分</button>
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">5分</button>
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">15分</button>
          </div>
          <div className="flex gap-1">
            <button className="flex-1 bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-secondary transition-colors">1小时</button>
            <button className="flex-1 bg-up-green text-white text-xs px-2 py-1 rounded">日线</button>
          </div>
        </div>
      </div>
      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">⚙️ 策略控制</h4>
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2"><input type="checkbox" defaultChecked className="accent-up-green" /><span className="text-text-secondary">启用策略</span></div>
          <div className="flex items-center gap-2"><input type="checkbox" className="accent-up-green" /><span className="text-text-secondary">仅查看K线</span></div>
          <button className="w-full mt-2 bg-up-green text-white text-xs font-medium px-3 py-2 rounded hover:opacity-90 transition-opacity">▶ 重新回测</button>
        </div>
      </div>
      <div className="p-3 border-b border-border-color">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">📊 图表显示</h4>
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2"><input type="checkbox" defaultChecked className="accent-up-green" /><span className="text-text-secondary">显示MA均线</span></div>
          <div className="flex items-center gap-2"><input type="checkbox" defaultChecked className="accent-up-green" /><span className="text-text-secondary">显示MACD</span></div>
          <div className="flex items-center gap-2"><input type="checkbox" defaultChecked className="accent-up-green" /><span className="text-text-secondary">显示买卖信号</span></div>
        </div>
      </div>
      <div className="p-3">
        <h4 className="text-text-secondary text-xs mb-3 font-semibold">📋 辅助功能</h4>
        <div className="space-y-2 text-xs">
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">查看回测日志</button>
          <button className="w-full bg-bg-card border border-border-color text-text-secondary text-xs px-3 py-2 rounded hover:bg-bg-secondary transition-colors">导出数据</button>
        </div>
      </div>
    </div>
  );
}

function SettingsSidebar() {
  const sections = ["账户设置", "交易成本", "指标参数", "风控规则", "高级选项"];
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-2">
        {sections.map((section, index) => (
          <button key={section} className={`w-full text-left px-3 py-2 text-xs rounded transition-colors ${index === 0 ? "bg-bg-primary text-text-primary font-medium" : "text-text-secondary hover:bg-bg-card"}`}>
            {index === 0 ? `[● ${section}]` : `[  ${section}]`}
          </button>
        ))}
      </div>
    </div>
  );
}