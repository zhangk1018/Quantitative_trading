import React from 'react';
import { Button, App } from 'antd';
import { PlusCircleOutlined, DownloadOutlined, ReloadOutlined, BlockOutlined } from '@ant-design/icons';
import { addToBacktestList } from '../../backtest/backtestListStorage';
import type { StockItem } from '../types';

interface StockPickerBottomBarProps {
  selectedCount: number;
  loading: boolean;
  itemsLength: number;
  items: StockItem[];
  selectedCodes: Set<string>;
  onAddToWatchlist: () => void;
  onExport: () => void;
  onRefresh: () => void;
}

/**
 * 选股器底部操作栏
 *
 * 包含：加入回测列表、添加自选、导出结果、加入黑名单、刷新、已选计数
 */
export const StockPickerBottomBar: React.FC<StockPickerBottomBarProps> = React.memo(({
  selectedCount, loading, itemsLength,
  items, selectedCodes,
  onAddToWatchlist, onExport, onRefresh,
}) => {
  const { message } = App.useApp();

  const handleAddToBacktest = () => {
    if (selectedCount === 0) {
      message.warning('请先选择至少一只股票');
      return;
    }
    const selectedItems = items.filter(s => selectedCodes.has(s.stock_code));
    const stocksToAdd = selectedItems.map(s => ({
      stock_code: s.stock_code,
      stock_name: s.stock_name,
    }));
    const added = addToBacktestList(stocksToAdd);
    if (added === 0) {
      message.info('所选股票已在回测列表中');
    } else {
      message.success(`成功添加 ${added} 只股票到回测列表`);
    }
  };

  return (
    <div className="h-10 px-4 flex items-center justify-between border-t border-border-color bg-bg-panel">
      <div className="flex items-center gap-2">
        <Button
          icon={<PlusCircleOutlined />}
          className="bg-color-accent/20 text-color-accent border-color-accent hover:bg-color-accent/30 text-sm"
          onClick={handleAddToBacktest}
          disabled={selectedCount === 0}
          data-testid="add-to-backtest-btn"
        >
          加入回测列表{selectedCount > 0 ? `(${selectedCount})` : ''}
        </Button>
        <Button
          icon={<PlusCircleOutlined />}
          className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
          onClick={onAddToWatchlist}
          disabled={loading}
          data-testid="add-to-watchlist-btn"
        >
          添加自选{selectedCount > 0 ? `(${selectedCount})` : ''}
        </Button>
        <Button
          icon={<DownloadOutlined />}
          className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
          onClick={onExport}
          disabled={loading || itemsLength === 0}
          data-testid="export-result-btn"
        >
          导出结果{itemsLength > 0 ? `(${itemsLength})` : ''}
        </Button>
        <Button
          icon={<BlockOutlined />}
          className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
        >
          加入黑名单
        </Button>
      </div>
      <div className="flex items-center gap-4">
        <Button
          icon={<ReloadOutlined />}
          className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
          onClick={onRefresh}
          disabled={loading || itemsLength === 0}
          data-testid="refresh-result-btn"
        >
          刷新
        </Button>
        <span className="text-text-secondary text-sm">
          {selectedCount > 0 ? `已选中 ${selectedCount} 只` : '未选中（点击左侧复选框多选）'}
        </span>
      </div>
    </div>
  );
});
StockPickerBottomBar.displayName = 'StockPickerBottomBar';