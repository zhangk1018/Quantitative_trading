import React, { useState } from 'react';
import { Typography, Button, Select, Divider, Spin, message } from 'antd';
import { SaveOutlined, FolderOpenOutlined, ReloadOutlined, PlusCircleOutlined, DownloadOutlined, BlockOutlined, PlayCircleOutlined, LoadingOutlined, CaretUpOutlined, CaretDownOutlined } from '@ant-design/icons';
import { ScreenerProvider, useScreener } from './context/ScreenerContext';
import RangeSelector from './components/RangeSelector';
import IndicatorFilter from './components/IndicatorFilter';
import FinancialFilter from './components/FinancialFilter';
import TechnicalFilter from './components/TechnicalFilter';
import ConditionBuilder from './components/ConditionBuilder';
import FactorScoringConfig from './components/FactorScoringConfig';
import { fetchStocks } from '../stock-detail/api';
import { useSettings } from '@/shared/contexts/SettingsContext';

const { Text } = Typography;

const StockPickerContent: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { colors: upDownColors } = useSettings();
  const [screenerLoading, setScreenerLoading] = useState(false);
  const [stockResults, setStockResults] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [sortBy, setSortBy] = useState('change_pct');
  const [sortAsc, setSortAsc] = useState(false);
  const [limit, setLimit] = useState(20);
  const [asOfDate, setAsOfDate] = useState<string>('');

  const totalFiltersCount =
    state.selectedMarketIndicators.length +
    state.selectedFinancialIndicators.length +
    Object.keys(state.selectedTechnicalIndicators).length;

  const handleReset = () => {
    dispatch({ type: 'RESET_ALL' });
    setStockResults([]);
    setTotalCount(0);
    setSortBy('change_pct');
    setSortAsc(false);
    setLimit(20);
    setAsOfDate('');
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
  // 用一个 ref/标记延迟到 state 提交后再发起请求，避免拿到旧 state
  const handleSortByColumn = (column: string) => {
    if (stockResults.length === 0 && !screenerLoading) {
      // 还没查过数据，只更新 sortBy/sortAsc 状态，不发起请求
      if (sortBy === column) {
        setSortAsc(!sortAsc);
      } else {
        setSortBy(column);
        setSortAsc(false);
      }
      return;
    }
    // 已有数据时，点击后立即更新状态并重新查询
    const nextSortAsc = sortBy === column ? !sortAsc : false;
    setSortBy(column);
    setSortAsc(nextSortAsc);
    // 用 setTimeout 0 让 setState 提交后再发起请求（fetchStocks 内部读最新 state）
    setTimeout(() => {
      runScreening(column, nextSortAsc);
    }, 0);
  };

  // 抽取查询逻辑，便于点击表头时复用
  const runScreening = async (overrideSortBy?: string, overrideSortAsc?: boolean) => {
    setScreenerLoading(true);
    try {
      const params: Record<string, any> = {};
      const _sortBy = overrideSortBy ?? sortBy;
      const _sortAsc = overrideSortAsc ?? sortAsc;

      // 上市地（listed_board）
      if (state.selectedBoards && !state.selectedBoards.includes('all')) {
        const boards = state.selectedBoards.filter((b) => b !== 'all');
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

      if (state.stockRange === 'watchlist') {
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

      if (state.marketIndicatorRanges) {
        Object.entries(state.marketIndicatorRanges).forEach(([key, range]) => {
          const multiplier = UNIT_CONVERSION[key] || 1;
          if (range.min) params[`${key}_min`] = Number(range.min) * multiplier;
          if (range.max) params[`${key}_max`] = Number(range.max) * multiplier;
        });
      }

      if (state.financialIndicatorRanges) {
        Object.entries(state.financialIndicatorRanges).forEach(([key, range]) => {
          if (range.min) params[`${key}_min`] = range.min;
          if (range.max) params[`${key}_max`] = range.max;
        });
      }

      // 技术指标选项：每个已选指标序列化为 `tech_{id}=option` 参数
      // 例如：tech_ma=long_align&tech_rsi=low_golden_cross
      if (state.selectedTechnicalIndicators) {
        Object.entries(state.selectedTechnicalIndicators).forEach(([id, option]) => {
          params[`tech_${id}`] = option;
        });
      }

      // 条件构建器：filterTree 序列化为 `cond=<op>:<fieldKey>` 多个参数
      // 例：cond=AND:rsi_oversold&cond=OR:volume_breakout
      if (state.filterTree?.conditions) {
        state.filterTree.conditions.forEach((cond) => {
          params[`cond_${cond.fieldKey}`] = cond.op;
        });
      }

      params.sort_by = _sortBy;
      params.sort_asc = _sortAsc;
      params.offset = 0;
      params.limit = limit;

      if (asOfDate) {
        params.as_of_date = asOfDate.replace(/-/g, '');
      }

      const result = await fetchStocks(params);
      setStockResults(result.items || []);
      setTotalCount(result.total || 0);
      return result;
    } catch (error: any) {
      console.error('选股失败:', error);
      message.error(`选股失败: ${error?.message || '请检查后端服务是否启动'}`);
      setStockResults([]);
      setTotalCount(0);
      return null;
    } finally {
      setScreenerLoading(false);
    }
  };

  // 渲染可排序的表头单元格
  const renderSortableHeader = (label: string, column: string) => {
    const isActive = sortBy === column;
    return (
      <th
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
                <span>(截至 {asOfDate || '2026-06-10'})</span>
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
