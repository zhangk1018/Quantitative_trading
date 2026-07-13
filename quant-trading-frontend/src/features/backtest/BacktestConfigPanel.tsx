// BacktestConfigPanel.tsx — 左侧策略配置面板（Form 重构）

import React, { useState, useMemo } from 'react';
import {
  Card, Select, DatePicker, Input, InputNumber, AutoComplete, Spin, Space, Divider, Button,
  Collapse, Radio, Tag, Tooltip, Typography, Form,
} from 'antd';
import { PlusOutlined, DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { BacktestConfig, BacktestCondition, ConditionFieldKey, IndicatorParams } from './backtestTypes';
import {
  BUY_CONDITION_KEYS, CONDITION_LABEL_MAP, DEFAULT_BACKTEST_CONFIG,
  DEFAULT_INDICATOR_PARAMS,
} from './backtestTypes';
import { useStockSearch } from './useStockSearch';
import { getBacktestList } from './backtestListStorage';
import { getBacktestDefaults } from './backtestSettingsStorage';
import type { StockSearchItem } from '../stock-detail/api';

const { Text } = Typography;
const { RangePicker } = DatePicker;
const { Panel } = Collapse;

interface ConfigPanelProps {
  onStart: (config: BacktestConfig) => void;
  loading: boolean;
  onCancel: () => void;
  form: ReturnType<typeof Form.useForm<BacktestConfig>>[0];
}

interface AutoCompleteOption {
  value: string;
  label: React.ReactNode;
  stock: StockSearchItem;
  isBacktestList: boolean;
}

const BacktestConfigPanel: React.FC<ConfigPanelProps> = ({ onStart, loading, onCancel, form }) => {
  const { keyword, setKeyword, options: searchOptions, loading: searchLoading } = useStockSearch(300);
  const [selectedStock, setSelectedStock] = useState<StockSearchItem | null>(null);

  // 读取系统设置中的全局默认值
  const globalDefaults = getBacktestDefaults();

  const initialValues: Partial<BacktestConfig> & { dateRange?: [dayjs.Dayjs, dayjs.Dayjs] } = {
    stockCode: '000001',
    stockName: '平安银行',
    dateRange: [dayjs('2025-01-01'), dayjs('2026-07-01')],
    capital: DEFAULT_BACKTEST_CONFIG.capital ?? 100000,
    buyConditions: [{ fieldKey: 'macd_golden_cross', label: 'MACD金叉' }],
    executionPrice: globalDefaults.executionPrice,
    signalConfirmBars: globalDefaults.signalConfirmBars,
    maxDeferDays: globalDefaults.maxDeferDays,
    feeRate: globalDefaults.feeRate,
    slippage: globalDefaults.slippage,
    riskFreeRate: globalDefaults.riskFreeRate,
    indicatorParams: globalDefaults.indicatorParams,
  };

  // 合并回测列表 + 搜索结果，优先显示回测列表
  const mergedOptions = useMemo<AutoCompleteOption[]>(() => {
    const backtestList = getBacktestList();
    const backtestOptions: AutoCompleteOption[] = backtestList.map(item => ({
      value: item.stock_code,
      label: (
        <div className="flex items-center justify-between gap-4">
          <span className="font-mono">{item.stock_code}</span>
          <span className="text-text-secondary flex-1">{item.stock_name}</span>
          <span className="text-xs text-color-accent bg-color-accent/10 px-1.5 py-0.5 rounded">回测列表</span>
        </div>
      ),
      stock: {
        stock_code: item.stock_code,
        stock_name: item.stock_name,
      },
      isBacktestList: true,
    }));

    const searchOptionsWithGroup: AutoCompleteOption[] = searchOptions.map(stock => ({
      value: stock.stock_code,
      label: (
        <div className="flex items-center justify-between gap-4">
          <span className="font-mono">{stock.stock_code}</span>
          <span className="text-text-secondary flex-1">{stock.stock_name}</span>
          {stock.close !== undefined && (
            <span className="text-sm text-text-secondary">¥{stock.close.toFixed(2)}</span>
          )}
        </div>
      ),
      stock,
      isBacktestList: false,
    }));

    // 去重：同一个股票如果既在回测列表又在搜索结果中，保留回测列表项
    const existingCodes = new Set(backtestOptions.map(o => o.value));
    const filteredSearch = searchOptionsWithGroup.filter(o => !existingCodes.has(o.value));

    return [...backtestOptions, ...filteredSearch];
  }, [searchOptions]);

  const handleSelect = (value: string, option: AutoCompleteOption) => {
    const { stock } = option;
    setSelectedStock(stock);
    form.setFieldsValue({
      stockCode: stock.stock_code,
      stockName: stock.stock_name,
    });
    setKeyword(`${stock.stock_code} ${stock.stock_name}`);
  };

  const handleSearch = (value: string) => {
    setKeyword(value);
    if (!value.trim()) {
      setSelectedStock(null);
      form.setFieldsValue({
        stockCode: '',
        stockName: '',
      });
    } else {
      // 手动输入时，将输入值作为 stockCode 提交
      form.setFieldsValue({ stockCode: value });
    }
  };

  const handleFinish = (values: any) => {
    // 转换日期
    const [startDate, endDate] = values.dateRange.map((d: dayjs.Dayjs) => d.format('YYYY-MM-DD'));
    const config: BacktestConfig = {
      ...values,
      startDate,
      endDate,
      buyConditions: values.buyConditions as BacktestCondition[],
      // 合并默认指标参数，确保 ma5/ma10/ma60/bollPeriod 等非表单字段不丢失
      indicatorParams: { ...globalDefaults.indicatorParams, ...values.indicatorParams } as IndicatorParams,
      // Collapse.Panel 已废弃，内部字段可能未注册，强制补齐默认值
      executionPrice: values.executionPrice ?? globalDefaults.executionPrice,
      signalConfirmBars: values.signalConfirmBars ?? globalDefaults.signalConfirmBars,
      maxDeferDays: values.maxDeferDays ?? globalDefaults.maxDeferDays,
      feeRate: values.feeRate ?? globalDefaults.feeRate,
      slippage: values.slippage ?? globalDefaults.slippage,
      riskFreeRate: values.riskFreeRate ?? globalDefaults.riskFreeRate,
    };
    onStart(config);
  };

  // 动态条件字段
  const conditions = Form.useWatch('buyConditions', form) || [];

  const addCondition = () => {
    const usedKeys = new Set(conditions.map((c: BacktestCondition) => c.fieldKey));
    const available = BUY_CONDITION_KEYS.filter((k) => !usedKeys.has(k));
    if (available.length === 0) return;
    const newCond = { fieldKey: available[0], label: CONDITION_LABEL_MAP[available[0]] };
    form.setFieldsValue({ buyConditions: [...conditions, newCond] });
  };

  const removeCondition = (index: number) => {
    const updated = conditions.filter((_: any, i: number) => i !== index);
    form.setFieldsValue({ buyConditions: updated });
  };

  const updateCondition = (index: number, key: ConditionFieldKey) => {
    const updated = [...conditions];
    updated[index] = { fieldKey: key, label: CONDITION_LABEL_MAP[key] };
    form.setFieldsValue({ buyConditions: updated });
  };

  return (
    <Form form={form} layout="vertical" initialValues={initialValues} onFinish={handleFinish}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* 股票选择 — 支持代码/名称搜索，回测列表优先显示 */}
        <Card size="small" title="股票选择">
          <Form.Item name="stockCode" label="股票代码/名称" rules={[{ required: true, message: '请选择或搜索股票' }]}>
            <AutoComplete
              placeholder="输入股票代码或名称，优先显示回测列表"
              value={keyword || undefined}
              onSearch={handleSearch}
              onSelect={handleSelect as any}
              options={mergedOptions}
              notFoundContent={searchLoading ? <Spin size="small" /> : '无匹配结果'}
              allowClear
              style={{ width: '100%' }}
              popupMatchSelectWidth={true}
              data-testid="stock-search-autocomplete"
            />
          </Form.Item>
          {/* 隐藏字段保存名称，供表单提交使用 */}
          <Form.Item name="stockName" hidden>
            <Input />
          </Form.Item>
        </Card>

        {/* 回测周期 */}
        <Card size="small" title="回测周期">
          <Form.Item name="dateRange" label="日期范围" rules={[{ required: true }]}>
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

        {/* 买入条件 */}
        <Card
          size="small"
          title={
            <Space>
              <span>买入条件</span>
              <Tag>{conditions.length}/5</Tag>
            </Space>
          }
          extra={
            <Button size="small" icon={<PlusOutlined />} onClick={addCondition} disabled={conditions.length >= 5}>
              添加
            </Button>
          }
        >
          <Form.List name="buyConditions">
            {(fields, { add, remove }) => (
              <Space direction="vertical" style={{ width: '100%' }}>
                {fields.map((field, index) => (
                  <Space key={field.key} style={{ width: '100%' }}>
                    <Form.Item
                      {...field}
                      name={[field.name, 'fieldKey']}
                      style={{ flex: 1, marginBottom: 0 }}
                    >
                      <Select
                        onChange={(v) => updateCondition(index, v)}
                        options={BUY_CONDITION_KEYS.map((k) => ({
                          value: k,
                          label: CONDITION_LABEL_MAP[k],
                          disabled: conditions.some((c2: BacktestCondition, j: number) => c2.fieldKey === k && j !== index),
                        }))}
                      />
                    </Form.Item>
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => removeCondition(index)}
                      disabled={conditions.length <= 1}
                    />
                  </Space>
                ))}
                {conditions.length > 1 && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    条件之间为 AND 关系，所有条件同时满足时触发买入
                  </Text>
                )}
              </Space>
            )}
          </Form.List>
        </Card>

        {/* 高级设置 */}
        <Collapse ghost size="small">
          <Panel header={<Space><SettingOutlined />高级设置</Space>} key="advanced">
            <Form.Item name="executionPrice" label="成交价模式">
              <Radio.Group>
                <Radio.Button value="next_open">T+1 开盘价</Radio.Button>
                <Radio.Button value="next_close">T+1 收盘价</Radio.Button>
              </Radio.Group>
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            <Form.Item name="signalConfirmBars" label="信号确认连续K线数">
              <InputNumber min={1} max={5} />
            </Form.Item>
            <Form.Item name="maxDeferDays" label="最大顺延天数">
              <InputNumber min={1} max={10} />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            <Form.Item name="feeRate" label="手续费率（万分之）">
              <InputNumber
                min={0} max={30} step={0.1}
                style={{ width: '100%' }}
                formatter={(v) => `${(Number(v) * 10000).toFixed(1)}`}
                parser={(v) => ((Number(v) || 0) / 10000) as 0 | 30}
              />
            </Form.Item>
            <Form.Item name="slippage" label="滑点（万分之）">
              <InputNumber
                min={0} max={30} step={0.1}
                style={{ width: '100%' }}
                formatter={(v) => `${(Number(v) * 10000).toFixed(1)}`}
                parser={(v) => ((Number(v) || 0) / 10000) as 0 | 30}
              />
            </Form.Item>
            <Form.Item
              name="riskFreeRate"
              label="无风险利率"
              tooltip="当前基准：3%（一年期国债参考值）"
            >
              <InputNumber min={0} max={0.1} step={0.01} />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            <Text type="secondary">指标参数</Text>
            <Space wrap>
              <Text style={{ fontSize: 12 }}>MACD:</Text>
              <Form.Item name={['indicatorParams', 'macdFast']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 60 }} min={2} max={50} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'macdSlow']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 60 }} min={2} max={100} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'macdSignal']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 60 }} min={2} max={50} />
              </Form.Item>
            </Space>
            <Space wrap>
              <Text style={{ fontSize: 12 }}>RSI:</Text>
              <Form.Item name={['indicatorParams', 'rsiPeriod']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 60 }} min={2} max={50} />
              </Form.Item>
            </Space>
            <Space wrap>
              <Text style={{ fontSize: 12 }}>MA:</Text>
              <Form.Item name={['indicatorParams', 'ma5']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={120} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'ma10']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={120} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'ma20']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={120} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'ma60']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={120} />
              </Form.Item>
            </Space>
            <Space wrap>
              <Text style={{ fontSize: 12 }}>BOLL:</Text>
              <Form.Item name={['indicatorParams', 'bollPeriod']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 60 }} min={5} max={120} />
              </Form.Item>
              <Text style={{ fontSize: 12 }}>标准差:</Text>
              <Form.Item name={['indicatorParams', 'bollStd']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 60 }} min={0.5} max={5} step={0.5} />
              </Form.Item>
            </Space>
            <Space wrap>
              <Text style={{ fontSize: 12 }}>KDJ:</Text>
              <Form.Item name={['indicatorParams', 'kdjK']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={30} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'kdjD']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={30} />
              </Form.Item>
              <Form.Item name={['indicatorParams', 'kdjJ']} style={{ display: 'inline-block', marginBottom: 0 }}>
                <InputNumber size="small" style={{ width: 55 }} min={2} max={30} />
              </Form.Item>
            </Space>
          </Panel>
        </Collapse>
      </div>
    </Form>
  );
};

export default BacktestConfigPanel;