/**
 * 回测默认设置面板
 *
 * 设计：紧凑两列表单风格，统一输入框宽度，深色主题适配
 */

import React, { useState } from 'react';
import { Card, Radio, InputNumber, Button, App, Tooltip, Divider } from 'antd';
import { SaveOutlined, UndoOutlined, InfoCircleOutlined } from '@ant-design/icons';
import {
  getBacktestDefaults,
  saveBacktestDefaults,
  DEFAULT_BACKTEST_DEFAULTS,
  feeRateToDisplay,
  displayToFeeRate,
  type BacktestDefaults,
} from '@/features/backtest/backtestSettingsStorage';

const INPUT_W = 80;

// ---------------------------------------------------------------------------
// 子组件：统一行布局（标签左对齐，控件右对齐）
// ---------------------------------------------------------------------------
interface RowProps {
  label: string;
  tooltip?: string;
  children: React.ReactNode;
}

const Row: React.FC<RowProps> = ({ label, tooltip, children }) => (
  <div className="flex items-center justify-between h-8">
    <div className="flex items-center gap-1">
      <span className="text-text-secondary text-sm">{label}</span>
      {tooltip && (
        <Tooltip title={tooltip}>
          <InfoCircleOutlined className="text-text-disabled text-[11px] cursor-help" />
        </Tooltip>
      )}
    </div>
    <div>{children}</div>
  </div>
);

// ---------------------------------------------------------------------------
// 子组件：指标行（名称 + 多个"标签+输入框"横向排列）
// ---------------------------------------------------------------------------
interface IndicatorField {
  subLabel: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number | null) => void;
}

const IndicatorRow: React.FC<{ name: string; fields: IndicatorField[] }> = ({ name, fields }) => (
  <div className="flex items-start flex-wrap gap-x-3 gap-y-1 py-1">
    <span className="text-text-secondary text-sm w-16 flex-shrink-0 leading-8">{name}</span>
    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 flex-1">
      {fields.map((f, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-text-disabled text-xs">{f.subLabel}</span>
          <InputNumber
            size="small"
            min={f.min} max={f.max} step={f.step ?? 1}
            value={f.value}
            onChange={f.onChange}
            controls={false}
            style={{ width: 70 }}
          />
        </div>
      ))}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

const BacktestDefaultsPanel: React.FC = () => {
  const { message } = App.useApp();
  const [defaults, setDefaults] = useState<BacktestDefaults>(() => getBacktestDefaults());

  const updateField = <K extends keyof BacktestDefaults>(key: K, value: BacktestDefaults[K]) => {
    setDefaults(prev => ({ ...prev, [key]: value }));
  };

  const updateIndicator = <K extends keyof BacktestDefaults['indicatorParams']>(
    key: K,
    value: BacktestDefaults['indicatorParams'][K],
  ) => {
    setDefaults(prev => ({
      ...prev,
      indicatorParams: { ...prev.indicatorParams, [key]: value },
    }));
  };

  const handleSave = () => {
    saveBacktestDefaults(defaults);
    message.success('设置已保存');
  };

  const handleReset = () => {
    const fresh = { ...DEFAULT_BACKTEST_DEFAULTS, indicatorParams: { ...DEFAULT_BACKTEST_DEFAULTS.indicatorParams } };
    setDefaults(fresh);
    saveBacktestDefaults(fresh);
    message.info('已恢复默认设置');
  };

  const p = defaults.indicatorParams;

  return (
    <div className="flex flex-col gap-4">
      {/* ==================== 交易参数 ==================== */}
      <Card className="!bg-bg-panel !border-border-color" size="small" title="交易参数">
        {/* 成交价模式 */}
        <Row label="成交价模式">
          <Radio.Group
            value={defaults.executionPrice}
            onChange={e => updateField('executionPrice', e.target.value)}
            size="small"
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="next_open">T+1 开盘价</Radio.Button>
            <Radio.Button value="next_close">T+1 收盘价</Radio.Button>
          </Radio.Group>
        </Row>

        <Divider className="!my-1 !border-border-color/60" />

        {/* 数值参数 */}
        <Row label="信号确认K线数" tooltip="信号需连续出现指定K线数后才确认触发">
          <InputNumber size="small" min={1} max={5} value={defaults.signalConfirmBars}
            onChange={v => updateField('signalConfirmBars', v ?? 2)} controls={false}
            style={{ width: INPUT_W }} />
        </Row>
        <Row label="最大顺延天数" tooltip="信号触发后允许顺延的最大交易日数">
          <InputNumber size="small" min={1} max={10} value={defaults.maxDeferDays}
            onChange={v => updateField('maxDeferDays', v ?? 3)} controls={false}
            style={{ width: INPUT_W }} />
        </Row>

        <Divider className="!my-1 !border-border-color/60" />

        {/* 手续费率 + 滑点 双列 */}
        <div className="grid grid-cols-2 gap-4 py-1">
          <div>
            <div className="text-text-secondary text-xs mb-1">手续费率</div>
            <InputNumber size="small" min={0} max={30} step={0.1}
              value={feeRateToDisplay(defaults.feeRate)}
              onChange={v => updateField('feeRate', displayToFeeRate(v ?? 0))}
              addonAfter="万分之" controls={false}
              className="!w-full" />
          </div>
          <div>
            <div className="text-text-secondary text-xs mb-1">滑点</div>
            <InputNumber size="small" min={0} max={30} step={0.1}
              value={feeRateToDisplay(defaults.slippage)}
              onChange={v => updateField('slippage', displayToFeeRate(v ?? 0))}
              addonAfter="万分之" controls={false}
              className="!w-full" />
          </div>
        </div>

        <Row label="无风险利率" tooltip="一年期国债参考值 3%">
          <InputNumber size="small" min={0} max={0.1} step={0.01}
            value={defaults.riskFreeRate}
            onChange={v => updateField('riskFreeRate', v ?? 0.03)} controls={false}
            addonAfter="%"
            style={{ width: INPUT_W }} />
        </Row>
      </Card>

      {/* ==================== 指标参数 ==================== */}
      <Card className="!bg-bg-panel !border-border-color" size="small" title="指标参数">
        <IndicatorRow name="MACD" fields={[
          { subLabel: '快', value: p.macdFast, min: 2, max: 50, onChange: v => updateIndicator('macdFast', v ?? 12) },
          { subLabel: '慢', value: p.macdSlow, min: 2, max: 100, onChange: v => updateIndicator('macdSlow', v ?? 26) },
          { subLabel: '信', value: p.macdSignal, min: 2, max: 50, onChange: v => updateIndicator('macdSignal', v ?? 9) },
        ]} />
        <Divider className="!my-1 !border-border-color/60" />
        <IndicatorRow name="RSI" fields={[
          { subLabel: '周期', value: p.rsiPeriod, min: 2, max: 50, onChange: v => updateIndicator('rsiPeriod', v ?? 6) },
        ]} />
        <Divider className="!my-1 !border-border-color/60" />
        <IndicatorRow name="MA" fields={[
          { subLabel: 'MA5', value: p.ma5, min: 2, max: 120, onChange: v => updateIndicator('ma5', v ?? 5) },
          { subLabel: 'MA10', value: p.ma10, min: 2, max: 120, onChange: v => updateIndicator('ma10', v ?? 10) },
          { subLabel: 'MA20', value: p.ma20, min: 2, max: 120, onChange: v => updateIndicator('ma20', v ?? 20) },
          { subLabel: 'MA60', value: p.ma60, min: 2, max: 120, onChange: v => updateIndicator('ma60', v ?? 60) },
        ]} />
        <Divider className="!my-1 !border-border-color/60" />
        <IndicatorRow name="BOLL" fields={[
          { subLabel: '周期', value: p.bollPeriod, min: 5, max: 120, onChange: v => updateIndicator('bollPeriod', v ?? 20) },
          { subLabel: '标准差', value: p.bollStd, min: 0.5, max: 5, step: 0.5, onChange: v => updateIndicator('bollStd', v ?? 2) },
        ]} />
        <Divider className="!my-1 !border-border-color/60" />
        <IndicatorRow name="KDJ" fields={[
          { subLabel: 'K', value: p.kdjK, min: 2, max: 30, onChange: v => updateIndicator('kdjK', v ?? 9) },
          { subLabel: 'D', value: p.kdjD, min: 2, max: 30, onChange: v => updateIndicator('kdjD', v ?? 3) },
          { subLabel: 'J', value: p.kdjJ, min: 2, max: 30, onChange: v => updateIndicator('kdjJ', v ?? 3) },
        ]} />
      </Card>

      {/* ==================== 操作按钮 ==================== */}
      <div className="flex justify-end gap-2">
        <Button icon={<UndoOutlined />} onClick={handleReset} data-testid="reset-backtest-defaults">
          恢复默认
        </Button>
        <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} data-testid="save-backtest-defaults">
          保存设置
        </Button>
      </div>
    </div>
  );
};

export default BacktestDefaultsPanel;