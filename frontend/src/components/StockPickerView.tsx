/**
 * StockPickerView.tsx - 选股视图
 *
 * Phase 6: 选股策略保存/加载
 * Phase 4.4.1 (2026-06-10): 接入真实 API
 * - 顶部工具栏：[💾保存策略] [📂我的策略]
 * - 筛选条件 state 化
 * - 集成 fetchStocks + fetchMeta 拉真实数据
 * - 集成 StrategyManager 抽屉
 *
 * Phase 6.1.a：条件构建器已从本视图顶部移入左侧功能区（Sidebar）
 * Phase 6.1.d：底部"加入回测列表/添加自选/刷新"已移至右下角浮动工具条
 *
 * 数据源：
 * - 列表：GET /api/stocks/?sort_by=...&sort_asc=...&offset=...&limit=...&as_of_date=...
 * - 元数据：GET /api/meta/（获取 trade_date）
 */

import { useState, useMemo } from 'react';
import type { ScreenerFilters, StockResponse } from '../types';
import { flattenFilters } from './ConditionBuilder';
import StrategyManager from './StrategyManager';
import type { IndicatorRangeValue } from './Sidebar';

interface StockPickerViewProps {
  selectedCode?: string | null;
  onSelectCode?: (code: string) => void;
  // 行情/财务指标范围（来自 Sidebar，App.tsx 中转）
  marketIndicatorRanges?: Record<string, IndicatorRangeValue>;
  financialIndicatorRanges?: Record<string, IndicatorRangeValue>;
  // 数据状态（由 App.tsx 拉取并传入）
  stocks: StockResponse[];
  loading: boolean;
  error: string | null;
  tradeDate: string;
  total: number;
  filters: ScreenerFilters;
  onFiltersChange: (next: ScreenerFilters) => void;
  onRefresh: () => void;
  // 条件树（用于标题"筛选条件: N 个"徽章 + 综合得分联动）
  conditionTree: import('./ConditionBuilder').FilterTree;
}

export default function StockPickerView({
  onSelectCode,
  stocks,
  loading,
  error,
  tradeDate,
  total,
  filters,
  onFiltersChange,
  onRefresh,
  conditionTree,
}: StockPickerViewProps) {
  const [managerOpen, setManagerOpen] = useState(false);
  // 表格多选状态：用于底部"选中: ..."展示 + 4 个批量操作按钮
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());

  // 切换单只股票的选中状态
  const toggleSelect = (code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedCodes.size === stocks.length) {
      setSelectedCodes(new Set());
    } else {
      setSelectedCodes(new Set(stocks.map((s) => s.stock_code)));
    }
  };

  // 选中股票的详细信息列表（按 stocks 顺序）
  const selectedStocks = stocks.filter((s) => selectedCodes.has(s.stock_code));

  // 当前已选条件数（用于顶部"筛选条件: N 个"徽章）
  const conditionCount = useMemo(
    () => flattenFilters(conditionTree).totalConditions,
    [conditionTree]
  );

  /**
   * 综合得分（0~100）
   * 简化公式：基础分 50 + 涨跌幅(±20%) + 换手率 + MA趋势
   *   涨跌幅权重最大：1% 涨 → +2 分
   *   换手率：1% 换手 → +0.3 分
   *   MA 趋势：1% 偏离 → +0.3 分
   * 命中"形态识别/突破信号/连续走势"条件：每个 +5 分
   */
  const computeScore = (s: StockResponse): number => {
    const change = s.change_pct ?? 0;
    const turnover = s.turnover_rate ?? 0;
    const maTrend = s.close && s.ma20 ? ((s.close - s.ma20) / s.ma20) * 100 : 0;
    let score = 50 + change * 2 + turnover * 0.3 + maTrend * 0.3;
    if (s.break_high_20) score += 3;
    if (s.break_high_60) score += 5;
    if (s.break_high_120) score += 7;
    if (s.break_high_250) score += 10;
    if (s.consec_up_3) score += 1;
    if (s.consec_up_5) score += 2;
    return Math.max(0, Math.min(100, score));
  };

  const handleTopNChange = (n: number) => {
    onFiltersChange({ ...filters, topN: n });
  };

  const handleSortChange = (sortBy: string) => {
    onFiltersChange({ ...filters, sortBy });
  };

  // 行内字段渲染辅助
  const renderTurnover = (s: StockResponse) => {
    const v = s.turnover_rate;
    if (v === null || v === undefined) return '-';
    return v.toFixed(2);
  };
  const renderMaTrend = (s: StockResponse) => {
    if (s.close === null || s.close === undefined) return '-';
    if (s.ma20 === null || s.ma20 === undefined) return '-';
    return (((s.close - s.ma20) / s.ma20) * 100).toFixed(2);
  };
  const renderVolume = (s: StockResponse) => {
    if (s.volume === null || s.volume === undefined) return '-';
    return (s.volume / 10000).toFixed(1);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-color bg-bg-secondary">
        <div className="flex items-center gap-3">
          <h3 className="text-text-primary font-medium text-base">因子综合排名 Top {filters.topN}</h3>
          {/* 筛选条件徽章（与条件构建器联动） */}
          <span
            data-testid="condition-count-badge"
            className={`text-xs px-2 py-0.5 rounded border ${
              conditionCount > 0
                ? 'text-up-green border-up-green/40 bg-up-green/5'
                : 'text-text-muted border-border-color'
            }`}
          >
            筛选条件: {conditionCount} 个
          </span>
          <span className="text-text-muted text-xs">
            {loading
              ? '加载中…'
              : error
                ? `加载失败：${error}`
                : `共 ${total.toLocaleString()} 只（截至 ${tradeDate || '—'}）`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filters.sortBy}
            onChange={(e) => handleSortChange(e.target.value)}
            className="bg-bg-card border border-border-color text-text-primary text-xs px-2 py-1.5 rounded focus:outline-none focus:border-up-green"
            disabled={loading}
          >
            <option value="score">综合得分</option>
            <option value="turnover">换手率</option>
            <option value="maTrend">MA趋势</option>
            <option value="volume">成交量</option>
          </select>

          <button
            onClick={() =>
              onFiltersChange({
                ...filters,
                sortOrder: filters.sortOrder === 'asc' ? 'desc' : 'asc',
              })
            }
            className="bg-bg-card border border-border-color text-text-primary text-xs px-2.5 py-1.5 rounded hover:bg-bg-primary transition-colors"
            title="切换升降序"
            disabled={loading}
          >
            {filters.sortOrder === 'asc' ? '↑ 升序' : '↓ 降序'}
          </button>

          <select
            value={filters.topN}
            onChange={(e) => handleTopNChange(Number(e.target.value))}
            className="bg-bg-card border border-border-color text-text-primary text-xs px-2 py-1.5 rounded focus:outline-none focus:border-up-green"
            disabled={loading}
          >
            {[10, 20, 50, 100].map((n) => (
              <option key={n} value={n}>
                Top {n}
              </option>
            ))}
          </select>

          <div className="w-px h-5 bg-border-color mx-1" />

          <button
            onClick={() => setManagerOpen(true)}
            data-action="open-manager"
            className="flex items-center gap-1.5 bg-bg-card border border-up-green/40 text-up-green text-xs px-3 py-1.5 rounded hover:bg-up-green/10 hover:border-up-green transition-colors"
            title="打开策略管理"
          >
            <span>💾</span>保存策略
          </button>

          <button
            onClick={() => setManagerOpen(true)}
            data-action="open-manager"
            className="flex items-center gap-1.5 bg-up-green text-white text-xs px-3 py-1.5 rounded hover:opacity-90 transition-opacity"
            title="加载/管理策略"
          >
            <span>📂</span>我的策略
          </button>
        </div>
      </div>

      {/* 表格区 */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-auto">
          {error ? (
            <div className="p-8 text-center">
              <p className="text-down-red text-sm mb-2">加载失败</p>
              <p className="text-text-muted text-xs">{error}</p>
              <button
                onClick={onRefresh}
                className="mt-3 bg-bg-card border border-border-color text-text-primary text-xs px-3 py-1.5 rounded hover:bg-bg-primary"
              >
                重试
              </button>
            </div>
          ) : stocks.length === 0 && !loading ? (
            <div className="p-8 text-center text-text-muted text-sm">暂无数据</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-secondary border-b border-border-color">
                <tr>
                  <th className="px-3 py-3 w-8">
                    <input
                      type="checkbox"
                      checked={stocks.length > 0 && selectedCodes.size === stocks.length}
                      ref={(el) => {
                        if (el) el.indeterminate = selectedCodes.size > 0 && selectedCodes.size < stocks.length;
                      }}
                      onChange={toggleSelectAll}
                      className="accent-up-green cursor-pointer"
                      title="全选/取消全选"
                    />
                  </th>
                  <th className="text-left px-2 py-3 text-text-muted font-medium">排名</th>
                  <th className="text-left px-2 py-3 text-text-muted font-medium">代码</th>
                  <th className="text-left px-2 py-3 text-text-muted font-medium">名称</th>
                  <th className="text-right px-2 py-3 text-text-muted font-medium" data-testid="th-score">综合得分</th>
                  <th className="text-right px-2 py-3 text-text-muted font-medium">换手率%</th>
                  <th className="text-right px-2 py-3 text-text-muted font-medium">MA趋势%</th>
                  <th className="text-right px-2 py-3 text-text-muted font-medium">成交量(万手)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color/50">
                {stocks.map((stock, idx) => (
                  <tr
                    key={stock.stock_code}
                    className={`hover:bg-bg-card transition-colors cursor-pointer ${
                      selectedCodes.has(stock.stock_code) ? 'bg-up-green/5' : ''
                    }`}
                    onClick={() => onSelectCode?.(stock.stock_code)}
                    title="点击查看详情"
                  >
                    <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedCodes.has(stock.stock_code)}
                        onChange={() => toggleSelect(stock.stock_code)}
                        className="accent-up-green cursor-pointer"
                      />
                    </td>
                    <td className="px-2 py-3 text-text-primary">{idx + 1}</td>
                    <td className="px-2 py-3 text-blue-400 hover:underline">{stock.stock_code}</td>
                    <td className="px-2 py-3 text-text-primary">{stock.stock_name}</td>
                    <td
                      className={`px-2 py-3 font-mono text-right ${
                        computeScore(stock) >= 70
                          ? 'text-up-green font-semibold'
                          : computeScore(stock) <= 30
                            ? 'text-down-red'
                            : 'text-text-primary'
                      }`}
                      data-testid="td-score"
                    >
                      {computeScore(stock).toFixed(1)}
                    </td>
                    <td
                      className={`px-2 py-3 font-mono text-right ${
                        (stock.turnover_rate ?? 0) > 7 ? 'text-up-green' : 'text-text-primary'
                      }`}
                    >
                      {renderTurnover(stock)}
                    </td>
                    <td
                      className={`px-2 py-3 font-mono text-right ${
                        Number(renderMaTrend(stock)) > 2 ? 'text-up-green' : 'text-text-primary'
                      }`}
                    >
                      {renderMaTrend(stock)}
                    </td>
                    <td className="px-2 py-3 font-mono text-right text-text-primary">
                      {renderVolume(stock)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 固定底部：4 个批量操作按钮 + 选中信息 */}
      <div className="border-t border-border-color bg-bg-secondary flex-shrink-0">
        <div className="px-4 py-2.5 flex items-center gap-2 flex-wrap">
          <button
            disabled={selectedStocks.length === 0}
            data-testid="add-to-backtest"
            className="bg-up-green text-white text-xs px-3 py-1.5 rounded hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            加入回测列表
          </button>
          <button
            disabled={selectedStocks.length === 0}
            data-testid="add-to-watchlist"
            className="bg-bg-card border border-border-color text-text-primary text-xs px-3 py-1.5 rounded hover:bg-bg-primary transition-colors disabled:opacity-50"
          >
            添加自选
          </button>
          <button
            disabled={stocks.length === 0}
            data-testid="export-result"
            className="bg-bg-card border border-border-color text-text-primary text-xs px-3 py-1.5 rounded hover:bg-bg-primary transition-colors disabled:opacity-50"
          >
            导出结果
          </button>
          <button
            disabled={selectedStocks.length === 0}
            data-testid="add-to-blacklist"
            className="bg-bg-card border border-border-color text-text-primary text-xs px-3 py-1.5 rounded hover:bg-bg-primary transition-colors disabled:opacity-50"
          >
            加入黑名单
          </button>

          <div className="w-px h-5 bg-border-color mx-1" />

          <button
            onClick={onRefresh}
            disabled={loading}
            data-testid="refresh-stocks"
            className="bg-bg-card border border-border-color text-text-primary text-xs px-3 py-1.5 rounded hover:bg-bg-primary transition-colors disabled:opacity-50"
          >
            刷新
          </button>

          {/* 选中信息 */}
          <div className="flex-1 min-w-0 ml-2 text-xs text-text-muted truncate" data-testid="selected-info">
            {selectedStocks.length === 0 ? (
              <span>未选中（点击行查看详情，勾选复选框多选）</span>
            ) : (
              <span>
                <span className="text-up-green font-medium">选中 ({selectedStocks.length}):</span>{' '}
                {selectedStocks
                  .map((s) => `${s.stock_code} ${s.stock_name}`)
                  .join('  ')}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 策略管理抽屉 */}
      <StrategyManager
        isOpen={managerOpen}
        onClose={() => setManagerOpen(false)}
        onLoad={(strategy) => onFiltersChange(strategy.filters)}
        currentFilters={filters}
        onSaveCurrent={() => {
          // 已在 StrategyManager 内部写入 storage
        }}
      />
    </div>
  );
}
