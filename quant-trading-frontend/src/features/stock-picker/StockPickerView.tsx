import React, { useState, useRef, useEffect } from 'react';
import { Typography, Button, Select, Divider, Spin, message } from 'antd';
import { SaveOutlined, FolderOpenOutlined, ReloadOutlined, PlusCircleOutlined, DownloadOutlined, BlockOutlined, PlayCircleOutlined, LoadingOutlined, CaretUpOutlined, CaretDownOutlined } from '@ant-design/icons';
import { ScreenerProvider, useScreener, ScreenerState } from './context/ScreenerContext';
import RangeSelector from './components/RangeSelector';
import IndicatorFilter from './components/IndicatorFilter';
import FinancialFilter from './components/FinancialFilter';
import TechnicalFilter from './components/TechnicalFilter';
import ConditionBuilder from './components/ConditionBuilder';
import FactorScoringConfig from './components/FactorScoringConfig';
import { fetchStocks } from '../stock-detail/api';
import { useSettings } from '@/shared/contexts/SettingsContext';

const { Text } = Typography;

// =====================================================================
// K 2026-06-18 反馈 #4：把 ScreenerState → fetchStocks params 的转换抽离为纯函数，
// 便于单测 + 降低 runScreening 职责。
// =====================================================================

/**
 * 把 ScreenerState 序列化为 fetchStocks 的 params（纯函数，无副作用）
 * K 2026-06-18 反馈 #4：便于单元测试 + 降低 runScreening 的行数。
 * K 2026-06-18 反馈 #1：显式解构 state 字段并在注释中列出依赖，
 * 避免未来 ScreenerState 结构变化时本函数产生隐式依赖。
 *
 * 依赖的 ScreenerState 字段（变更时需同步检查本函数）：
 * - selectedBoards: string[]   — 上市地过滤
 * - stockRange: string         — 选股范围（watchlist / all）
 * - marketIndicatorRanges: Record<string, IndicatorRange>  — 行情指标阈值（含单位转换）
 * - financialIndicatorRanges: Record<string, IndicatorRange> — 财务指标阈值
 * - selectedTechnicalIndicators: Record<string, string>    — 技术指标选项
 * - filterGroup: FilterGroup | null  — 条件构建器
 */
export function buildScreeningParams(
  state: ScreenerState,
  sortBy: string,
  sortAsc: boolean,
  limit: number,
): Record<string, unknown> {
  // 显式解构 state 字段（K 反馈 #1）：列出所有依赖，未来调整时编译器会立即提示
  const {
    selectedBoards,
    stockRange,
    marketIndicatorRanges,
    financialIndicatorRanges,
    selectedTechnicalIndicators,
    filterGroup,
  } = state;
  const params: Record<string, unknown> = {};

  // 上市地（listed_board）
  if (selectedBoards && !selectedBoards.includes('all')) {
    const boards = selectedBoards.filter((b) => b !== 'all');
    if (boards.length > 0) {
      if (
        boards.length === 2 &&
        boards.includes('上海主板') &&
        boards.includes('深圳主板')
      ) {
        params.listed_board = '主板';
      } else {
        params.listed_board = boards.join(',');
      }
    }
  }

  if (stockRange === 'watchlist') {
    params.watchlist_only = true;
  }

  // 指标范围参数单位转换（前端用户输入单位 → 后端存储单位）
  // market_cap: 用户输入"亿" → 后端"万元"，×10000
  // amount: 用户输入"亿" → 后端"万元"，×10000
  // volume: 用户输入"手" → 后端"手"，无需转换
  const UNIT_CONVERSION: Record<string, number> = {
    market_cap: 10000,  // 亿 → 万元
    amount: 10000,      // 亿 → 万元
  };

  if (marketIndicatorRanges) {
    Object.entries(marketIndicatorRanges).forEach(([key, range]) => {
      const multiplier = UNIT_CONVERSION[key] || 1;
      if (range.min) params[`${key}_min`] = Number(range.min) * multiplier;
      if (range.max) params[`${key}_max`] = Number(range.max) * multiplier;
    });
  }

  if (financialIndicatorRanges) {
    Object.entries(financialIndicatorRanges).forEach(([key, range]) => {
      if (range.min) params[`${key}_min`] = range.min;
      if (range.max) params[`${key}_max`] = range.max;
    });
  }

  // 技术指标选项：每个已选指标序列化为 `tech_{id}=option` 参数
  // 例如：tech_ma=long_align&tech_rsi=low_golden_cross
  if (selectedTechnicalIndicators) {
    Object.entries(selectedTechnicalIndicators).forEach(([id, option]) => {
      params[`tech_${id}`] = option;
    });
  }

  // 条件构建器：filterGroup 序列化为 `cond_<fieldKey>=<op>` 多个 query 参数
  // 例：cond_rsi_oversold=AND&cond_volume_breakout=AND
  // 后端 router/stocks.py 的 _parse_condition_builder 识别该格式
  // (K 2026-06-18 任务：把条件构建器接入选股)
  if (filterGroup?.conditions) {
    filterGroup.conditions.forEach((cond) => {
      params[`cond_${cond.fieldKey}`] = cond.op;
    });
  }

  params.sort_by = sortBy;
  params.sort_asc = sortAsc;
  params.offset = 0;
  params.limit = limit;

  return params;
}

const StockPickerContent: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { colors: upDownColors } = useSettings();
  const [screenerLoading, setScreenerLoading] = useState(false);
  const [stockResults, setStockResults] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [sortBy, setSortBy] = useState('change_pct');
  const [sortAsc, setSortAsc] = useState(false);
  const [limit, setLimit] = useState(20);
  // K 2026-06-18 反馈 #5：移除未使用的 asOfDate state（UI 无对应日期选择器）

  // K 2026-06-18 任务 #11：用 AbortController 取消上一次未完成的选股请求，
  // 防止用户快速多次点击时旧数据覆盖新数据。
  // K 2026-06-18 反馈 #1：加 isMounted 保险，防止组件卸载后 setState 警告 + 旧 controller
  // 的 finally 块在 abortRef 已指向新 controller 时不关 loading 的潜在 race。
  // K 2026-06-18 反馈 #4：引入 requestIdRef 自增计数器作为"当前活跃请求"判断，
  // 避免依赖引用比较（多个连续请求被 abort 时仍能准确识别"哪一次是最终活跃"）。
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      // 组件卸载时取消未完成的请求 + 清空 ref，避免内存泄漏 / setState after unmount
      // K 2026-06-18 反馈 #6：同时把 abortRef.current 置 null，
      // 防止 finally 块中 abortRef.current === controller 判断因引用变化失败导致 loading 未清理
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, []);

  const totalFiltersCount =
    state.selectedMarketIndicators.length +
    state.selectedFinancialIndicators.length +
    Object.keys(state.selectedTechnicalIndicators).length +
    (state.filterGroup?.conditions.length || 0);

  const handleReset = () => {
    dispatch({ type: 'RESET_ALL' });
    setStockResults([]);
    setTotalCount(0);
    setSortBy('change_pct');
    setSortAsc(false);
    setLimit(20);
  };

  const handleStartScreening = async () => {
    const result = await runScreening();
    if (result && result.items && result.items.length > 0) {
      message.success(`选股成功，共 ${result.total} 只`);
    }
  };

  // 格式化市值（万元 → 亿）
  const formatMarketCap = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return '-';
    // market_cap 字段为万元，转为亿需要 ÷10000
    const yi = value / 10000;
    return `${yi.toFixed(2)}亿`;
  };

  // 格式化数字
  const formatNumber = (value: number | null | undefined, decimals = 2): string => {
    if (value === null || value === undefined) return '-';
    return Number(value).toFixed(decimals);
  };

  // 点击表头排序：同列切换升/降序，不同列切换为该列（默认降序）
  // K 2026-06-18 反馈 #2：统一排序行为，无论是否已有数据，立即按新排序参数发起请求。
  // 之前"无数据时只更新 state"会导致用户切换列后不立即生效，产生歧义。
  const handleSortByColumn = (column: string) => {
    const nextSortAsc = sortBy === column ? !sortAsc : false;
    setSortBy(column);
    setSortAsc(nextSortAsc);
    runScreening(column, nextSortAsc);
  };

  // 抽取查询逻辑，便于点击表头时复用
  // K 2026-06-18 任务 #11：每次调用先 abort 上一次未完成的请求，避免旧数据覆盖
  // K 2026-06-18 反馈 #4：参数构建已抽离到 buildScreeningParams 纯函数，
  // 本函数仅关注 AbortController 生命周期 + 错误处理 + setState 分发
  // K 2026-06-18 反馈 #4：用 requestIdRef 自增计数器判断"当前活跃请求"，
  // 避免引用比较在多请求快速切换时失效导致 loading 卡住
  const runScreening = async (overrideSortBy?: string, overrideSortAsc?: boolean) => {
    // 取消上一次未完成的请求（如果有）
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;
    // K 反馈 #4：自增 ID 标记本次请求
    const myRequestId = ++requestIdRef.current;

    setScreenerLoading(true);
    try {
      const _sortBy = overrideSortBy ?? sortBy;
      const _sortAsc = overrideSortAsc ?? sortAsc;
      const params = buildScreeningParams(state, _sortBy, _sortAsc, limit) as Record<string, any>;

      const result = await fetchStocks(params, controller.signal);
      // K 反馈 #4：仅当本次 requestId 仍是当前活跃的 + 组件未卸载才更新 state
      if (requestIdRef.current !== myRequestId || !isMountedRef.current) {
        return null;
      }
      setStockResults(result.items || []);
      setTotalCount(result.total || 0);
      return result;
    } catch (error: any) {
      // axios 取消请求会抛 AbortError，忽略（属于正常取消）
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
        return null;
      }
      if (!isMountedRef.current) return null;
      console.error('选股失败:', error);
      message.error(`选股失败: ${error?.message || '请检查后端服务是否启动'}`);
      setStockResults([]);
      setTotalCount(0);
      return null;
    } finally {
      // K 反馈 #4：仅当本次 requestId 仍是当前活跃的 + 组件未卸载才清 loading
      if (requestIdRef.current === myRequestId && isMountedRef.current) {
        setScreenerLoading(false);
      }
    }
  };

  // 渲染可排序的表头单元格
  const renderSortableHeader = (label: string, column: string) => {
    const isActive = sortBy === column;
    return (
      <th
        data-testid={`sort-${column}`}
        className={`px-3 py-2 text-right cursor-pointer select-none hover:text-text-primary transition-colors ${
          isActive ? 'text-color-accent' : ''
        }`}
        onClick={() => handleSortByColumn(column)}
        title="点击排序"
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {isActive ? (
            sortAsc ? (
              <CaretUpOutlined style={{ fontSize: 10 }} />
            ) : (
              <CaretDownOutlined style={{ fontSize: 10 }} />
            )
          ) : (
            <span style={{ display: 'inline-block', width: 10 }} />
          )}
        </span>
      </th>
    );
  };

  return (
    <div className="min-h-screen flex flex-col bg-bg-base">
      {/* 主内容区 */}
      <div className="flex-1 flex overflow-hidden min-h-[calc(100vh-56px)]">
        {/* 左侧筛选区（固定宽度280px） */}
        <div className="w-[280px] flex-shrink-0 bg-bg-panel border-r border-border-color flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
          <div className="flex-1 overflow-y-auto overflow-x-hidden">
            <RangeSelector />
            <IndicatorFilter />
            <FinancialFilter />
            <TechnicalFilter />
            <ConditionBuilder />
            <FactorScoringConfig />
          </div>
          
          {/* 左侧底部操作按钮 */}
          <div className="p-3 border-t border-border-color bg-bg-panel">
            <div className="flex gap-2">
              <Button
                type="primary"
                data-testid="start-screener"
                className={`flex-1 border-color-accent ${screenerLoading ? 'bg-color-accent/60 cursor-not-allowed' : 'bg-color-accent hover:bg-color-accent/80'}`}
                icon={screenerLoading ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
                onClick={handleStartScreening}
                disabled={screenerLoading}
              >
                {screenerLoading ? '选股中...' : '开始选股'}
              </Button>
              <Button
                data-testid="reset-screener"
                className="flex-1 bg-bg-card border-border-color text-text-secondary hover:text-text-primary"
                icon={<ReloadOutlined />}
                onClick={handleReset}
                disabled={screenerLoading}
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
                <span className="px-2 py-0.5 bg-bg-card rounded text-xs">筛选条件: {totalFiltersCount}个</span>
                <span>共 {totalCount} 只</span>
                {/* K 2026-06-18 反馈 #5：移除 asOfDate 状态后，"截至 日期" 显示一并移除 */}
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

          {/* 数据展示区域 */}
          <div className="flex-1 flex items-center justify-center text-text-secondary bg-bg-base/50 overflow-hidden">
            {screenerLoading ? (
              <div className="flex flex-col items-center gap-2">
                <Spin indicator={<LoadingOutlined spin />} size="large" />
                <Text className="text-text-secondary text-sm">正在加载数据...</Text>
              </div>
            ) : stockResults.length > 0 ? (
              <div className="w-full h-full overflow-auto">
                <table className="w-full text-sm border-collapse">
                  <thead className="sticky top-0 z-10 bg-bg-panel">
                    <tr className="text-text-secondary text-xs border-b border-border-color">
                      <th className="px-3 py-2 text-center w-12">#</th>
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
                    </tr>
                  </thead>
                  <tbody>
                    {stockResults.map((stock, idx) => {
                      const changePct = Number(stock.change_pct) || 0;
                      const isUp = changePct >= 0;
                      return (
                        <tr
                          key={stock.stock_code || idx}
                          className="border-b border-border-color hover:bg-bg-panel/60 transition-colors"
                        >
                          <td className="px-3 py-2 text-center text-text-secondary text-xs">{idx + 1}</td>
                          <td className="px-3 py-2 text-text-primary font-mono">{stock.stock_code}</td>
                          <td className="px-3 py-2 text-text-primary">{stock.stock_name}</td>
                          <td className="px-3 py-2 text-right font-mono" style={{ color: isUp ? upDownColors.up : upDownColors.down }}>
                            {formatNumber(stock.close)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono" style={{ color: isUp ? upDownColors.up : upDownColors.down }}>
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
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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
              >
                添加自选
              </Button>
              <Button
                icon={<DownloadOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
              >
                导出结果
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
              >
                刷新
              </Button>
              <span className="text-text-secondary text-sm">未选中 (点击行查看详情, 勾选复选框多选)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const StockPickerView: React.FC = () => {
  // K 2026-06-17 决策：ScreenerProvider 已上移到 AppLayout 层（让 /config 和 /picker
  // 共享同一份 screener state，无需事件桥接）
  return <StockPickerContent />;
};

export default StockPickerView;
