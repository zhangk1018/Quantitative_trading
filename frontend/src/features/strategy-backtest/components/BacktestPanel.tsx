// src/features/strategy-backtest/components/BacktestPanel.tsx
// 回测参数面板 — 区间选择 + 高级设置 + 开始按钮

import React, { useState } from 'react';
import {
  DatePicker,
  Button,
  Collapse,
  InputNumber,
  Select,
  Switch,
  Tooltip,
  Space,
} from 'antd';
import { PlayCircleOutlined, SettingOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { StrategyBacktestDefaults } from '../types';
import {
  saveStrategyBacktestDefaults,
  DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
  fenToWanYuan,
  wanYuanToFen,
  feeRateToDisplay,
  displayToFeeRate,
  stampDutyToDisplay,
  displayToStampDuty,
  slippageToDisplay,
  displayToSlippage,
  decimalToPct,
  pctToDecimal,
} from '../storage';

interface LayeredTPParams {
  initialStopLossPct: number;     // 初始止损比例（-0.08 = -8%）
  firstProfitPct: number;         // 第一止盈目标（0.08 = +8%）
  firstSellPct: number;           // 第一止盈卖出比例（0.25 = 25%）
  secondProfitPct: number;        // 第二止盈目标（0.15 = +15%）
  secondSellPct: number;          // 第二止盈卖出比例（0.25 = 25%）
  breakevenStopPct: number;       // TP1后保本止损比例（0.00 = 成本价，固定）
  lockProfitPct: number;          // TP2后锁定利润比例（0.06 = +6%）
  hardFloorPct: number;           // TP2后硬性底线安全阀（0.03 = +3%）
  trailingDrawdownPct: number;    // TP2后峰值回撤阈值（0.05 = 5%）
  maPeriod: number;               // 均线兜底周期（20）
  maConfirmDays: number;          // 均线破位确认天数（2）
  maExceptionDropPct: number;     // 均线例外单日跌幅（0.07 = 7%）
  maxHoldDays: number;            // 建仓期时间止损天数（20）
  stopSlippagePct: number;        // 止损成交价滑点（0.02 = 2%）
}

const DEFAULT_LAYERED_TP_PARAMS: LayeredTPParams = {
  initialStopLossPct: -0.08,
  firstProfitPct: 0.08,
  firstSellPct: 0.25,
  secondProfitPct: 0.15,
  secondSellPct: 0.25,
  breakevenStopPct: 0.00,
  lockProfitPct: 0.06,
  hardFloorPct: 0.03,
  trailingDrawdownPct: 0.05,
  maPeriod: 20,
  maConfirmDays: 2,
  maExceptionDropPct: 0.07,
  maxHoldDays: 20,
  stopSlippagePct: 0.02,
};

interface BacktestPanelProps {
  config: StrategyBacktestDefaults;
  onConfigChange: (config: StrategyBacktestDefaults) => void;
  onStart: () => void;
  dateRange: [dayjs.Dayjs, dayjs.Dayjs];
  onDateRangeChange: (range: [dayjs.Dayjs, dayjs.Dayjs]) => void;
  disabled?: boolean;
  strategyType?: 'filterTree' | 'filterTreeLayeredTP';
  onStrategyTypeChange?: (type: 'filterTree' | 'filterTreeLayeredTP') => void;
  layeredTPParams?: LayeredTPParams;
  onLayeredTPParamsChange?: (params: LayeredTPParams) => void;
}

const { RangePicker } = DatePicker;

const BacktestPanel: React.FC<BacktestPanelProps> = ({
  config, onConfigChange, onStart, dateRange, onDateRangeChange, disabled,
  strategyType = 'filterTree', onStrategyTypeChange,
  layeredTPParams = DEFAULT_LAYERED_TP_PARAMS, onLayeredTPParamsChange,
}) => {
  const [activePreset, setActivePreset] = useState<string>('1y');

  const handlePresetClick = (preset: string) => {
    setActivePreset(preset);
    const end = dayjs();
    let start: dayjs.Dayjs;
    switch (preset) {
      case '3m':
        start = end.subtract(3, 'month');
        break;
      case '6m':
        start = end.subtract(6, 'month');
        break;
      case '1y':
        start = end.subtract(1, 'year');
        break;
      case 'all':
        start = dayjs('2005-01-04');
        break;
      default:
        start = end.subtract(1, 'year');
    }
    onDateRangeChange([start, end]);
  };

  const handleDateChange = (_: unknown, dateStrings: [string, string]) => {
    if (dateStrings[0] && dateStrings[1]) {
      onDateRangeChange([dayjs(dateStrings[0]), dayjs(dateStrings[1])]);
      setActivePreset('');
    }
  };

  const updateConfig = (partial: Partial<StrategyBacktestDefaults>) => {
    const updated = { ...config, ...partial };
    onConfigChange(updated);
    saveStrategyBacktestDefaults(updated);
  };

  const presetBtns = [
    { key: '3m', label: '3月' },
    { key: '6m', label: '6月' },
    { key: '1y', label: '1年' },
    { key: 'all', label: '全部', tooltip: '全部（2005-01-04 起）' },
  ];

  const presetLabel = (item: { key: string; label: string; tooltip?: string }) => {
    const btn = (
      <Button
        key={item.key}
        size="small"
        type={activePreset === item.key ? 'primary' : 'default'}
        onClick={() => handlePresetClick(item.key)}
      >
        {item.label}
      </Button>
    );
    return item.tooltip ? <Tooltip key={item.key} title={item.tooltip}>{btn}</Tooltip> : btn;
  };

  return (
    <div className="bg-bg-panel rounded-lg border border-border-color p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium">回测参数</span>
        <Space size="small">
          <Button
            size="small"
            onClick={() => {
              onConfigChange({ ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS });
              saveStrategyBacktestDefaults(DEFAULT_STRATEGY_BACKTEST_DEFAULTS);
            }}
            disabled={disabled}
          >
            重置默认
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={onStart}
            disabled={disabled}
            loading={disabled}
            data-testid="start-backtest-btn"
          >
            开始回测
          </Button>
        </Space>
      </div>

      {/* 回测区间 */}
      <div className="mb-3">
        <div className="text-xs text-text-secondary mb-1">回测区间</div>
        <div className="flex items-center gap-2">
          <RangePicker
            value={dateRange}
            onChange={handleDateChange}
            size="small"
            disabled={disabled}
            disabledDate={(d) => d.isAfter(dayjs())}
          />
          <Space size="small">
            {presetBtns.map(presetLabel)}
          </Space>
        </div>
      </div>

      {/* 高级设置 */}
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: 'advanced',
            label: (
              <span className="text-xs">
                <SettingOutlined className="mr-1" />
                高级设置
              </span>
            ),
            children: (
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                {/* 策略类型选择 */}
                <div className="col-span-2 text-xs font-medium text-text-secondary mt-1 mb-0.5">策略类型</div>
                <div className="col-span-2 flex items-center justify-between">
                  <span className="text-xs">回测策略</span>
                  <Select
                    size="small"
                    value={strategyType}
                    onChange={(v) => onStrategyTypeChange?.(v)}
                    disabled={disabled}
                    style={{ width: 200 }}
                    options={[
                      { value: 'filterTree', label: '选股条件调仓（AST）' },
                      { value: 'filterTreeLayeredTP', label: '选股条件分层止盈' },
                    ]}
                  />
                </div>

                {/* 分层止盈参数 */}
                {strategyType === 'filterTreeLayeredTP' && (
                  <>
                    <div className="col-span-2 text-xs font-medium text-primary mt-1 mb-0.5">
                      建仓期 — 风控参数
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">初始止损比例</span>
                      <InputNumber
                        size="small" min={1} max={30} step={1}
                        value={Math.abs(layeredTPParams.initialStopLossPct) * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, initialStopLossPct: -v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `-${v}%`}
                        parser={(v) => parseFloat(v ?? '8')}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">
                        时间止损（交易日）
                        <Tooltip title="仅建仓期生效：买入后N个交易日未触发止盈则平仓">
                          <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                        </Tooltip>
                      </span>
                      <InputNumber
                        size="small" min={5} max={60} step={1}
                        value={layeredTPParams.maxHoldDays}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, maxHoldDays: v })}
                        disabled={disabled} style={{ width: 120 }}
                      />
                    </div>

                    <div className="col-span-2 text-xs font-medium text-primary mt-2 mb-0.5">
                      第一锁定 — 收回本金
                    </div>
                    <div className="col-span-2 pl-2 -mt-1 mb-1">
                      <span className="text-xs text-text-tertiary">卖出后止损自动上移至成本价（保本）</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">触发涨幅</span>
                      <InputNumber
                        size="small" min={2} max={20} step={1}
                        value={layeredTPParams.firstProfitPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, firstProfitPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `+${v}%`}
                        parser={(v) => parseFloat(v ?? '8')}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">卖出比例</span>
                      <InputNumber
                        size="small" min={10} max={50} step={5}
                        value={layeredTPParams.firstSellPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, firstSellPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `${v}%`}
                        parser={(v) => parseFloat(v ?? '25')}
                      />
                    </div>

                    <div className="col-span-2 text-xs font-medium text-primary mt-2 mb-0.5">
                      第二锁定 — 锁定满意利润
                    </div>
                    <div className="col-span-2 pl-2 -mt-1 mb-1">
                      <span className="text-xs text-text-tertiary">卖出后止损线上移至+6%（保证这笔交易至少赚6%）</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">触发涨幅</span>
                      <InputNumber
                        size="small" min={5} max={40} step={1}
                        value={layeredTPParams.secondProfitPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, secondProfitPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `+${v}%`}
                        parser={(v) => parseFloat(v ?? '15')}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">卖出比例</span>
                      <InputNumber
                        size="small" min={10} max={50} step={5}
                        value={layeredTPParams.secondSellPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, secondSellPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `${v}%`}
                        parser={(v) => parseFloat(v ?? '25')}
                      />
                    </div>

                    <div className="col-span-2 text-xs font-medium text-primary mt-2 mb-0.5">
                      无限续航 — 底仓跟踪止盈
                    </div>
                    <div className="col-span-2 pl-2 -mt-1 mb-1">
                      <span className="text-xs text-text-tertiary">跟踪线 = max(+6%锁定, 峰值回撤-5%)，谁先触发谁出场</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">
                        锁定利润
                        <Tooltip title="第二止盈后止损线上移至此，保证至少赚6%">
                          <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                        </Tooltip>
                      </span>
                      <InputNumber
                        size="small" min={1} max={15} step={1}
                        value={layeredTPParams.lockProfitPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, lockProfitPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `+${v}%`}
                        parser={(v) => parseFloat(v ?? '6')}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">峰值回撤</span>
                      <InputNumber
                        size="small" min={2} max={15} step={1}
                        value={layeredTPParams.trailingDrawdownPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, trailingDrawdownPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `-${v}%`}
                        parser={(v) => parseFloat(v ?? '5')}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">
                        均线周期
                        <Tooltip title="跌破该均线则清仓底仓">
                          <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                        </Tooltip>
                      </span>
                      <Select
                        size="small"
                        value={layeredTPParams.maPeriod}
                        onChange={(v) => onLayeredTPParamsChange?.({ ...layeredTPParams, maPeriod: v })}
                        disabled={disabled}
                        style={{ width: 120 }}
                        options={[
                          { value: 5, label: 'MA5' },
                          { value: 10, label: 'MA10' },
                          { value: 20, label: 'MA20' },
                          { value: 60, label: 'MA60' },
                        ]}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">
                        均线确认天数
                        <Tooltip title="连续N天跌破均线才触发">
                          <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                        </Tooltip>
                      </span>
                      <InputNumber
                        size="small" min={1} max={5} step={1}
                        value={layeredTPParams.maConfirmDays}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, maConfirmDays: v })}
                        disabled={disabled} style={{ width: 120 }}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">
                        均线例外跌幅
                        <Tooltip title="单日跌幅超过此值不等确认直接卖">
                          <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                        </Tooltip>
                      </span>
                      <InputNumber
                        size="small" min={3} max={15} step={1}
                        value={layeredTPParams.maExceptionDropPct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, maExceptionDropPct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `-${v}%`}
                        parser={(v) => parseFloat(v ?? '7')}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs">
                        止损滑点
                        <Tooltip title="保守回测：止损成交价相对触发价的滑点">
                          <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                        </Tooltip>
                      </span>
                      <InputNumber
                        size="small" min={0} max={5} step={0.5}
                        value={layeredTPParams.stopSlippagePct * 100}
                        onChange={(v) => v !== null && onLayeredTPParamsChange?.({ ...layeredTPParams, stopSlippagePct: v / 100 })}
                        disabled={disabled} style={{ width: 120 }}
                        formatter={(v) => `${v}%`}
                        parser={(v) => parseFloat(v ?? '2')}
                      />
                    </div>
                  </>
                )}

                {/* Card 1: 基础参数 */}
                <div className="col-span-2 text-xs font-medium text-text-secondary mt-1 mb-0.5">基础参数</div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">初始资金（万元）</span>
                  <InputNumber
                    size="small"
                    min={1}
                    max={999999}
                    value={fenToWanYuan(config.initialCapital)}
                    onChange={(v) => v && updateConfig({ initialCapital: wanYuanToFen(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">基准指数</span>
                  <Select
                    size="small"
                    value={config.benchmarkCode}
                    onChange={(v) => updateConfig({ benchmarkCode: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    options={[
                      { value: '000300.SH', label: '沪深300' },
                      { value: '000905.SH', label: '中证500' },
                      { value: '000688.SH', label: '科创50' },
                    ]}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">无风险利率（年化%）</span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={10}
                    step={0.1}
                    value={decimalToPct(config.riskFreeRate)}
                    onChange={(v) => v !== null && updateConfig({ riskFreeRate: pctToDecimal(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">预热天数</span>
                  <InputNumber
                    size="small"
                    min={20}
                    max={250}
                    value={config.warmupDays}
                    onChange={(v) => v && updateConfig({ warmupDays: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>

                {/* Card 2: 调仓与仓位 */}
                <div className="col-span-2 text-xs font-medium text-text-secondary mt-2 mb-0.5">调仓与仓位</div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">调仓频率</span>
                  <Select
                    size="small"
                    value={config.rebalanceInterval}
                    onChange={(v) => updateConfig({ rebalanceInterval: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    options={[
                      { value: 1, label: '每日' },
                      { value: 5, label: '每周' },
                      { value: 21, label: '每月' },
                    ]}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">最大持仓数</span>
                  <InputNumber
                    size="small"
                    min={3}
                    max={50}
                    value={config.maxPositions}
                    onChange={(v) => v && updateConfig({ maxPositions: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">
                    仓位分配方式
                    <Tooltip title="等权重：每只股票等额分配；市值加权：按市值比例分配">
                      <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                    </Tooltip>
                  </span>
                  <Select
                    size="small"
                    value={config.positionAlloc}
                    onChange={(v) => updateConfig({ positionAlloc: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    options={[
                      { value: 'equal', label: '等权重' },
                      { value: 'marketCap', label: '市值加权' },
                    ]}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">
                    单股最大仓位
                    <Tooltip title="单只股票占净资产的最高比例，100%=不限制">
                      <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                    </Tooltip>
                  </span>
                  <InputNumber
                    size="small"
                    min={0.05}
                    max={1}
                    step={0.05}
                    value={config.singleStockMaxPct}
                    onChange={(v) => v !== null && updateConfig({ singleStockMaxPct: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    formatter={(v) => `${(v ?? 0) * 100}%`}
                    parser={(v) => parseFloat(v ?? '100') / 100}
                  />
                </div>

                {/* Card 3: 交易成本 */}
                <div className="col-span-2 text-xs font-medium text-text-secondary mt-2 mb-0.5">交易成本</div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">
                    手续费率
                    <Tooltip title="组合回测：按成交额百分比计算；个股回测：固定万分比">
                      <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                    </Tooltip>
                  </span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={30}
                    step={0.5}
                    value={feeRateToDisplay(config.feeRate)}
                    onChange={(v) => v !== null && updateConfig({ feeRate: displayToFeeRate(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    formatter={(v) => `${v}‱`}
                    parser={(v) => parseFloat(v ?? '2.5')}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">
                    滑点
                    <Tooltip title="组合滑点：按成交额百分比计算（反映流动性冲击）；个股滑点：固定万分比">
                      <QuestionCircleOutlined className="ml-1 text-text-disabled" />
                    </Tooltip>
                  </span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={10}
                    step={0.5}
                    value={slippageToDisplay(config.slippage)}
                    onChange={(v) => v !== null && updateConfig({ slippage: displayToSlippage(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    formatter={(v) => `${v}‱`}
                    parser={(v) => parseFloat(v ?? '1')}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">印花税（卖出）</span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={3}
                    step={0.5}
                    value={stampDutyToDisplay(config.stampDuty)}
                    onChange={(v) => v !== null && updateConfig({ stampDuty: displayToStampDuty(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    formatter={(v) => `${v}‰`}
                    parser={(v) => parseFloat(v ?? '1')}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">最低佣金（元）</span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={100}
                    value={config.minCommission / 100}
                    onChange={(v) => v !== null && updateConfig({ minCommission: v * 100 })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>

                {/* Card 4: 风险控制 */}
                <div className="col-span-2 text-xs font-medium text-text-secondary mt-2 mb-0.5">
                  风险控制
                  {strategyType === 'filterTreeLayeredTP' && (
                    <span className="text-orange-500 ml-2 font-normal">
                      （分层模式下以下参数被覆盖）
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">止损比例</span>
                  <InputNumber
                    size="small"
                    min={-50}
                    max={0}
                    step={1}
                    value={decimalToPct(config.stopLossPct)}
                    onChange={(v) => v !== null && updateConfig({ stopLossPct: pctToDecimal(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    formatter={(v) => `${v}%`}
                    parser={(v) => parseFloat(v ?? '-8')}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">止盈比例</span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={100}
                    step={5}
                    value={decimalToPct(config.takeProfitPct)}
                    onChange={(v) => v !== null && updateConfig({ takeProfitPct: pctToDecimal(v) })}
                    disabled={disabled}
                    style={{ width: 120 }}
                    formatter={(v) => `${v}%`}
                    parser={(v) => parseFloat(v ?? '25')}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">最大持仓天数</span>
                  <InputNumber
                    size="small"
                    min={5}
                    max={250}
                    value={config.maxHoldDays}
                    onChange={(v) => v && updateConfig({ maxHoldDays: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">最大顺延天数</span>
                  <InputNumber
                    size="small"
                    min={0}
                    max={20}
                    value={config.maxDeferDays}
                    onChange={(v) => v !== null && updateConfig({ maxDeferDays: v })}
                    disabled={disabled}
                    style={{ width: 120 }}
                  />
                </div>

                {/* 组合风控 */}
                <div className="col-span-2 text-xs font-medium text-text-secondary mt-2 mb-0.5 text-warning">
                  组合级风控（默认关闭）
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">单日最大亏损</span>
                  <Space>
                    <Switch
                      size="small"
                      checked={config.dailyLossLimitEnabled}
                      onChange={(v) => updateConfig({ dailyLossLimitEnabled: v })}
                      disabled={disabled}
                    />
                    {config.dailyLossLimitEnabled && (
                      <InputNumber
                        size="small"
                        min={-50}
                        max={0}
                        step={1}
                        value={decimalToPct(config.dailyLossLimitPct)}
                        onChange={(v) => v !== null && updateConfig({ dailyLossLimitPct: pctToDecimal(v) })}
                        disabled={disabled}
                        style={{ width: 80 }}
                        formatter={(v) => `${v}%`}
                        parser={(v) => parseFloat(v ?? '-5')}
                      />
                    )}
                  </Space>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs">最大回撤止损</span>
                  <Space>
                    <Switch
                      size="small"
                      checked={config.maxDrawdownStopEnabled}
                      onChange={(v) => updateConfig({ maxDrawdownStopEnabled: v })}
                      disabled={disabled}
                    />
                    {config.maxDrawdownStopEnabled && (
                      <InputNumber
                        size="small"
                        min={-50}
                        max={0}
                        step={5}
                        value={decimalToPct(config.maxDrawdownStopPct)}
                        onChange={(v) => v !== null && updateConfig({ maxDrawdownStopPct: pctToDecimal(v) })}
                        disabled={disabled}
                        style={{ width: 80 }}
                        formatter={(v) => `${v}%`}
                        parser={(v) => parseFloat(v ?? '-15')}
                      />
                    )}
                  </Space>
                </div>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default BacktestPanel;