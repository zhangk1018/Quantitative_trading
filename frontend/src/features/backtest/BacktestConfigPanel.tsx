// BacktestConfigPanel.tsx — 左侧策略配置面板（Form 重构）

import React, { useEffect, useMemo, useState } from 'react';
import {
  Card, Select, DatePicker, Input, InputNumber, Cascader, Spin, Space, Button,
  Tag, Tooltip, Typography, Form,
} from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { BacktestConfig, BacktestFormValues, IndicatorParams, SellStrategy } from './backtestTypes';
import {
  DEFAULT_BACKTEST_CONFIG,
  SELL_STRATEGY_LABELS,
} from './backtestTypes';
import { useStockSearch } from './useStockSearch';
import { getBacktestList, removeFromBacktestList } from './backtestListStorage';
import { getBacktestDefaults } from './backtestSettingsStorage';
import { useWatchlist } from '../watchlist/store';
import { listCustomIndicators } from '../stock-picker/utils/customIndicatorStorage';
import type { CustomIndicator } from '../stock-picker/types/customIndicator';
import { fetchStocks } from '../stock-detail/api';
import type { StockSearchItem } from '../stock-detail/api';

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
  isLeaf?: boolean;
}

const DEFAULT_STOCK: StockSearchItem = { stock_code: '000001', stock_name: '平安银行' };

const BacktestConfigPanel: React.FC<ConfigPanelProps> = ({ onStart, form }) => {
  const { keyword: searchKeyword, setKeyword: setSearchKeyword, options: searchOptions, loading: searchLoading } = useStockSearch(300);
  const [cascaderValue, setCascaderValue] = useState<string[]>([]);
  const [backtestVersion, setBacktestVersion] = useState(0);
  const [watchlistNames, setWatchlistNames] = useState<Record<string, string>>({});
  const [customIndicators, setCustomIndicators] = useState<CustomIndicator[]>([]);

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

  // 加载自选股名称（自选股只保存 code，需要反查 name）
  useEffect(() => {
    const codes = watchlistGroups.flatMap((g) => watchlistState.stocks[g] || []);
    if (codes.length === 0) {
      setWatchlistNames({});
      return;
    }
    let cancelled = false;
    fetchStocks({ stock_codes: codes.join(','), limit: codes.length })
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, string> = {};
        for (const item of res.items) {
          map[item.stock_code] = item.stock_name;
        }
        setWatchlistNames(map);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
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

    // 自选股分组：直接作为一级选项，点击分组后二级菜单展示个股
    for (const groupName of watchlistGroups) {
      const codes = watchlistState.stocks[groupName] || [];
      if (codes.length === 0) continue;
      options.push({
        value: `__watchlist_group__${groupName}`,
        label: `${groupName} (${codes.length})`,
        children: codes.map((code) => ({
          value: code,
          label: `${code} ${watchlistNames[code] || code}`,
          stock: {
            stock_code: code,
            stock_name: watchlistNames[code] || code,
          },
          isLeaf: true,
        })),
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
    if (!leaf?.stock) return;
    setCascaderValue(value.map(String));
    form.setFieldsValue({
      stockCode: leaf.stock.stock_code,
      stockName: leaf.stock.stock_name,
    });
  };

  const handleCascaderSearch = (value: string) => {
    setSearchKeyword(value);
  };

  const indicatorOptions = useMemo(
    () =>
      customIndicators.map((ind) => ({
        value: ind.id,
        label: ind.name,
      })),
    [customIndicators],
  );

  const sellStrategyOptions = useMemo(
    () =>
      (Object.keys(SELL_STRATEGY_LABELS) as SellStrategy[]).map((key) => ({
        value: key,
        label: SELL_STRATEGY_LABELS[key],
      })),
    [],
  );

  const [selectedSellStrategy, setSelectedSellStrategy] = useState<SellStrategy>(
    (globalDefaults.sellStrategy as SellStrategy) ?? 'trailing_stop',
  );

  const handleIndicatorChange = (indicatorId: string) => {
    form.setFieldsValue({ indicatorId });
  };

  const handleFinish = (values: BacktestFormValues) => {
    const [startDate, endDate] = (values.dateRange ?? []).map((d: dayjs.Dayjs) => d.format('YYYY-MM-DD'));
    const indicator = customIndicators.find((i) => i.id === values.indicatorId);
    const strategy = (values.sellStrategy as SellStrategy) ?? selectedSellStrategy;
    const config: BacktestConfig = {
      stockCode: values.stockCode ?? '',
      stockName: values.stockName ?? '',
      startDate,
      endDate,
      capital: values.capital ?? DEFAULT_BACKTEST_CONFIG.capital ?? 100000,
      buyCondition: indicator
        ? { indicatorId: indicator.id, indicatorName: indicator.name, formula: indicator.formula }
        : { indicatorId: '', indicatorName: '', formula: '' },
      sellStrategy: strategy,
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
    <Form form={form} layout="vertical" initialValues={initialValues} onFinish={handleFinish}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* 股票选择 —— 级联菜单：回测列表（可删除）、自选股分组、搜索 */}
        <Card size="small" title="股票选择">
          <Form.Item name="stockCode" label="股票代码/名称" rules={[{ required: true, message: '请选择或搜索股票' }]}>
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
              displayRender={(labels) => labels[labels.length - 1] || ''}
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
          {/* 隐藏字段保存名称，供表单提交使用 */}
          <Form.Item name="stockName" hidden>
            <Input />
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

        {/* 买入条件：仅支持自编指标 */}
        <Card
          size="small"
          title={
            <Space>
              <span>买入条件</span>
              <Tag color="blue">自编指标</Tag>
            </Space>
          }
        >
          <Form.Item
            name="indicatorId"
            label="选择自编指标"
            rules={[{ required: true, message: '请选择一个自编指标作为买入条件' }]}
          >
            <Select
              placeholder="请选择自编指标"
              options={indicatorOptions}
              onChange={handleIndicatorChange}
              disabled={indicatorOptions.length === 0}
              style={{ width: '100%' }}
              allowClear
            />
          </Form.Item>
          {indicatorOptions.length === 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              暂无自编指标，请先在选股视图中创建。
            </Text>
          )}
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            脚本约定：返回每日信号数组，1 表示满足买入，0 表示不满足。
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
              onChange={(val) => setSelectedSellStrategy(val as SellStrategy)}
              style={{ width: '100%' }}
            />
          </Form.Item>

          {/* 高点回落参数（仅 trailing_stop 时显示） */}
          {selectedSellStrategy === 'trailing_stop' && (
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
          {selectedSellStrategy === 'atr_chandelier' && (
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
          {selectedSellStrategy === 'ema_cross' && (
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
        </Card>
      </div>
    </Form>
  );
};

export default BacktestConfigPanel;
