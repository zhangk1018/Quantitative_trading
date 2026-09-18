// BacktestConfigPanel.tsx — 左侧策略配置面板（Form 重构）

import React, { useEffect, useMemo, useState } from 'react';
import {
  Card, Select, DatePicker, Input, InputNumber, Cascader, Spin, Space, Button,
  Tag, Tooltip, Typography, Form, Collapse,
} from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { BacktestConfig, BacktestCondition, BacktestFormValues, BacktestStock, IndicatorParams, SellStrategy } from './backtestTypes';
import {
  DEFAULT_BACKTEST_CONFIG,
  SELL_STRATEGY_LABELS,
  DEFAULT_LAYERED_TP_PARAMS,
} from './backtestTypes';
import { useStockSearch } from './useStockSearch';
import { getBacktestList, removeFromBacktestList } from './backtestListStorage';
import { getBacktestDefaults } from './backtestSettingsStorage';
import { useWatchlist } from '../watchlist/store';
import { listCustomIndicators } from '../stock-picker/utils/customIndicatorStorage';
import type { CustomIndicator } from '../stock-picker/types/customIndicator';
import { fetchStocks } from '../stock-detail/api';
import type { StockSearchItem } from '../stock-detail/api';
import { inferMarketKey, type MarketKey } from '../watchlist/utils/stock-utils';
import {
  listCustomSellStrategies,
  type CustomSellStrategy,
} from './utils/customSellStrategyStorage';
import { PRESET_CONDITIONS } from './backtestTypes';

const { Text } = Typography;
const { RangePicker } = DatePicker;

interface ConfigPanelProps {
  onStart: (config: BacktestConfig) => void;
  loading: boolean;
  onCancel: () => void;
  form: ReturnType<typeof Form.useForm<BacktestFormValues>>[0];
}

interface CascaderOption {
  value: string;
  label: React.ReactNode;
  children?: CascaderOption[];
  stock?: StockSearchItem;
  /** 整组回测选项所在的自选股分组名（value 为 '__group_all__' 时有效） */
  groupName?: string;
  isLeaf?: boolean;
}

/** 整组回测叶子的 value 前缀（实际 value 需拼接分组名以保证全树唯一） */
const GROUP_ALL_VALUE_PREFIX = '__group_all__';

/** 生成整组回测叶子的唯一 value */
function groupAllValue(groupName: string): string {
  return `${GROUP_ALL_VALUE_PREFIX}${groupName}`;
}

/** 判断某个 value 是否为整组回测叶子，并返回其分组名 */
function parseGroupAllValue(value: string): string | null {
  if (value.startsWith(GROUP_ALL_VALUE_PREFIX)) {
    return value.slice(GROUP_ALL_VALUE_PREFIX.length);
  }
  return null;
}

const DEFAULT_STOCK: StockSearchItem = { stock_code: '000001', stock_name: '平安银行' };

const BacktestConfigPanel: React.FC<ConfigPanelProps> = ({ onStart, form }) => {
  const { keyword: searchKeyword, setKeyword: setSearchKeyword, options: searchOptions, loading: searchLoading } = useStockSearch(300);
  const [cascaderValue, setCascaderValue] = useState<string[]>([]);
  /** 级联选择器输入框显示的文本（整组回测时显示分组提示，单股时显示代码+名称） */
  const [cascaderLabel, setCascaderLabel] = useState<string>(`${DEFAULT_STOCK.stock_code} ${DEFAULT_STOCK.stock_name}`);
  const [backtestVersion, setBacktestVersion] = useState(0);
  const [watchlistNames, setWatchlistNames] = useState<Record<string, string>>({});
  const [customIndicators, setCustomIndicators] = useState<CustomIndicator[]>([]);
  /** 自编卖出策略列表（卖出策略下拉「自编卖出策略」分组来源） */
  const [customSellStrategies, setCustomSellStrategies] = useState<CustomSellStrategy[]>([]);

  const { state: watchlistState, allGroups: watchlistGroups } = useWatchlist();

  // 读取系统设置中的全局默认值
  const globalDefaults = getBacktestDefaults();

  const initialValues: Partial<BacktestFormValues> = {
    stockCode: DEFAULT_STOCK.stock_code,
    stockName: DEFAULT_STOCK.stock_name,
    dateRange: [dayjs('2025-01-01'), dayjs()],
    capital: DEFAULT_BACKTEST_CONFIG.capital ?? 100000,
    indicatorId: undefined,
  };

  // 加载自选股名称（自选股只保存 code，需要反查 name；按市场分组请求避免跨市场查不到）
  useEffect(() => {
    const codes = watchlistGroups.flatMap((g) => watchlistState.stocks[g] || []);
    if (codes.length === 0) {
      setWatchlistNames({});
      return;
    }
    let cancelled = false;

    // 按市场分桶，避免单一 market 默认 cn 时港股/美股查不到
    const buckets: Record<MarketKey, string[]> = { cn: [], hk: [], us: [] };
    for (const c of codes) {
      const mkt = inferMarketKey(c) ?? 'cn';
      buckets[mkt].push(c);
    }

    (async () => {
      const map: Record<string, string> = {};
      try {
        // 各市场分别请求（cn 不显式传 market 兼容旧后端默认值）
        const tasks = (Object.keys(buckets) as MarketKey[])
          .filter((m) => buckets[m].length > 0)
          .map((m) =>
            fetchStocks({
              stock_codes: buckets[m].join(','),
              limit: buckets[m].length,
              ...(m !== 'cn' ? { market: m } : {}),
            }).catch(() => ({ items: [] })),
          );
        const results = await Promise.all(tasks);
        for (const res of results) {
          for (const item of res.items ?? []) {
            map[item.stock_code] = item.stock_name;
          }
        }
      } catch {
        // 静默降级
      }
      if (!cancelled) setWatchlistNames(map);
    })();

    return () => { cancelled = true; };
  }, [watchlistGroups, watchlistState.stocks]);

  // 加载自编指标列表（每次组件显示时重新加载，确保与系统配置页同步）
  useEffect(() => {
    const loadIndicators = () => {
      setCustomIndicators(listCustomIndicators());
    };
    
    loadIndicators();
    
    // 监听页面可见性变化，当用户从其他页面返回时重新加载
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadIndicators();
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    // 监听 storage 事件，当其他页面修改 localStorage 时重新加载
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'qt_custom_indicators_v1_mock_user_default') {
        loadIndicators();
      }
    };
    
    window.addEventListener('storage', handleStorageChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  // 加载自编卖出策略列表（卖出策略下拉分组数据源）
  useEffect(() => {
    setCustomSellStrategies(listCustomSellStrategies());
  }, []);

  // 初始化 cascaderValue：优先在回测列表或自选股中定位默认股票
  useEffect(() => {
    const backtestList = getBacktestList();
    if (backtestList.some((s) => s.stock_code === DEFAULT_STOCK.stock_code)) {
      setCascaderValue(['__backtest__', DEFAULT_STOCK.stock_code]);
      return;
    }
    for (const groupName of watchlistGroups) {
      const codes = watchlistState.stocks[groupName] || [];
      if (codes.includes(DEFAULT_STOCK.stock_code)) {
        setCascaderValue([`__watchlist_group__${groupName}`, DEFAULT_STOCK.stock_code]);
        return;
      }
    }
    // 都不存在时，使用默认分组
    setCascaderValue(['__default__', DEFAULT_STOCK.stock_code]);
  }, [watchlistGroups, watchlistState.stocks, backtestVersion]);

  // 合并回测列表 + 自选股分组 + 搜索结果，生成 Cascader 树
  const cascaderOptions = useMemo<CascaderOption[]>(() => {
    const backtestList = getBacktestList();
    const options: CascaderOption[] = [];

    // 默认推荐
    options.push({
      value: '__default__',
      label: '默认',
      children: [{
        value: DEFAULT_STOCK.stock_code,
        label: `${DEFAULT_STOCK.stock_code} ${DEFAULT_STOCK.stock_name}`,
        stock: DEFAULT_STOCK,
        isLeaf: true,
      }],
    });

    // 回测列表
    if (backtestList.length > 0) {
      options.push({
        value: '__backtest__',
        label: (
          <span>
            回测列表 <span className="text-xs text-text-secondary">({backtestList.length})</span>
          </span>
        ),
        children: backtestList.map((item) => ({
          value: item.stock_code,
          label: (
            <div className="flex items-center justify-between gap-4">
              <span>{item.stock_code} {item.stock_name}</span>
              <Tooltip title="从回测列表移除">
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<CloseOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFromBacktestList(item.stock_code);
                    setBacktestVersion((v) => v + 1);
                    const currentCode = form.getFieldValue('stockCode');
                    if (currentCode === item.stock_code) {
                      form.setFieldsValue({ stockCode: '', stockName: '' });
                      setCascaderValue([]);
                    }
                  }}
                />
              </Tooltip>
            </div>
          ),
          stock: {
            stock_code: item.stock_code,
            stock_name: item.stock_name,
          },
          isLeaf: true,
        })),
      });
    }

    // 自选股分组：直接作为一级选项，点击分组后二级菜单展示整组回测 + 个股
    for (const groupName of watchlistGroups) {
      const codes = watchlistState.stocks[groupName] || [];
      if (codes.length === 0) continue;
      options.push({
        value: `__watchlist_group__${groupName}`,
        label: `${groupName} (${codes.length})`,
        children: [
          // 整组回测选项：一键选择整个自选股分组
          {
            value: groupAllValue(groupName),
            label: (
              <span className="flex items-center justify-between gap-4">
                <span className="font-medium">🎯 回测整个分组</span>
                <span className="text-xs text-text-secondary">{codes.length} 只</span>
              </span>
            ),
            groupName,
            isLeaf: true,
          },
          ...codes.map((code) => ({
            value: code,
            label: watchlistNames[code]
              ? `${code} ${watchlistNames[code]}`
              : code,
            stock: {
              stock_code: code,
              stock_name: watchlistNames[code] ?? '',
            },
            isLeaf: true,
          })),
        ],
      });
    }

    // 搜索结果
    if (searchOptions.length > 0) {
      options.push({
        value: '__search__',
        label: `搜索结果 "${searchKeyword}"`,
        children: searchOptions.map((stock) => ({
          value: stock.stock_code,
          label: `${stock.stock_code} ${stock.stock_name}`,
          stock,
          isLeaf: true,
        })),
      });
    }

    return options;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchOptions, backtestVersion, watchlistGroups, watchlistState.stocks, watchlistNames]);

  const handleCascaderChange = (value: (string | number)[], selectedOptions: CascaderOption[]) => {
    const leaf = selectedOptions[selectedOptions.length - 1];
    if (!leaf) return;

    // 整组回测：选择整个自选股分组
    const leafValue = String(leaf.value ?? '');
    const allGroupName = parseGroupAllValue(leafValue);
    if (allGroupName && allGroupName.length > 0) {
      const codes = watchlistState.stocks[allGroupName] || [];
      const stocks: BacktestStock[] = codes.map((code) => ({
        stockCode: code,
        stockName: watchlistNames[code] ?? '',
      }));
      if (stocks.length === 0) return;
      setCascaderValue(value.map(String));
      setCascaderLabel(`🎯 ${allGroupName} 整组 (${stocks.length}只)`);
      form.setFieldsValue({
        stockCode: stocks[0].stockCode,
        stockName: stocks[0].stockName,
        stocks,
      });
      return;
    }

    // 单只股票
    if (!leaf?.stock) return;
    setCascaderValue(value.map(String));
    setCascaderLabel(`${leaf.stock.stock_code} ${leaf.stock.stock_name}`);
    form.setFieldsValue({
      stockCode: leaf.stock.stock_code,
      stockName: leaf.stock.stock_name,
      stocks: undefined,
    });
  };

  const handleCascaderSearch = (value: string) => {
    setSearchKeyword(value);
  };

  const sellStrategyOptions = useMemo(
    () => [
      {
        label: '系统预设',
        options: (Object.keys(SELL_STRATEGY_LABELS) as SellStrategy[])
          .filter((s) => s !== 'custom')
          .map((key) => ({ value: key, label: SELL_STRATEGY_LABELS[key] })),
      },
      ...(customSellStrategies.length > 0
        ? [{
            label: '自编卖出策略',
            options: customSellStrategies.map((s) => ({ value: `custom_${s.id}`, label: s.name })),
          }]
        : []),
    ],
    [customSellStrategies],
  );

  // 可能为 custom_<id> 前缀（自编卖出策略），需放宽为 string
  const [selectedSellStrategy, setSelectedSellStrategy] = useState<string>(
    (globalDefaults.sellStrategy as SellStrategy) ?? 'trailing_stop',
  );

  const handleIndicatorChange = (value: string) => {
    form.setFieldsValue({ indicatorId: value });
  };

  const handleFinish = (values: BacktestFormValues) => {
    const [startDate, endDate] = (values.dateRange ?? []).map((d: dayjs.Dayjs) => d.format('YYYY-MM-DD'));
    const indicatorId = values.indicatorId;
    const strategy = (values.sellStrategy as string) ?? selectedSellStrategy;

    // 构建买入条件：支持自编指标和系统预设
    let buyCondition: BacktestCondition;
    if (indicatorId && indicatorId.startsWith('preset_')) {
      const presetId = indicatorId.replace('preset_', '');
      const preset = PRESET_CONDITIONS.find((p) => p.id === presetId);
      buyCondition = preset
        ? { type: 'preset', presetId: preset.id, presetName: preset.name }
        : { type: 'preset', presetId: '', presetName: '' };
    } else {
      const rawId = indicatorId?.replace('custom_', '');
      const indicator = customIndicators.find((i) => i.id === rawId);
      buyCondition = indicator
        ? {
            type: 'custom',
            indicatorId: indicator.id,
            indicatorName: indicator.name,
            formula: indicator.formula,
            // 透传算子+默认阈值，使回测判定口径与选股视图一致
            operator: indicator.operator,
            threshold: indicator.defaultThreshold,
          }
        : { type: 'custom', indicatorId: '', indicatorName: '', formula: '' };
    }

    // 构建卖出策略：内置策略 or 自编卖出策略（custom_<id>）
    let sellStrategy: BacktestConfig['sellStrategy'] = strategy as BacktestConfig['sellStrategy'];
    let customSellStrategy: BacktestConfig['customSellStrategy'];
    if (strategy.startsWith('custom_')) {
      const sid = strategy.slice('custom_'.length);
      const found = customSellStrategies.find((s) => s.id === sid);
      if (found) {
        sellStrategy = 'custom';
        customSellStrategy = {
          type: 'custom',
          strategyId: found.id,
          strategyName: found.name,
          formula: found.formula,
          operator: found.operator,
          threshold: found.defaultThreshold,
        };
      } else {
        // 策略已被删除 → 回退内置，避免空公式
        sellStrategy = 'trailing_stop';
        customSellStrategy = undefined;
      }
    }

    const config: BacktestConfig = {
      stockCode: values.stockCode ?? '',
      stockName: values.stockName ?? '',
      stocks: Array.isArray(values.stocks) && values.stocks.length > 0 ? values.stocks : undefined,
      startDate,
      endDate,
      capital: values.capital ?? DEFAULT_BACKTEST_CONFIG.capital ?? 100000,
      buyCondition,
      sellStrategy,
      customSellStrategy,
      layeredTPParams:
        strategy === 'layered_take_profit'
          ? (values.layeredTPParams ?? DEFAULT_LAYERED_TP_PARAMS)
          : undefined,
      trailingStopPct: values.trailingStopPct ?? globalDefaults.trailingStopPct,
      atrPeriod: values.atrPeriod ?? globalDefaults.atrPeriod,
      atrMultiplier: values.atrMultiplier ?? globalDefaults.atrMultiplier,
      emaShort: values.emaShort ?? globalDefaults.emaShort,
      emaLong: values.emaLong ?? globalDefaults.emaLong,
      // 回测参数统一从系统配置页签"回测设置"读取
      indicatorParams: { ...globalDefaults.indicatorParams } as IndicatorParams,
      executionPrice: globalDefaults.executionPrice,
      maxDeferDays: globalDefaults.maxDeferDays,
      feeRate: globalDefaults.feeRate,
      slippage: globalDefaults.slippage,
      riskFreeRate: globalDefaults.riskFreeRate,
    };
    onStart(config);
  };

  return (
    <>
      <Form form={form} layout="vertical" initialValues={initialValues} onFinish={handleFinish}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* 股票选择 —— 级联菜单：回测列表（可删除）、自选股分组、搜索 */}
        <Card size="small" title="股票选择">
          <Form.Item label="股票代码/名称">
            <Cascader
              value={cascaderValue}
              options={cascaderOptions}
              onChange={handleCascaderChange as any}
              onSearch={handleCascaderSearch}
              showSearch
              changeOnSelect={false}
              placeholder="选择回测列表/自选股分组，或输入代码搜索"
              expandTrigger="click"
              style={{ width: '100%' }}
              displayRender={() => cascaderLabel}
              dropdownRender={(menu) => (
                <div>
                  {searchLoading && (
                    <div className="px-3 py-2 text-xs text-text-secondary">
                      <Spin size="small" /> 搜索中...
                    </div>
                  )}
                  {menu}
                </div>
              )}
              data-testid="stock-search-cascader"
            />
          </Form.Item>
          {/* 隐藏字段保存股票代码（含必填校验），供表单提交使用 */}
          <Form.Item name="stockCode" rules={[{ required: true, message: '请选择或搜索股票' }]} hidden>
            <Input />
          </Form.Item>
          {/* 隐藏字段保存名称，供表单提交使用 */}
          <Form.Item name="stockName" hidden>
            <Input />
          </Form.Item>
          {/* 隐藏字段保存批量回测股票列表（整组选择时填充），div 为占位承载组件 */}
          <Form.Item name="stocks" hidden>
            <div />
          </Form.Item>
        </Card>

        {/* 回测周期 */}
        <Card size="small" title="回测周期">
          <Form.Item
            name="dateRange"
            label="日期范围"
            rules={[
              { required: true, message: '请选择回测日期范围' },
              {
                validator: (_, value: [dayjs.Dayjs, dayjs.Dayjs] | undefined) => {
                  if (!value || !Array.isArray(value) || value.length !== 2) {
                    return Promise.reject(new Error('日期范围格式错误'));
                  }
                  const [start, end] = value;
                  if (!start || !end) {
                    return Promise.reject(new Error('请选择开始和结束日期'));
                  }
                  if (end.isBefore(start)) {
                    return Promise.reject(new Error('结束日期不能早于开始日期'));
                  }
                  if (start.isAfter(dayjs(), 'day') || end.isAfter(dayjs(), 'day')) {
                    return Promise.reject(new Error('日期范围不能包含未来日期'));
                  }
                  const maxRangeDays = 365 * 10;
                  if (end.diff(start, 'day') > maxRangeDays) {
                    return Promise.reject(new Error('单次回测周期不能超过 10 年'));
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <RangePicker style={{ width: '100%' }} popupClassName="single-month-range" />
          </Form.Item>
          <Form.Item name="capital" label="初始资金" rules={[{ required: true }]}>
            <InputNumber
              style={{ width: '100%' }}
              min={10000}
              step={10000}
              formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
            />
          </Form.Item>
        </Card>

        {/* 买入条件：支持系统预设和自编指标 */}
        <Card
          size="small"
          title={
            <Space>
              <span>买入条件</span>
              <Tag color="green">系统预设</Tag>
              <Tag color="blue">自编指标</Tag>
            </Space>
          }
        >
          <Form.Item
            name="indicatorId"
            label="选择买入条件"
            rules={[{ required: true, message: '请选择一个买入条件' }]}
          >
            <Select
              placeholder="请选择买入条件"
              onChange={handleIndicatorChange}
              style={{ width: '100%' }}
              allowClear
              dropdownStyle={{ maxHeight: 300, overflow: 'auto' }}
            >
              <Select.OptGroup label="系统预设">
                {PRESET_CONDITIONS.map((p) => (
                  <Select.Option key={`preset_${p.id}`} value={`preset_${p.id}`}>
                    {p.name}
                  </Select.Option>
                ))}
              </Select.OptGroup>
              <Select.OptGroup label="自编指标">
                {customIndicators.map((ind) => (
                  <Select.Option key={`custom_${ind.id}`} value={`custom_${ind.id}`}>
                    {ind.name}
                  </Select.Option>
                ))}
              </Select.OptGroup>
            </Select>
          </Form.Item>
          {customIndicators.length === 0 && PRESET_CONDITIONS.length === 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              暂无可用条件，请先在选股视图中创建自编指标。
            </Text>
          )}
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            系统预设：使用与选股视图一致的检测逻辑；自编指标：需返回每日信号数组。
          </Text>
        </Card>

        {/* 卖出策略：从策略回测复用 */}
        <Card
          size="small"
          title={
            <Space>
              <span>卖出策略</span>
              <Tag color="orange">可选</Tag>
            </Space>
          }
        >
          <Form.Item
            name="sellStrategy"
            label="选择卖出策略"
            initialValue={selectedSellStrategy}
          >
            <Select
              placeholder="请选择卖出策略"
              options={sellStrategyOptions}
              onChange={(val) => setSelectedSellStrategy(val as string)}
              style={{ width: '100%' }}
            />
          </Form.Item>

          {/* 自编卖出策略：显示所选策略说明 */}
          {selectedSellStrategy.startsWith('custom_') && (
            <div className="mb-2">
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                {(() => {
                  const s = customSellStrategies.find((x) => `custom_${x.id}` === selectedSellStrategy);
                  return s ? (
                    <>
                      已选策略：<Text strong>{s.name}</Text>
                      {s.description ? `（${s.description}）` : ''}
                    </>
                  ) : '所选策略已删除，将回退内置「高点回落移动止损」';
                })()}
              </Text>
            </div>
          )}

          {/* 内置策略参数区（仅当选择内置 3 项之一时显示） */}
          {!selectedSellStrategy.startsWith('custom_') && selectedSellStrategy === 'trailing_stop' && (
            <Form.Item
              name="trailingStopPct"
              label="回撤比例"
              initialValue={globalDefaults.trailingStopPct}
              tooltip="从持仓期间最高价回撤达到此比例时触发卖出"
            >
              <InputNumber
                style={{ width: '100%' }}
                min={0.01}
                max={0.30}
                step={0.01}
                formatter={(v) => `${((v ?? 0) as number * 100).toFixed(0)}%`}
                parser={(v) => parseFloat((v ?? '0').replace('%', '')) / 100 as any}
              />
            </Form.Item>
          )}

          {/* ATR吊灯参数（仅 atr_chandelier 时显示） */}
          {!selectedSellStrategy.startsWith('custom_') && selectedSellStrategy === 'atr_chandelier' && (
            <>
              <Form.Item
                name="atrPeriod"
                label="ATR周期"
                initialValue={globalDefaults.atrPeriod}
                tooltip="计算平均真实波幅的周期，默认14日"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={5}
                  max={30}
                  step={1}
                  addonAfter="日"
                />
              </Form.Item>
              <Form.Item
                name="atrMultiplier"
                label="ATR倍数"
                initialValue={globalDefaults.atrMultiplier}
                tooltip="止损线 = 最高价 - 倍数 × ATR，默认3倍"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={1}
                  max={5}
                  step={0.5}
                />
              </Form.Item>
            </>
          )}

          {/* 双均线参数（仅 ema_cross 时显示） */}
          {!selectedSellStrategy.startsWith('custom_') && selectedSellStrategy === 'ema_cross' && (
            <>
              <Form.Item
                name="emaShort"
                label="短期EMA周期"
                initialValue={globalDefaults.emaShort}
                tooltip="短期指数移动平均线周期，默认10日"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={3}
                  max={20}
                  step={1}
                  addonAfter="日"
                />
              </Form.Item>
              <Form.Item
                name="emaLong"
                label="长期EMA周期"
                initialValue={globalDefaults.emaLong}
                tooltip="长期指数移动平均线周期，默认30日"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={10}
                  max={60}
                  step={1}
                  addonAfter="日"
                />
              </Form.Item>
            </>
          )}

          {/* 分层止盈参数（仅 layered_take_profit 时显示，分组折叠） */}
          {!selectedSellStrategy.startsWith('custom_') && selectedSellStrategy === 'layered_take_profit' && (
            <>
              <div className="flex items-center justify-between mb-1">
                <Text type="secondary" style={{ fontSize: 12 }}>
                  分层止盈：TP1 卖 firstSellPct → 保本 → TP2 再卖 → 底仓跟踪止盈
                </Text>
                <Button
                  size="small"
                  onClick={() => form.setFieldsValue({ layeredTPParams: { ...DEFAULT_LAYERED_TP_PARAMS } })}
                >
                  恢复默认参数
                </Button>
              </div>
              <Collapse
                ghost
                size="small"
                items={[
                  {
                    key: 'c1',
                    label: '建仓期 — 风控参数',
                    children: (
                      <div className="space-y-2">
                        <Form.Item name={['layeredTPParams', 'initialStopLossPct']} label="初始止损比例" initialValue={DEFAULT_LAYERED_TP_PARAMS.initialStopLossPct}
                          tooltip="买入后跌破该比例即止损离场">
                          <InputNumber style={{ width: '100%' }} min={-0.3} max={-0.01} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'maxHoldDays']} label="时间止损（交易日）" initialValue={DEFAULT_LAYERED_TP_PARAMS.maxHoldDays}
                          tooltip="仅建仓期生效：买入后 N 个交易日未触发止盈则平仓">
                          <InputNumber style={{ width: '100%' }} min={5} max={60} step={1} addonAfter="日" />
                        </Form.Item>
                      </div>
                    ),
                  },
                  {
                    key: 'c2',
                    label: '第一锁定（TP1）— 收回本金',
                    children: (
                      <div className="space-y-2">
                        <Form.Item name={['layeredTPParams', 'firstProfitPct']} label="触发涨幅" initialValue={DEFAULT_LAYERED_TP_PARAMS.firstProfitPct}>
                          <InputNumber style={{ width: '100%' }} min={0.02} max={0.2} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'firstSellPct']} label="卖出比例" initialValue={DEFAULT_LAYERED_TP_PARAMS.firstSellPct}>
                          <InputNumber style={{ width: '100%' }} min={0.1} max={0.5} step={0.05} />
                        </Form.Item>
                        <Text type="secondary" style={{ fontSize: 11 }}>卖出后止损自动上移至成本价（保本）</Text>
                      </div>
                    ),
                  },
                  {
                    key: 'c3',
                    label: '第二锁定（TP2）— 锁定满意利润',
                    children: (
                      <div className="space-y-2">
                        <Form.Item name={['layeredTPParams', 'secondProfitPct']} label="触发涨幅" initialValue={DEFAULT_LAYERED_TP_PARAMS.secondProfitPct}>
                          <InputNumber style={{ width: '100%' }} min={0.05} max={0.4} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'secondSellPct']} label="卖出比例" initialValue={DEFAULT_LAYERED_TP_PARAMS.secondSellPct}>
                          <InputNumber style={{ width: '100%' }} min={0.1} max={0.5} step={0.05} />
                        </Form.Item>
                        <Text type="secondary" style={{ fontSize: 11 }}>卖出后止损线上移，保证这笔交易至少赚 lockProfitPct</Text>
                      </div>
                    ),
                  },
                  {
                    key: 'c4',
                    label: '无限续航 — 底仓跟踪止盈',
                    children: (
                      <div className="space-y-2">
                        <Form.Item name={['layeredTPParams', 'lockProfitPct']} label="锁定利润" initialValue={DEFAULT_LAYERED_TP_PARAMS.lockProfitPct}>
                          <InputNumber style={{ width: '100%' }} min={0.01} max={0.15} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'baseTrailingPct']} label="TP1后底仓回撤" initialValue={DEFAULT_LAYERED_TP_PARAMS.baseTrailingPct}
                          tooltip="TP1 卖出后剩余底仓从持仓期最高点回撤该比例即清仓。给足爆发空间并快速锁利，默认 8%">
                          <InputNumber style={{ width: '100%' }} min={0.03} max={0.2} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'trailingDrawdownPct']} label="TP2后峰值回撤" initialValue={DEFAULT_LAYERED_TP_PARAMS.trailingDrawdownPct}>
                          <InputNumber style={{ width: '100%' }} min={0.02} max={0.15} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'maPeriod']} label="均线周期" initialValue={DEFAULT_LAYERED_TP_PARAMS.maPeriod}>
                          <Select
                            options={[
                              { value: 5, label: 'MA5' },
                              { value: 10, label: 'MA10' },
                              { value: 20, label: 'MA20' },
                              { value: 60, label: 'MA60' },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'maConfirmDays']} label="均线确认天数" initialValue={DEFAULT_LAYERED_TP_PARAMS.maConfirmDays}>
                          <InputNumber style={{ width: '100%' }} min={1} max={5} step={1} addonAfter="日" />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'maExceptionDropPct']} label="均线例外跌幅" initialValue={DEFAULT_LAYERED_TP_PARAMS.maExceptionDropPct}
                          tooltip="单日跌幅超过此值不等确认直接卖">
                          <InputNumber style={{ width: '100%' }} min={0.03} max={0.15} step={0.01} />
                        </Form.Item>
                        <Form.Item name={['layeredTPParams', 'stopSlippagePct']} label="止损滑点" initialValue={DEFAULT_LAYERED_TP_PARAMS.stopSlippagePct}>
                          <InputNumber style={{ width: '100%' }} min={0} max={0.05} step={0.005} />
                        </Form.Item>
                        <Text type="secondary" style={{ fontSize: 11 }}>跟踪线 = max(锁定利润, 峰值回撤)，谁先触发谁出场</Text>
                      </div>
                    ),
                  },
                ]}
              />
            </>
          )}

          {/* 管理入口已迁移至「系统设置 → 自编指标 → 卖出策略」 */}
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            自编卖出策略可在「系统设置 → 自编指标 → 卖出策略」中管理。
          </Text>
        </Card>
      </div>
      </Form>
    </>
  );
};

export default BacktestConfigPanel;
