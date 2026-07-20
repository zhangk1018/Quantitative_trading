import React, { useRef, useMemo, useCallback } from 'react';
import { Modal, Input, Select, App } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useScreenerDispatch, useScreener } from './context/ScreenerContext';
import { useScreenerData } from './hooks/useScreenerData';
import { useStockPickerActions } from './hooks/useStockPickerActions';
import { StockPickerSidebar } from './components/StockPickerSidebar';
import { StockPickerToolbar } from './components/StockPickerToolbar';
import { StockPickerTable } from './components/StockPickerTable';
import { StockPickerBottomBar } from './components/StockPickerBottomBar';
import { SaveStrategyModal } from './components/SaveStrategyModal';
import { StrategyListDrawer } from './components/StrategyListDrawer';
import StockAnalysisModal from './components/StockAnalysisModal';
import { screenerStateToFilterNode } from '@/features/strategy-backtest/utils/screenerToFilterNode';
import { encodeTreeParam } from '@/features/strategy-backtest/utils/filterTreeAdapter';

const StockPickerContent: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const dispatch = useScreenerDispatch();
  const { state: screenerState } = useScreener();
  const tableContainerRef = useRef<HTMLDivElement>(null!);

  const { tree: filterTree, warnings: conversionWarnings, hardErrors: conversionHardErrors } = useMemo(
    () => screenerStateToFilterNode(screenerState),
    [screenerState],
  );

  const handleNavigateToBacktest = useCallback(() => {
    if (!filterTree) {
      if (conversionHardErrors.length > 0) {
        message.error(conversionHardErrors[0]);
        return;
      }
      message.warning('请先设置至少一个筛选条件（如板块、行情指标或技术形态）');
      return;
    }
    if (conversionHardErrors.length > 0) {
      message.error(conversionHardErrors[0]);
      return;
    }

    const doNavigate = () => {
      try {
        const encoded = encodeTreeParam(filterTree);
        navigate(`/strategy-backtest?tree=${encoded}`);
      } catch (e) {
        message.error((e as Error).message);
      }
    };

    if (conversionWarnings.length > 0) {
      const warningItems = conversionWarnings.map((w, i) => <div key={i} className="text-xs text-text-secondary py-0.5">• {w}</div>);
      Modal.warning({
        title: `${conversionWarnings.length}个筛选条件不支持回测，已自动过滤`,
        content: (
          <div className="mt-2">
            <div className="text-xs text-text-secondary mb-2">以下条件将不参与回测运算，剩余条件将正常参与回测：</div>
            {warningItems}
          </div>
        ),
        okText: '继续回测',
        onOk: doNavigate,
      });
      console.warn('回测条件转换警告:', conversionWarnings);
    } else {
      doNavigate();
    }
  }, [filterTree, conversionWarnings, conversionHardErrors, navigate, message]);

  // 数据层
  const {
    items, total, loading, loadingMore, error, loadMoreError,
    sortBy, sortAsc, PAGE_SIZE,
    phase, progress, progressText,
    fetchFirstPage, fetchNextPage, clearResults, retry, retryLoadMore,
    cancelScreening,
  } = useScreenerData(message);

  const showProgressBar = phase !== 'idle' && phase !== 'ready' && phase !== ('' as any);

  // 操作层
  const actions = useStockPickerActions(
    items, total, sortBy, sortAsc, loading,
    fetchFirstPage, clearResults, tableContainerRef,
  );

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* 左侧筛选区 */}
        <StockPickerSidebar
          loading={loading}
          onStartScreening={actions.handleStartScreening}
          onReset={actions.handleReset}
        />

        {/* 右侧数据展示区 */}
        <div className="flex-1 flex flex-col h-full min-h-0">
          <StockPickerToolbar
            totalFiltersCount={actions.totalFiltersCount}
            total={total}
            onOpenSaveModal={() => actions.setSaveModalVisible(true)}
            onOpenStrategyDrawer={() => actions.setStrategyDrawerVisible(true)}
            onNavigateToBacktest={handleNavigateToBacktest}
            backtestWarningsCount={conversionWarnings.length}
          />
          {showProgressBar && (
            <div className="px-4 py-2 bg-bg-card border-b border-border-color flex items-center gap-3">
              <div className="flex-1 h-1.5 bg-bg-base rounded-full overflow-hidden">
                <div
                  className="h-full bg-color-accent rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
                />
              </div>
              <span className="text-text-secondary text-xs whitespace-nowrap min-w-0 truncate max-w-[240px]">
                {progressText || '加载中...'}
              </span>
              <span className="text-text-tertiary text-xs font-mono">
                {Math.round(progress)}%
              </span>
              <button
                onClick={cancelScreening}
                className="text-text-secondary text-xs hover:text-text-primary transition-colors px-2 py-0.5 border border-border-color rounded"
              >
                取消
              </button>
            </div>
          )}
          <StockPickerTable
            items={items}
            total={total}
            loading={loading}
            loadingMore={loadingMore}
            pageSize={PAGE_SIZE}
            selectedCodes={actions.selectedCodes}
            indeterminate={actions.indeterminate}
            allSelected={actions.allSelected}
            sortBy={sortBy}
            sortAsc={sortAsc}
            error={error}
            loadMoreError={loadMoreError}
            onToggleAll={actions.toggleAll}
            onToggleOne={actions.toggleOne}
            onSort={actions.handleSort}
            onDoubleClick={actions.handleDoubleClick}
            onLoadMore={fetchNextPage}
            onRetry={retry}
            onRetryLoadMore={retryLoadMore}
            scrollContainerRef={tableContainerRef}
          />
          <StockPickerBottomBar
            selectedCount={actions.selectedCount}
            loading={loading}
            itemsLength={items.length}
            items={items}
            selectedCodes={actions.selectedCodes}
            onAddToWatchlist={actions.handleAddClick}
            onExport={actions.handleExport}
            onRefresh={() => fetchFirstPage()}
          />
        </div>
      </div>

      {/* 添加自选弹窗 */}
      <Modal
        title={`添加 ${actions.selectedCount} 只股票到自选股`}
        open={actions.addModalOpen}
        onCancel={() => {
          if (!actions.adding) {
            actions.setAddModalOpen(false);
            actions.setSelectedGroup(actions.selectedMarketLabel);
            actions.setNewGroupName('');
          }
        }}
        onOk={actions.handleConfirmAdd}
        confirmLoading={actions.adding}
        okText="确认添加"
        cancelText="取消"
        destroyOnHidden
        maskClosable={!actions.adding}
        data-testid="add-to-watchlist-modal"
      >
        <div className="py-2">
          <div className="text-text-secondary text-sm mb-2">选择目标分组</div>
          <Select
            value={actions.selectedGroup}
            onChange={(v) => actions.setSelectedGroup(v)}
            options={[
              { label: actions.selectedMarketLabel, value: actions.selectedMarketLabel },
              ...actions.watchlistState?.customGroups?.map((g: string) => ({ label: g, value: g })) || [],
              { label: '+ 新建分组', value: '__new__' },
            ]}
            className="w-full"
            data-testid="add-to-watchlist-group-select"
            disabled={actions.adding}
          />
          {actions.selectedGroup === '__new__' && (
            <div className="mt-3">
              <div className="text-text-secondary text-sm mb-1">新分组名称</div>
              <Input
                placeholder="输入分组名称"
                value={actions.newGroupName}
                onChange={(e) => actions.setNewGroupName(e.target.value)}
                maxLength={20}
                disabled={actions.adding}
                data-testid="add-to-watchlist-new-group-input"
                autoFocus
              />
            </div>
          )}
          <div className="text-text-secondary text-xs mt-3">
            重复股票会自动跳过，可在「自选股」页面查看与管理。
          </div>
        </div>
      </Modal>

      <StockAnalysisModal
        open={!!actions.analysisStock}
        stock={actions.analysisStock}
        onClose={() => actions.setAnalysisStock(null)}
        conditions={actions.filterGroup?.conditions}
      />
      <SaveStrategyModal
        visible={actions.saveModalVisible}
        existingStrategies={actions.strategies}
        onClose={() => actions.setSaveModalVisible(false)}
        onSave={actions.handleSaveStrategy}
      />
      <StrategyListDrawer
        visible={actions.strategyDrawerVisible}
        strategies={actions.strategies}
        onClose={() => actions.setStrategyDrawerVisible(false)}
        onLoad={(strategy) => {
          dispatch({ type: 'LOAD_STRATEGY', payload: strategy.state });
        }}
        onRename={actions.handleRenameStrategy}
        onDelete={actions.handleDeleteStrategy}
      />
    </div>
  );
};

const StockPickerView: React.FC = () => <StockPickerContent />;
export default StockPickerView;