import React, { useRef } from 'react';
import { Modal, Input, Select, App } from 'antd';
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

const StockPickerContent: React.FC = () => {
  const { message } = App.useApp();
  const dispatch = useScreenerDispatch();
  const screenerState = useScreener();
  const tableContainerRef = useRef<HTMLDivElement>(null!);

  // 数据层
  const {
    items, total, loading, loadingMore, error, loadMoreError,
    sortBy, sortAsc, PAGE_SIZE,
    fetchFirstPage, fetchNextPage, clearResults, retry, retryLoadMore,
  } = useScreenerData(message);

  // 操作层
  const actions = useStockPickerActions(
    items, total, sortBy, sortAsc, loading,
    fetchFirstPage, clearResults, tableContainerRef,
  );

  return (
    <div className="min-h-screen flex flex-col bg-bg-base">
      <div className="flex-1 flex overflow-hidden min-h-[calc(100vh-56px)]">
        {/* 左侧筛选区 */}
        <StockPickerSidebar
          loading={loading}
          onStartScreening={actions.handleStartScreening}
          onReset={actions.handleReset}
        />

        {/* 右侧数据展示区 */}
        <div className="flex-1 flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
          <StockPickerToolbar
            totalFiltersCount={actions.totalFiltersCount}
            total={total}
            onOpenSaveModal={() => actions.setSaveModalVisible(true)}
            onOpenStrategyDrawer={() => actions.setStrategyDrawerVisible(true)}
          />
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