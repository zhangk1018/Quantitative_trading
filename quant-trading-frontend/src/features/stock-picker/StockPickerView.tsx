// StockPickerView.tsx
import React, {
  useState, useCallback, useMemo, useRef, useEffect, useLayoutEffect, memo,
} from 'react';
import {
  Typography, Button, Divider, Spin, message, Checkbox, Modal, Input,
} from 'antd';
import {
  SaveOutlined, FolderOpenOutlined, ReloadOutlined,
  PlusCircleOutlined, DownloadOutlined, BlockOutlined,
  PlayCircleOutlined, LoadingOutlined, CaretUpOutlined, CaretDownOutlined,
} from '@ant-design/icons';
import { useScreenerSelector, useScreenerDispatch } from './context/ScreenerContext';
import RangeSelector from './components/RangeSelector';
import IndicatorFilter from './components/IndicatorFilter';
import FinancialFilter from './components/FinancialFilter';
import TechnicalFilter from './components/TechnicalFilter';
import ConditionBuilder from './components/ConditionBuilder';
import FactorScoringConfig from './components/FactorScoringConfig';
import { fetchStocks } from '../stock-detail/api';
import { useSettings } from '@/shared/contexts/SettingsContext';
import { useWatchlist } from '../watchlist/store';
import StockAnalysisModal from './components/StockAnalysisModal';
import {
  buildScreeningParams,
  formatMarketCap,
  formatNumber,
  exportToCsv,
  CONFIG,
  ScreenerFilterPayload,
  RequestParamKeys,
} from './utils/screener';

const { Text } = Typography;

// ==================== 类型定义 ====================
interface StockItem {
  stock_code: string;
  stock_name: string;
  close: number | null;
  change_pct: number | null;
  turnover_rate: number | null;
  pe: number | null;
  pe_ttm?: number | null;
  pb: number | null;
  market_cap: number | null;
  amount: number | null;
  listed_board: string | null;
  patterns?: string[];
}

interface FetchStocksResponse {
  items: StockItem[];
  total: number;
}

// ==================== 自定义 Hook：数据管理（分离至独立函数，便于测试） ====================
function useScreenerData() {
  // 所有筛选状态（使用 ref 保证最新值，配合 useLayoutEffect 确保同步）
  const selectedBoards = useScreenerSelector((s) => s.market.selectedBoards);
  const stockRange = useScreenerSelector((s) => s.market.stockRange);
  const marketIndicatorRanges = useScreenerSelector((s) => s.marketIndicators.ranges);
  const financialIndicatorRanges = useScreenerSelector((s) => s.financialIndicators.ranges);
  const selectedTechnicalIndicators = useScreenerSelector((s) => s.technical.selected);
  const selectedPatterns = useScreenerSelector((s) => s.patterns.selected);
  const filterGroup = useScreenerSelector((s) => s.condition.filterGroup);

  // 使用 useRef 存储最新状态，并在每次渲染后同步更新
  const stateRef = useRef<ScreenerFilterPayload>({
    selectedBoards,
    stockRange,
    marketIndicatorRanges,
    financialIndicatorRanges,
    selectedTechnicalIndicators,
    selectedPatterns,
    filterGroup,
  });
  // 使用 useLayoutEffect 确保在浏览器绘制前更新，避免视觉不一致
  useLayoutEffect(() => {
    stateRef.current = {
      selectedBoards,
      stockRange,
      marketIndicatorRanges,
      financialIndicatorRanges,
      selectedTechnicalIndicators,
      selectedPatterns,
      filterGroup,
    };
  });

  const [items, setItems] = useState<StockItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sortBy, setSortBy] = useState('change_pct');
  const [sortAsc, setSortAsc] = useState(false);
  const [offset, setOffset] = useState(0);
  const PAGE_SIZE = CONFIG.PAGE_SIZE;

  // 请求控制
  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const debounceTimerRef = useRef<number | null>(null);

  /** 核心请求函数（重命名明确意图） */
  const fetchScreeningData = useCallback(
    async (params: {
      sortBy: string;
      sortAsc: boolean;
      offset: number;
      append?: boolean;
      signal?: AbortSignal;
    }) => {
      const { sortBy: sortByParam, sortAsc: sortAscParam, offset: offsetParam, append = false, signal } = params;

      if (abortRef.current) abortRef.current.abort();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);

      const controller = new AbortController();
      abortRef.current = controller;
      const finalSignal = signal || controller.signal;

      const timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT);
      timeoutRef.current = timeoutId;

      if (!append) setLoading(true);
      else setLoadingMore(true);

      try {
        const state = stateRef.current;
        const requestParams = buildScreeningParams(
          state,
          sortByParam,
          sortAscParam,
          PAGE_SIZE,
          offsetParam,
        );
        const result = (await fetchStocks(requestParams, finalSignal)) as FetchStocksResponse;

        setItems((prev) => (append ? [...prev, ...result.items] : result.items));
        setTotal(result.total || 0);
        setSortBy(sortByParam);
        setSortAsc(sortAscParam);
        setOffset(offsetParam);
        return result;
      } catch (error: any) {
        if (finalSignal.aborted) return null;
        if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') return null;
        // 分类错误
        const isNetworkError = !error.response && error.request;
        const statusCode = error.response?.status;
        let errorMsg = '选股失败，请稍后重试';
        if (isNetworkError) errorMsg = '网络连接异常，请检查网络';
        else if (statusCode === 400) errorMsg = '请求参数错误，请检查筛选条件';
        else if (statusCode >= 500) errorMsg = '服务器异常，请稍后重试';
        else if (error.message) errorMsg = error.message;
        console.error('选股失败:', error);
        message.error(errorMsg);
        if (!append) { setItems([]); setTotal(0); }
        return null;
      } finally {
        if (timeoutRef.current === timeoutId) {
          clearTimeout(timeoutId);
          timeoutRef.current = null;
        }
        if (!append) setLoading(false);
        else setLoadingMore(false);
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [PAGE_SIZE],
  );

  const refresh = useCallback(
    async (newSortBy?: string, newSortAsc?: boolean) => {
      const sortByParam = newSortBy ?? sortBy;
      const sortAscParam = newSortAsc ?? sortAsc;
      return fetchScreeningData({
        sortBy: sortByParam,
        sortAsc: sortAscParam,
        offset: 0,
        append: false,
      });
    },
    [fetchScreeningData, sortBy, sortAsc],
  );

  const loadMore = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      const nextOffset = offset + PAGE_SIZE;
      fetchScreeningData({
        sortBy,
        sortAsc,
        offset: nextOffset,
        append: true,
      });
      debounceTimerRef.current = null;
    }, CONFIG.DEBOUNCE_DELAY) as unknown as number;
  }, [fetchScreeningData, sortBy, sortAsc, offset, PAGE_SIZE]);

  const reset = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    setItems([]);
    setTotal(0);
    setSortBy('change_pct');
    setSortAsc(false);
    setOffset(0);
  }, []);

  // 页面可见性监听
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  // 组件卸载清理
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, []);

  return {
    items,
    total,
    loading,
    loadingMore,
    sortBy,
    sortAsc,
    offset,
    PAGE_SIZE,
    refresh,
    loadMore,
    reset,
  };
}

// ==================== 表格行组件（memo） ====================
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
        {formatMarketCap(stock.amount)}
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

// ==================== 主组件 ====================
const StockPickerContent: React.FC = () => {
  const dispatch = useScreenerDispatch();
  const { addMany } = useWatchlist();
  const tableContainerRef = useRef<HTMLDivElement>(null);

  const {
    items, total, loading, loadingMore, sortBy, sortAsc, PAGE_SIZE,
    refresh, loadMore, reset: resetData,
  } = useScreenerData();

  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [groupName, setGroupName] = useState('');
  const [adding, setAdding] = useState(false);
  const [analysisStock, setAnalysisStock] = useState<StockItem | null>(null);

  // 筛选条件计数
  const marketCount = useScreenerSelector((s) => s.marketIndicators.selected.length);
  const financialCount = useScreenerSelector((s) => s.financialIndicators.selected.length);
  const techCount = useScreenerSelector((s) => Object.keys(s.technical.selected).length);
  const patternCount = useScreenerSelector((s) => Object.keys(s.patterns.selected).length);
  const conditionCount = useScreenerSelector(
    (s) => s.condition.filterGroup?.conditions?.length || 0,
  );
  const totalFiltersCount = useMemo(
    () => marketCount + financialCount + techCount + patternCount + conditionCount,
    [marketCount, financialCount, techCount, patternCount, conditionCount],
  );

  const handleReset = useCallback(() => {
    dispatch({ type: 'RESET_ALL' });
    resetData();
    setSelectedCodes(new Set());
  }, [dispatch, resetData]);

  const handleStartScreening = useCallback(async () => {
    const result = await refresh();
    if (result && result.items.length > 0) {
      message.success(`选股成功，共 ${result.total} 只`);
    }
  }, [refresh]);

  // ---- 排序（带默认方向 + 滚动到顶部） ----
  const handleSort = useCallback(
    (column: string) => {
      const defaultAsc = CONFIG.DEFAULT_SORT_DIR[column] ?? false;
      const newAsc = sortBy === column ? !sortAsc : defaultAsc;
      refresh(column, newAsc).then(() => {
        if (tableContainerRef.current) {
          tableContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
        }
      });
    },
    [sortBy, sortAsc, refresh],
  );

  const allCodes = useMemo(
    () => items.map((s) => s.stock_code).filter((code) => code != null),
    [items],
  );
  const selectedCount = selectedCodes.size;
  const allSelected = allCodes.length > 0 && selectedCount === allCodes.length;
  const indeterminate = selectedCount > 0 && !allSelected;

  const toggleOne = useCallback((code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  const handleDoubleClick = useCallback((stock: StockItem) => {
    setAnalysisStock(stock);
  }, []);

  const toggleAll = useCallback(() => {
    if (allSelected) setSelectedCodes(new Set());
    else setSelectedCodes(new Set(allCodes));
  }, [allCodes, allSelected]);

  const handleExport = useCallback(() => {
    if (items.length === 0) {
      message.warning('暂无可导出的数据，请先选股');
      return;
    }
    exportToCsv(items);
    message.success(`已导出 ${items.length} 只股票`);
  }, [items]);

  const handleAddClick = useCallback(() => {
    if (selectedCount === 0) {
      Modal.info({
        title: '请先勾选股票',
        content: '点击表格左侧复选框选择要加入自选股的股票',
        okText: '我知道了',
      });
      return;
    }
    setAddModalOpen(true);
  }, [selectedCount]);

  const handleConfirmAdd = useCallback(async () => {
    if (adding) return;
    setAdding(true);
    try {
      const codes = Array.from(selectedCodes);
      const result = await addMany(codes, groupName.trim() || undefined);
      const parts = [];
      if (result.added > 0) parts.push(`新增 ${result.added}`);
      if (result.skipped > 0) parts.push(`跳过 ${result.skipped}（已在自选）`);
      if (result.failed > 0) parts.push(`失败 ${result.failed}`);
      const summary = parts.length > 0 ? parts.join('，') : '无变化';
      if (result.failed > 0) {
        message.warning(`添加自选完成：${summary}。失败股票：${result.errors.join(', ')}`);
      } else {
        message.success(`添加自选完成：${summary}`);
      }
      setSelectedCodes(new Set());
      setAddModalOpen(false);
      setGroupName('');
    } catch (e: any) {
      message.error(`添加自选失败: ${e?.message || '未知错误'}`);
    } finally {
      setAdding(false);
    }
  }, [addMany, selectedCodes, groupName, adding]);

  const renderSortableHeader = (label: string, column: string) => {
    const isActive = sortBy === column;
    return (
      <th
        data-testid={`sort-${column}`}
        className={`px-3 py-2 text-right cursor-pointer select-none hover:text-text-primary transition-colors ${
          isActive ? 'text-color-accent' : ''
        }`}
        onClick={() => handleSort(column)}
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
  };

  return (
    <div className="min-h-screen flex flex-col bg-bg-base">
      <div className="flex-1 flex overflow-hidden min-h-[calc(100vh-56px)]">
        {/* 左侧筛选区 */}
        <div
          className="w-[280px] flex-shrink-0 bg-bg-panel border-r border-border-color flex flex-col"
          style={{ height: 'calc(100vh - 56px)' }}
        >
          <div className="flex-1 overflow-y-auto overflow-x-hidden">
            <RangeSelector />
            <IndicatorFilter />
            <FinancialFilter />
            <TechnicalFilter />
            <ConditionBuilder />
            <FactorScoringConfig />
          </div>
          <div className="p-3 border-t border-border-color bg-bg-panel">
            <div className="flex gap-2">
              <Button
                type="primary"
                data-testid="start-screener"
                className={`flex-1 border-color-accent ${
                  loading ? 'bg-color-accent/60 cursor-not-allowed' : 'bg-color-accent hover:bg-color-accent/80'
                }`}
                icon={loading ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
                onClick={handleStartScreening}
                disabled={loading}
              >
                {loading ? '选股中...' : '开始选股'}
              </Button>
              <Button
                data-testid="reset-screener"
                className="flex-1 bg-bg-card border-border-color text-text-secondary hover:text-text-primary"
                icon={<ReloadOutlined />}
                onClick={handleReset}
                disabled={loading}
              >
                重置
              </Button>
            </div>
          </div>
        </div>

        {/* 右侧数据展示区 */}
        <div className="flex-1 flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
          {/* 顶部工具栏 */}
          <div className="h-12 px-4 flex items-center justify-between border-b border-border-color bg-bg-panel">
            <div className="flex items-center gap-4">
              <Text className="text-text-primary font-semibold">因子综合排名</Text>
              <div className="flex items-center gap-2 text-text-secondary text-sm">
                <span className="px-2 py-0.5 bg-bg-card rounded text-xs">
                  筛选条件: {totalFiltersCount}个
                </span>
                <span>共 {total} 只</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Divider type="vertical" className="h-6 bg-border-color" />
              <Button
                icon={<SaveOutlined />}
                className="bg-bg-card text-text-primary border-border-color hover:bg-border-color"
              >
                保存策略
              </Button>
              <Button
                icon={<FolderOpenOutlined />}
                className="bg-bg-card text-text-primary border-border-color hover:bg-border-color"
              >
                我的策略
              </Button>
            </div>
          </div>

          {/* 表格容器，绑定 ref 用于滚动 */}
          <div
            ref={tableContainerRef}
            className="flex-1 flex items-center justify-center text-text-secondary bg-bg-base/50 overflow-auto"
          >
            {loading ? (
              <div className="flex flex-col items-center gap-2">
                <Spin indicator={<LoadingOutlined spin />} size="large" />
                <Text className="text-text-secondary text-sm">正在加载数据...</Text>
              </div>
            ) : items.length > 0 ? (
              <div className="w-full h-full">
                <table className="w-full text-sm border-collapse">
                  <thead className="sticky top-0 z-10 bg-bg-panel">
                    <tr className="text-text-secondary text-xs border-b border-border-color">
                      <th className="px-3 py-2 text-center w-12">
                        <Checkbox
                          indeterminate={indeterminate}
                          checked={allSelected}
                          onChange={toggleAll}
                          data-testid="select-all-checkbox"
                        />
                      </th>
                      <th className="px-3 py-2 text-center text-text-secondary text-xs">#</th>
                      <th className="px-3 py-2 text-left">代码</th>
                      <th className="px-3 py-2 text-left">名称</th>
                      <th className="px-3 py-2 text-right">收盘价</th>
                      {renderSortableHeader('涨跌幅', 'change_pct')}
                      {renderSortableHeader('换手率', 'turnover_rate')}
                      {renderSortableHeader('市盈率', 'pe')}
                      <th className="px-3 py-2 text-right">市净率</th>
                      {renderSortableHeader('总市值', 'market_cap')}
                      {renderSortableHeader('成交额', 'amount')}
                      <th className="px-3 py-2 text-center">板块</th>
                      <th className="px-3 py-2 text-center" style={{ minWidth: 100 }}>
                        K线形态
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((stock, idx) => (
                      <TableRow
                        key={stock.stock_code || idx}
                        stock={stock}
                        index={idx}
                        selected={selectedCodes.has(stock.stock_code)}
                        onToggle={toggleOne}
                        onDoubleClick={handleDoubleClick}
                      />
                    ))}
                  </tbody>
                </table>
                {items.length < total && (
                  <div className="flex justify-center py-4">
                    <Button
                      type="dashed"
                      icon={loadingMore ? <LoadingOutlined spin /> : undefined}
                      onClick={loadMore}
                      disabled={loadingMore}
                      className="w-48"
                      data-testid="load-more-btn"
                    >
                      {loadingMore ? '加载中...' : `加载更多（${Math.min(PAGE_SIZE, total - items.length)} 只）`}
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <Text className="text-text-secondary">暂无数据，请先设置筛选条件并点击"开始选股"</Text>
            )}
          </div>

          {/* 底部操作栏 */}
          <div className="h-10 px-4 flex items-center justify-between border-t border-border-color bg-bg-panel">
            <div className="flex items-center gap-2">
              <Button
                icon={<PlusCircleOutlined />}
                className="bg-color-accent/20 text-color-accent border-color-accent hover:bg-color-accent/30 text-sm"
              >
                加入回测列表
              </Button>
              <Button
                icon={<PlusCircleOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
                onClick={handleAddClick}
                disabled={loading}
                data-testid="add-to-watchlist-btn"
              >
                添加自选{selectedCount > 0 ? `(${selectedCount})` : ''}
              </Button>
              <Button
                icon={<DownloadOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
                onClick={handleExport}
                disabled={loading || items.length === 0}
                data-testid="export-result-btn"
              >
                导出结果{items.length > 0 ? `(${items.length})` : ''}
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
                onClick={() => refresh()}
                disabled={loading || items.length === 0}
                data-testid="refresh-result-btn"
              >
                刷新
              </Button>
              <span className="text-text-secondary text-sm">
                {selectedCount > 0 ? `已选中 ${selectedCount} 只` : '未选中（点击左侧复选框多选）'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 添加自选弹窗 */}
      <Modal
        title={`添加 ${selectedCount} 只股票到自选股`}
        open={addModalOpen}
        onCancel={() => {
          if (!adding) {
            setAddModalOpen(false);
            setGroupName('');
          }
        }}
        onOk={handleConfirmAdd}
        confirmLoading={adding}
        okText="确认添加"
        cancelText="取消"
        destroyOnHidden
        maskClosable={!adding}
        data-testid="add-to-watchlist-modal"
      >
        <div className="py-2">
          <div className="text-text-secondary text-sm mb-2">
            分组名（留空使用默认分组"默认分组"）
          </div>
          <Input
            placeholder="例如：白马股 / 高股息 / 短期关注"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            maxLength={20}
            data-testid="add-to-watchlist-group-input"
          />
          <div className="text-text-secondary text-xs mt-3">
            重复股票会自动跳过，可在「自选股」页面查看与管理。
          </div>
        </div>
      </Modal>
      <StockAnalysisModal
        open={!!analysisStock}
        stock={analysisStock}
        onClose={() => setAnalysisStock(null)}
      />
    </div>
  );
};

const StockPickerView: React.FC = () => <StockPickerContent />;
export default StockPickerView;