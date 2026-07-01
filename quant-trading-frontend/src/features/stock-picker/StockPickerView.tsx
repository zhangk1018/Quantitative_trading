import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Typography, Button, Select, Divider, Spin, message, Checkbox, Modal, Input } from 'antd';
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
import { useWatchlist } from '../watchlist/store';

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
      if (range.min) params[`${key}_min`] = Number(range.min);
      if (range.max) params[`${key}_max`] = Number(range.max);
    });
  }

  // 技术指标选项：每个已选指标序列化为 `tech_{id}=option` 参数
  // 例如：tech_ma=long_align&tech_rsi=low_golden_cross
  if (selectedTechnicalIndicators) {
    Object.entries(selectedTechnicalIndicators).forEach(([id, option]) => {
      params[`tech_${id}`] = option;
    });
  }

  // K线形态筛选：每个已选形态序列化为 `pattern_{id}=lookbackDays` 参数
  // 例如：pattern_hammer=3&pattern_bullish_engulfing=5
  if (state.selectedPatterns) {
    Object.entries(state.selectedPatterns).forEach(([patternId, lookbackDays]) => {
      params[`pattern_${patternId}`] = lookbackDays;
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
  const { addMany } = useWatchlist();
  const [screenerLoading, setScreenerLoading] = useState(false);
  const [stockResults, setStockResults] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [sortBy, setSortBy] = useState('change_pct');
  const [sortAsc, setSortAsc] = useState(false);
  const [limit, setLimit] = useState(20);
  // 选股结果中的复选框选中项（key 为股票 code）
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  // 批量加入自选：自定义分组名（空 → 走后端默认分组）
  const [addToWatchlistOpen, setAddToWatchlistOpen] = useState(false);
  const [groupNameInput, setGroupNameInput] = useState('');
  const [addingToWatchlist, setAddingToWatchlist] = useState(false);
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
    Object.keys(state.selectedPatterns).length +
    (state.filterGroup?.conditions.length || 0);

  const handleReset = () => {
    // K 2026-06-22 反馈：重置时取消进行中的请求，避免旧响应覆盖空状态
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    requestIdRef.current += 1;
    dispatch({ type: 'RESET_ALL' });
    setStockResults([]);
    setTotalCount(0);
    setSortBy('change_pct');
    setSortAsc(false);
    setLimit(20);
    setSelectedCodes(new Set());
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

  // ============================================================
  // 复选框：单行 toggle / 全选 / 反选 / 清空
  // 选股结果切换（重新选股 / 重置）时自动清空选中集，避免悬空引用
  // ============================================================
  const allCodes = useMemo(
    () => stockResults.map((s) => s.stock_code).filter(Boolean) as string[],
    [stockResults],
  );
  const selectedCount = selectedCodes.size;
  const allSelected = allCodes.length > 0 && selectedCount === allCodes.length;
  const indeterminate = selectedCount > 0 && !allSelected;

  const toggleOne = (code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelectedCodes(new Set());
    } else {
      setSelectedCodes(new Set(allCodes));
    }
  };

  // ============================================================
  // 导出 CSV：导出当前 stockResults 全部行（不分选中/未选中，保持简单）
  // 文件名格式：screener-result-YYYYMMDD-HHmm.csv
  // ============================================================
  const handleExportCsv = () => {
    if (stockResults.length === 0) {
      message.warning('暂无可导出的数据，请先选股');
      return;
    }
    // CSV 表头（中文 + 英文别名）
    const headers = [
      '#', '代码', '名称', '收盘价', '涨跌幅(%)', '换手率(%)',
      '市盈率(PE)', '市净率(PB)', '总市值(亿)', '成交额(亿)', '板块',
    ];
    // CSV 单元格：含逗号/引号/换行的字段加引号包裹，引号转义为 ""
    const escape = (v: unknown): string => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      if (/[",\n\r]/.test(s)) {
        return `"${s.replace(/"/g, '""')}"`;
      }
      return s;
    };
    const rows = stockResults.map((s, idx) => {
      const changePct = Number(s.change_pct) || 0;
      return [
        idx + 1,
        s.stock_code,
        s.stock_name,
        Number(s.close ?? 0).toFixed(2),
        changePct.toFixed(2),
        s.turnover_rate === null || s.turnover_rate === undefined ? '' : Number(s.turnover_rate).toFixed(2),
        s.pe ?? s.pe_ttm ?? '',
        s.pb ?? '',
        // market_cap/amount 字段为万元，导出"亿"对用户更直观
        s.market_cap === null || s.market_cap === undefined ? '' : (Number(s.market_cap) / 10000).toFixed(2),
        s.amount === null || s.amount === undefined ? '' : (Number(s.amount) / 10000).toFixed(2),
        s.listed_board ?? '',
      ];
    });
    // Excel 友好：UTF-8 BOM
    const BOM = '\uFEFF';
    const csv = BOM + [headers, ...rows]
      .map((row) => row.map(escape).join(','))
      .join('\r\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const filename = `screener-result-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.csv`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    message.success(`已导出 ${stockResults.length} 只股票到 ${filename}`);
  };

  // ============================================================
  // 添加自选：弹窗让用户选分组 → 批量 POST /api/watchlist
  // - 无选中：弹 Modal 提示用户勾选
  // - 已选中：弹分组名输入框（可留空走后端默认）
  // ============================================================
  const handleAddToWatchlistClick = () => {
    if (selectedCount === 0) {
      Modal.info({
        title: '请先勾选股票',
        content: '点击表格左侧复选框选择要加入自选股的股票',
        okText: '我知道了',
      });
      return;
    }
    setAddToWatchlistOpen(true);
  };

  const handleConfirmAddToWatchlist = async () => {
    if (addingToWatchlist) return;
    setAddingToWatchlist(true);
    try {
      const codes = Array.from(selectedCodes);
      const result = await addMany(
        codes,
        groupNameInput.trim() || undefined,
      );
      // 汇总结果：成功/跳过/失败分类提示（K 偏好：覆盖率异常必须显示原因）
      const parts: string[] = [];
      if (result.added > 0) parts.push(`新增 ${result.added}`);
      if (result.skipped > 0) parts.push(`跳过 ${result.skipped}（已在自选）`);
      if (result.failed > 0) parts.push(`失败 ${result.failed}`);
      const summary = parts.length > 0 ? parts.join('，') : '无变化';
      if (result.failed > 0) {
        message.warning(
          `添加自选完成：${summary}。失败股票：${result.errors.join(', ')}`,
        );
      } else {
        message.success(`添加自选完成：${summary}`);
      }
      // 操作成功后清空选中（避免重复点击）
      setSelectedCodes(new Set());
      setAddToWatchlistOpen(false);
      setGroupNameInput('');
    } catch (e: any) {
      message.error(`添加自选失败: ${e?.message || '未知错误'}`);
    } finally {
      setAddingToWatchlist(false);
    }
  };

  const handleCancelAddToWatchlist = () => {
    if (addingToWatchlist) return;
    setAddToWatchlistOpen(false);
    setGroupNameInput('');
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
      // K 2026-06-22 反馈 #5：选股结果变化时清空选中集（旧的 stock_code 不再有效）
      setSelectedCodes(new Set());
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
                      <th className="px-3 py-2 text-center w-12">
                        {stockResults.length > 0 && (
                          <Checkbox
                            indeterminate={indeterminate}
                            checked={allSelected}
                            onChange={toggleAll}
                            data-testid="select-all-checkbox"
                          />
                        )}
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
                      <th className="px-3 py-2 text-center" style={{ minWidth: 100 }}>K线形态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stockResults.map((stock, idx) => {
                      const changePct = Number(stock.change_pct) || 0;
                      const isUp = changePct >= 0;
                      return (
                        <tr
                          key={stock.stock_code || idx}
                          className={`border-b border-border-color hover:bg-bg-panel/60 transition-colors ${
                            selectedCodes.has(stock.stock_code) ? 'bg-color-accent/10' : ''
                          }`}
                        >
                          <td className="px-3 py-2 text-center">
                            <Checkbox
                              checked={selectedCodes.has(stock.stock_code)}
                              onChange={() => toggleOne(stock.stock_code)}
                              data-testid={`row-checkbox-${stock.stock_code}`}
                            />
                          </td>
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
                          <td className="px-3 py-2 text-center">
                            {stock.patterns && stock.patterns.length > 0 ? (
                              <div className="flex gap-1 justify-center flex-wrap">
                                {stock.patterns.slice(0, 2).map((p: string, i: number) => (
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
                onClick={handleAddToWatchlistClick}
                disabled={screenerLoading}
                data-testid="add-to-watchlist-btn"
              >
                添加自选{selectedCount > 0 ? `(${selectedCount})` : ''}
              </Button>
              <Button
                icon={<DownloadOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
                onClick={handleExportCsv}
                disabled={screenerLoading || stockResults.length === 0}
                data-testid="export-result-btn"
              >
                导出结果{stockResults.length > 0 ? `(${stockResults.length})` : ''}
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
                onClick={() => runScreening()}
                disabled={screenerLoading || stockResults.length === 0}
                data-testid="refresh-result-btn"
              >
                刷新
              </Button>
              <span className="text-text-secondary text-sm">
                {selectedCount > 0
                  ? `已选中 ${selectedCount} 只`
                  : '未选中（点击左侧复选框多选）'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 添加自选弹窗：分组名输入 + 提交 */}
      <Modal
        title={`添加 ${selectedCount} 只股票到自选股`}
        open={addToWatchlistOpen}
        onCancel={handleCancelAddToWatchlist}
        onOk={handleConfirmAddToWatchlist}
        confirmLoading={addingToWatchlist}
        okText="确认添加"
        cancelText="取消"
        destroyOnHidden
        maskClosable={false}
        data-testid="add-to-watchlist-modal"
      >
        <div className="py-2">
          <div className="text-text-secondary text-sm mb-2">
            分组名（留空使用默认分组"默认分组"）
          </div>
          <Input
            placeholder="例如：白马股 / 高股息 / 短期关注"
            value={groupNameInput}
            onChange={(e) => setGroupNameInput(e.target.value)}
            maxLength={20}
            data-testid="add-to-watchlist-group-input"
          />
          <div className="text-text-secondary text-xs mt-3">
            重复股票会自动跳过，可在「自选股」页面查看与管理。
          </div>
        </div>
      </Modal>
    </div>
  );
};

const StockPickerView: React.FC = () => {
  // K 2026-06-17 决策：ScreenerProvider 已上移到 AppLayout 层（让 /config 和 /picker
  // 共享同一份 screener state，无需事件桥接）
  return <StockPickerContent />;
};

export default StockPickerView;
