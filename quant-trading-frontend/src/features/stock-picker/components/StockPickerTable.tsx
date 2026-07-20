import React, { memo, useRef, useCallback } from 'react';
import { Typography, Spin, Checkbox, Button } from 'antd';
import { LoadingOutlined, CaretUpOutlined, CaretDownOutlined } from '@ant-design/icons';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useSettings } from '@/shared/contexts/SettingsContext';
import { formatMarketCap, formatAmount, formatNumber } from '../utils/screener';
import type { StockItem } from '../types';

const { Text } = Typography;

// ==================== 常量 ====================
const ROW_HEIGHT = 36; // py-2 (8+8) + 单行文字高度
const OVERSCAN = 5;
/** 距底部 N 条时自动触发加载更多 */
const LOAD_MORE_THRESHOLD = 5;

// ==================== 表格行 ====================
interface TableRowProps {
  stock: StockItem;
  index: number;
  selected: boolean;
  onToggle: (code: string) => void;
  onDoubleClick?: (stock: StockItem) => void;
}

const TableRow = memo(({ stock, index, selected, onToggle, onDoubleClick }: TableRowProps) => {
  const { colors } = useSettings();
  const changePct = Number(stock.change_pct) || 0;
  const isUp = changePct >= 0;
  const color = isUp ? colors.up : colors.down;

  return (
    <tr
      className={`border-b border-border-color hover:bg-bg-panel/60 transition-colors cursor-pointer ${
        selected ? 'bg-color-accent/10' : ''
      }`}
      onDoubleClick={() => onDoubleClick?.(stock)}
      style={{ height: ROW_HEIGHT }}
    >
      <td className="px-3 py-2 text-center">
        <Checkbox
          checked={selected}
          onChange={() => onToggle(stock.stock_code)}
          data-testid={`row-checkbox-${stock.stock_code}`}
        />
      </td>
      <td className="px-3 py-2 text-center text-text-secondary text-xs">{index + 1}</td>
      <td className="px-3 py-2 text-text-primary font-mono">{stock.stock_code}</td>
      <td className="px-3 py-2 text-text-primary">{stock.stock_name}</td>
      <td className="px-3 py-2 text-right font-mono" style={{ color }}>
        {formatNumber(stock.close)}
      </td>
      <td className="px-3 py-2 text-right font-mono" style={{ color }}>
        {isUp ? '+' : ''}{changePct.toFixed(2)}%
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatNumber(stock.turnover_rate)}%
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatNumber(stock.pe ?? stock.pe_ttm)}
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatNumber(stock.pb)}
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatMarketCap(stock.market_cap)}
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatAmount(stock.amount)}
      </td>
      <td className="px-3 py-2 text-center">
        {stock.listed_board && (
          <span className="text-xs px-1.5 py-0.5 bg-bg-card text-text-secondary rounded">
            {stock.listed_board}
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-center">
        {stock.patterns && stock.patterns.length > 0 ? (
          <div className="flex gap-1 justify-center flex-wrap">
            {stock.patterns.slice(0, 2).map((p, i) => (
              <span key={i} className="text-xs px-1.5 py-0.5 bg-color-accent/20 text-color-accent rounded">
                {p}
              </span>
            ))}
            {stock.patterns.length > 2 && (
              <span className="text-xs text-text-secondary">+{stock.patterns.length - 2}</span>
            )}
          </div>
        ) : (
          <span className="text-text-secondary text-xs">-</span>
        )}
      </td>
    </tr>
  );
});
TableRow.displayName = 'TableRow';

// ==================== 排序表头 ====================
interface SortableHeaderProps {
  label: string;
  column: string;
  sortBy: string;
  sortAsc: boolean;
  onSort: (column: string) => void;
}

const SortableHeader = memo(({ label, column, sortBy, sortAsc, onSort }: SortableHeaderProps) => {
  const isActive = sortBy === column;
  return (
    <th
      data-testid={`sort-${column}`}
      className={`px-3 py-2 text-right cursor-pointer select-none hover:text-text-primary transition-colors ${
        isActive ? 'text-color-accent' : ''
      }`}
      onClick={() => onSort(column)}
      title="点击排序"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive ? (
          sortAsc ? <CaretUpOutlined style={{ fontSize: 10 }} /> : <CaretDownOutlined style={{ fontSize: 10 }} />
        ) : (
          <span style={{ display: 'inline-block', width: 10 }} />
        )}
      </span>
    </th>
  );
});
SortableHeader.displayName = 'SortableHeader';

// ==================== 表格组件 ====================
interface StockPickerTableProps {
  items: StockItem[];
  total: number;
  loading: boolean;
  loadingMore: boolean;
  pageSize: number;
  selectedCodes: Set<string>;
  indeterminate: boolean;
  allSelected: boolean;
  sortBy: string;
  sortAsc: boolean;
  error: string | null;
  loadMoreError: string | null;
  onToggleAll: () => void;
  onToggleOne: (code: string) => void;
  onSort: (column: string) => void;
  onDoubleClick: (stock: StockItem) => void;
  onLoadMore: () => void;
  onRetry: () => void;
  onRetryLoadMore: () => void;
  scrollContainerRef: React.Ref<HTMLDivElement>;
}

/**
 * 选股结果表格（虚拟滚动）
 *
 * 使用 @tanstack/react-virtual 仅渲染可视区域行，支持大数据量流畅滚动。
 * 距底部 LOAD_MORE_THRESHOLD 条时自动触发加载更多。
 * 加载中 / 错误 / 空数据 / 加载更多错误 四种状态均在表格区域展示。
 */
export const StockPickerTable: React.FC<StockPickerTableProps> = React.memo(({
  items, total, loading, loadingMore, pageSize,
  selectedCodes, indeterminate, allSelected,
  sortBy, sortAsc, error, loadMoreError,
  onToggleAll, onToggleOne, onSort, onDoubleClick, onLoadMore, onRetry, onRetryLoadMore,
  scrollContainerRef,
}) => {
  // 防止 onChange 中重复触发 loadMore
  const loadMoreTriggeredRef = useRef(false);
  // 用 ref 保存 onChange 所需的动态值，避免 useCallback 循环依赖 virtualizer
  const stateRef = useRef({ itemsLen: items.length, total, loadingMore, loadMoreError, onLoadMore });
  stateRef.current = { itemsLen: items.length, total, loadingMore, loadMoreError, onLoadMore };

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => {
      if (typeof scrollContainerRef === 'function') return null;
      return scrollContainerRef?.current ?? null;
    },
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
    onChange: useCallback(
      () => {
        const endIndex = virtualizerRef.current?.range?.endIndex ?? 0;
        const { itemsLen, total: t, loadingMore: lm, loadMoreError: lme, onLoadMore: olm } = stateRef.current;
        if (
          endIndex >= itemsLen - LOAD_MORE_THRESHOLD &&
          itemsLen < t &&
          !lm &&
          !lme &&
          !loadMoreTriggeredRef.current
        ) {
          loadMoreTriggeredRef.current = true;
          olm();
        }
      },
      [],
    ),
  });

  // 通过 ref 访问 virtualizer（避免 onChange 循环依赖）
  const virtualizerRef = useRef(virtualizer);
  virtualizerRef.current = virtualizer;

  // 重置自动触发标记（当 items 变化时说明加载完成）
  const prevItemsLenRef = useRef(items.length);
  if (items.length !== prevItemsLenRef.current) {
    prevItemsLenRef.current = items.length;
    loadMoreTriggeredRef.current = false;
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-secondary bg-bg-base/50 overflow-auto">
        <div className="flex flex-col items-center gap-2">
          <Spin indicator={<LoadingOutlined spin />} size="large" />
          <Text className="text-text-secondary text-sm">正在加载数据...</Text>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base/50 overflow-auto">
        <div className="flex flex-col items-center gap-3">
          <Text className="text-red-500">{error}</Text>
          <Button onClick={onRetry}>重试</Button>
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base/50 overflow-auto">
        <Text className="text-text-secondary">暂无数据，请先设置筛选条件并点击"开始选股"</Text>
      </div>
    );
  }

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <div ref={scrollContainerRef} className="flex-1 bg-bg-base/50 overflow-auto">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 z-10 bg-bg-panel">
          <tr className="text-text-secondary text-xs border-b border-border-color">
            <th className="px-3 py-2 text-center w-12">
              <Checkbox
                indeterminate={indeterminate}
                checked={allSelected}
                onChange={onToggleAll}
                data-testid="select-all-checkbox"
              />
            </th>
            <th className="px-3 py-2 text-center text-text-secondary text-xs">#</th>
            <th className="px-3 py-2 text-left">代码</th>
            <th className="px-3 py-2 text-left">名称</th>
            <th className="px-3 py-2 text-right">收盘价</th>
            <SortableHeader label="涨跌幅" column="change_pct" sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
            <SortableHeader label="换手率" column="turnover_rate" sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
            <SortableHeader label="市盈率" column="pe" sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
            <th className="px-3 py-2 text-right">市净率</th>
            <SortableHeader label="总市值" column="market_cap" sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
            <SortableHeader label="成交额" column="amount" sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
            <th className="px-3 py-2 text-center">板块</th>
            <th className="px-3 py-2 text-center" style={{ minWidth: 100 }}>K线形态</th>
          </tr>
        </thead>
        <tbody>
          {/* 顶部占位：已滚过的行 */}
          {virtualItems.length > 0 && virtualItems[0].start > 0 && (
            <tr>
              <td colSpan={13} style={{ height: virtualItems[0].start, padding: 0, border: 0 }} />
            </tr>
          )}
          {virtualItems.map((virtualRow) => {
            const stock = items[virtualRow.index];
            return (
              <TableRow
                key={virtualRow.key}
                stock={stock}
                index={virtualRow.index}
                selected={selectedCodes.has(stock.stock_code)}
                onToggle={onToggleOne}
                onDoubleClick={onDoubleClick}
              />
            );
          })}
          {/* 底部占位：尚未渲染的行 */}
          {virtualItems.length > 0 && virtualItems[virtualItems.length - 1].end < totalSize && (
            <tr>
              <td colSpan={13} style={{ height: totalSize - virtualItems[virtualItems.length - 1].end, padding: 0, border: 0 }} />
            </tr>
          )}
        </tbody>
      </table>
      {/* 加载更多区域 */}
      {items.length < total && (
        <div className="flex flex-col items-center py-4 gap-2">
          {loadMoreError ? (
            <div className="flex items-center gap-2">
              <Text className="text-red-500 text-sm">{loadMoreError}</Text>
              <Button size="small" onClick={onRetryLoadMore} data-testid="retry-load-more-btn">
                重试
              </Button>
            </div>
          ) : (
            <Button
              type="dashed"
              icon={loadingMore ? <LoadingOutlined spin /> : undefined}
              onClick={onLoadMore}
              disabled={loadingMore}
              className="w-48"
              data-testid="load-more-btn"
            >
              {loadingMore ? '加载中...' : `加载更多（${Math.min(pageSize, total - items.length)} 只）`}
            </Button>
          )}
        </div>
      )}
    </div>
  );
});
StockPickerTable.displayName = 'StockPickerTable';