/**
 * 合并回测设置面板
 *
 * 整合 V1 回测默认设置 + V2 策略回测默认设置
 * 按钮固定在底部，内容区域可滚动
 * 输入框统一 small 尺寸，宽度统一
 */

import React, { useState } from 'react';
import {
  Card,
  Radio,
  InputNumber,
  Button,
  Switch,
  Select,
  Tooltip,
  Divider,
  App,
  Modal,
} from 'antd';
import {
  SaveOutlined,
  UndoOutlined,
  InfoCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import {
  getBacktestDefaults,
  saveBacktestDefaults,
  DEFAULT_BACKTEST_DEFAULTS,
  type BacktestDefaults,
} from '@/features/backtest/backtestSettingsStorage';
import {
  getStrategyBacktestDefaults,
  saveStrategyBacktestDefaults,
  DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
  fenToWanYuan,
  wanYuanToFen,
  feeRateToDisplay,
  displayToFeeRate,
  slippageToDisplay,
  displayToSlippage,
  stampDutyToDisplay,
  displayToStampDuty,
  decimalToPct,
  pctToDecimal,
} from '@/features/strategy-backtest/storage';
import type {
  StrategyBacktestDefaults,
  RebalanceInterval,
  PositionAlloc,
  IdleCashReturn,
  DeferFailAction,
} from '@/features/strategy-backtest/types';

const NUM_W = 110;

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
    <div className="flex items-center">{children}</div>
  </div>
);

interface IndField {
  sub: string;
  val: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number | null) => void;
}

const IndRow: React.FC<{ name: string; fields: IndField[] }> = ({ name, fields }) => (
  <div className="flex items-center flex-wrap gap-x-4 gap-y-1 py-1">
    <span className="text-text-secondary text-sm w-12 flex-shrink-0 leading-8">{name}</span>
    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 flex-1">
      {fields.map((f, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-text-disabled text-xs">{f.sub}</span>
          <InputNumber
            size="small"
            min={f.min} max={f.max} step={f.step ?? 1}
            value={f.val}
            onChange={f.onChange}
            controls={false}
            style={{ width: 60 }}
          />
        </div>
      ))}
    </div>
  </div>
);

interface SecTitleProps {
  text: string;
  color: string;
}

const SectionTitle: React.FC<SecTitleProps> = ({ text, color }) => (
  <div className="flex items-center gap-2">
    <div className="w-1 h-4 rounded-sm" style={{ backgroundColor: color }} />
    <span className="text-sm font-medium">{text}</span>
  </div>
);

const gridInputClass = "!w-full [&_.ant-input-number]:!w-full";

const CombinedBacktestPanel: React.FC = () => {
  const { message, modal: antdModal } = App.useApp();

  const [v1Defaults, setV1Defaults] = useState<BacktestDefaults>(() => getBacktestDefaults());
  const [v2Defaults, setV2Defaults] = useState<StrategyBacktestDefaults>(
    () => getStrategyBacktestDefaults(),
  );

  const updateV1 = <K extends keyof BacktestDefaults>(key: K, val: BacktestDefaults[K]) => {
    setV1Defaults(prev => ({ ...prev, [key]: val }));
  };

  const updateInd = <K extends keyof BacktestDefaults['indicatorParams']>(
    key: K, val: BacktestDefaults['indicatorParams'][K],
  ) => {
    setV1Defaults(prev => ({ ...prev, indicatorParams: { ...prev.indicatorParams, [key]: val } }));
  };

  const updateV2 = <K extends keyof StrategyBacktestDefaults>(
    key: K, val: StrategyBacktestDefaults[K],
  ) => {
    setV2Defaults(prev => ({ ...prev, [key]: val }));
  };

  const handleRiskToggle = (
    field: 'dailyLossLimitEnabled' | 'maxDrawdownStopEnabled',
    checked: boolean,
  ) => {
    if (checked) {
      antdModal.confirm({
        title: '启用组合级风控',
        icon: <ExclamationCircleOutlined />,
        content: (
          <div className="text-sm space-y-2">
            <p className="text-warning">⚠️ 启用组合级风控可能引入过拟合，回测业绩可能偏乐观。</p>
            <p className="text-text-secondary">实盘中此类风控触发即清仓，一旦误判会永久踏空。</p>
            <p className="text-text-disabled">建议仅在验证策略稳健性时使用，不作为实盘参考。</p>
          </div>
        ),
        okText: '确认启用',
        cancelText: '取消',
        onOk: () => updateV2(field, true),
      });
    } else {
      updateV2(field, false);
    }
  };

  const handleSave = () => {
    saveBacktestDefaults(v1Defaults);
    saveStrategyBacktestDefaults(v2Defaults);
    message.success('回测设置已保存');
  };

  const handleReset = () => {
    setV1Defaults({ ...DEFAULT_BACKTEST_DEFAULTS, indicatorParams: { ...DEFAULT_BACKTEST_DEFAULTS.indicatorParams } });
    setV2Defaults({ ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS });
    saveBacktestDefaults({ ...DEFAULT_BACKTEST_DEFAULTS, indicatorParams: { ...DEFAULT_BACKTEST_DEFAULTS.indicatorParams } });
    saveStrategyBacktestDefaults({ ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS });
    message.info('已恢复默认设置');
  };

  const p = v1Defaults.indicatorParams;

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-auto pr-1 space-y-3 min-h-0">
        <Card className="!bg-bg-panel !border-border-color" size="small" title={<SectionTitle text="基础参数" color="#13c2c2" />}>
          <Row label="初始资金">
            <InputNumber size="small" min={10} max={10000} value={fenToWanYuan(v2Defaults.initialCapital)}
              onChange={(v) => updateV2('initialCapital', wanYuanToFen(v ?? 100))} controls={false}
              addonAfter="万" style={{ width: NUM_W }} />
          </Row>
          <Row label="基准指数">
            <Select size="small" value={v2Defaults.benchmarkCode} onChange={(v) => updateV2('benchmarkCode', v)}
              style={{ width: NUM_W }}
              options={[
                { value: '000300.SH', label: '沪深300' },
                { value: '000905.SH', label: '中证500' },
                { value: '000016.SH', label: '上证50' },
                { value: '399006.SZ', label: '创业板指' },
              ]} />
          </Row>
          <Row label="全收益指数" tooltip="开启使用 H00300.CSI（含分红），需后端支持">
            <Switch size="small" checked={v2Defaults.benchmarkTotalReturn} onChange={(v) => updateV2('benchmarkTotalReturn', v)} />
          </Row>
          <Row label="无风险利率" tooltip="夏普比率计算用，参考一年期国债 3%">
            <InputNumber size="small" min={0} max={10} step={0.1} value={decimalToPct(v2Defaults.riskFreeRate)}
              onChange={(v) => updateV2('riskFreeRate', pctToDecimal(v ?? 3))} controls={false}
              addonAfter="%" style={{ width: NUM_W }} />
          </Row>
          <Row label="预热天数" tooltip="指标冷启动所需历史数据天数">
            <InputNumber size="small" min={20} max={250} value={v2Defaults.warmupDays}
              onChange={(v) => updateV2('warmupDays', v ?? 60)} controls={false}
              addonAfter="天" style={{ width: NUM_W }} />
          </Row>
        </Card>

        <Card className="!bg-bg-panel !border-border-color" size="small" title={<SectionTitle text="交易执行" color="#1677ff" />}>
          <Row label="成交价模式">
            <Radio.Group value={v1Defaults.executionPrice} onChange={e => updateV1('executionPrice', e.target.value)}
              size="small" optionType="button" buttonStyle="solid">
              <Radio.Button value="next_open">T+1 开盘价</Radio.Button>
              <Radio.Button value="next_close">T+1 收盘价</Radio.Button>
            </Radio.Group>
          </Row>
          <Row label="最大顺延天数" tooltip="信号触发后允许顺延的最大交易日数">
            <InputNumber size="small" min={1} max={10} value={v2Defaults.maxDeferDays}
              onChange={(v) => updateV2('maxDeferDays', v ?? 3)} controls={false}
              addonAfter="天" style={{ width: NUM_W }} />
          </Row>
          <Row label="顺延失败处理">
            <Select size="small" value={v2Defaults.deferFailAction}
              onChange={(v) => updateV2('deferFailAction', v as DeferFailAction)} style={{ width: NUM_W }}
              options={[
                { value: 'abandon', label: '放弃交易' },
                { value: 'atClose', label: '按收盘价' },
              ]} />
          </Row>
        </Card>

        <Card className="!bg-bg-panel !border-border-color" size="small" title={<SectionTitle text="调仓与仓位" color="#1677ff" />}>
          <Row label="调仓频率">
            <Radio.Group value={v2Defaults.rebalanceInterval}
              onChange={(e) => updateV2('rebalanceInterval', e.target.value as RebalanceInterval)}
              size="small" optionType="button" buttonStyle="solid">
              <Radio.Button value={1}>每日</Radio.Button>
              <Radio.Button value={5}>每周</Radio.Button>
              <Radio.Button value={21}>每月</Radio.Button>
            </Radio.Group>
          </Row>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 py-1">
            <div>
              <div className="text-text-secondary text-xs mb-1">最大持仓数</div>
              <InputNumber size="small" min={3} max={50} value={v2Defaults.maxPositions}
                onChange={(v) => updateV2('maxPositions', v ?? 10)} controls={false}
                addonAfter="只" className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">仓位分配</div>
              <Radio.Group value={v2Defaults.positionAlloc}
                onChange={(e) => updateV2('positionAlloc', e.target.value as PositionAlloc)}
                size="small" optionType="button" buttonStyle="solid" className="!w-full [&_.ant-radio-button-wrapper]:!px-3">
                <Radio.Button value="equal">等权</Radio.Button>
                <Radio.Button value="marketCap">市值</Radio.Button>
              </Radio.Group>
            </div>
          </div>
          <Row label="单股最大仓位" tooltip="单只股票最多占总资产比例，默认100%不限即等权分配">
            <InputNumber size="small" min={5} max={100} value={decimalToPct(v2Defaults.singleStockMaxPct)}
              onChange={(v) => updateV2('singleStockMaxPct', pctToDecimal(v ?? 100))} controls={false}
              addonAfter="%" style={{ width: NUM_W }} />
          </Row>
          <Row label="剩余现金处理">
            <Radio.Group value={v2Defaults.idleCashReturn}
              onChange={(e) => updateV2('idleCashReturn', e.target.value as IdleCashReturn)}
              size="small" optionType="button" buttonStyle="solid">
              <Radio.Button value="none">闲置</Radio.Button>
              <Radio.Button value="moneyMarket">模拟货基</Radio.Button>
            </Radio.Group>
          </Row>
          {v2Defaults.idleCashReturn === 'moneyMarket' && (
            <Row label="货基年化利率">
              <InputNumber size="small" min={0} max={5} step={0.1} value={decimalToPct(v2Defaults.idleCashRate)}
                onChange={(v) => updateV2('idleCashRate', pctToDecimal(v ?? 2))} controls={false}
                addonAfter="%" style={{ width: NUM_W }} />
            </Row>
          )}
        </Card>

        <Card className="!bg-bg-panel !border-border-color" size="small" title={<SectionTitle text="交易成本" color="#fa8c16" />}>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 py-1">
            <div>
              <div className="text-text-secondary text-xs mb-1">手续费率</div>
              <InputNumber size="small" min={0} max={30} step={0.1} value={feeRateToDisplay(v2Defaults.feeRate)}
                onChange={(v) => updateV2('feeRate', displayToFeeRate(v ?? 0))} addonAfter="‱" controls={false}
                className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">组合滑点</div>
              <InputNumber size="small" min={0} max={30} step={0.1} value={slippageToDisplay(v2Defaults.slippage)}
                onChange={(v) => updateV2('slippage', displayToSlippage(v ?? 0))} addonAfter="‱" controls={false}
                className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">印花税</div>
              <InputNumber size="small" min={0} max={5} step={0.1} value={stampDutyToDisplay(v2Defaults.stampDuty)}
                onChange={(v) => updateV2('stampDuty', displayToStampDuty(v ?? 0))} addonAfter="‰" controls={false}
                className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">最小佣金</div>
              <InputNumber size="small" min={0} max={100} value={v2Defaults.minCommission / 100}
                onChange={(v) => updateV2('minCommission', Math.round((v ?? 5) * 100))} addonAfter="元" controls={false}
                className={gridInputClass} />
            </div>
          </div>
        </Card>

        <Card className="!bg-bg-panel !border-border-color" size="small" title={<SectionTitle text="风险控制" color="#f5222d" />}>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 py-1">
            <div>
              <div className="text-text-secondary text-xs mb-1">止损比例</div>
              <InputNumber size="small" min={-50} max={0} step={1} value={decimalToPct(v2Defaults.stopLossPct)}
                onChange={(v) => updateV2('stopLossPct', pctToDecimal(v ?? -8))} addonAfter="%" controls={false}
                className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">止盈比例</div>
              <InputNumber size="small" min={0} max={200} step={1} value={decimalToPct(v2Defaults.takeProfitPct)}
                onChange={(v) => updateV2('takeProfitPct', pctToDecimal(v ?? 25))} addonAfter="%" controls={false}
                className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">最大持仓天数</div>
              <InputNumber size="small" min={1} max={250} value={v2Defaults.maxHoldDays}
                onChange={(v) => updateV2('maxHoldDays', v ?? 20)} addonAfter="天" controls={false}
                className={gridInputClass} />
            </div>
            <div>
              <div className="text-text-secondary text-xs mb-1">超时处理</div>
              <Select size="small" value={v2Defaults.deferFailAction}
                onChange={(v) => updateV2('deferFailAction', v as DeferFailAction)} className="!w-full"
                options={[
                  { value: 'abandon', label: '放弃交易' },
                  { value: 'atClose', label: '按收盘价' },
                ]} />
            </div>
          </div>

          <Divider className="!my-2 !border-border-color/60" />

          <div className="text-text-disabled text-xs mb-2 text-center">── 组合级风控（默认关闭）──</div>
          <div className="flex items-center justify-between h-8">
            <div className="flex items-center gap-2">
              <Switch size="small" checked={v2Defaults.dailyLossLimitEnabled}
                onChange={(v) => handleRiskToggle('dailyLossLimitEnabled', v)} />
              <span className="text-text-secondary text-sm">单日最大亏损</span>
              <Tooltip title="扣除当日交易费用后的日收益率 ≤ 阈值时触发，次日空仓">
                <InfoCircleOutlined className="text-text-disabled text-[11px] cursor-help" />
              </Tooltip>
            </div>
            {v2Defaults.dailyLossLimitEnabled && (
              <InputNumber size="small" min={-50} max={0} step={1}
                value={decimalToPct(v2Defaults.dailyLossLimitPct)}
                onChange={(v) => updateV2('dailyLossLimitPct', pctToDecimal(v ?? -5))}
                addonAfter="%" controls={false} style={{ width: NUM_W }} />
            )}
          </div>
          <div className="flex items-center justify-between h-8">
            <div className="flex items-center gap-2">
              <Switch size="small" checked={v2Defaults.maxDrawdownStopEnabled}
                onChange={(v) => handleRiskToggle('maxDrawdownStopEnabled', v)} />
              <span className="text-text-secondary text-sm">最大回撤止损</span>
              <Tooltip title="触发后全部清仓并停止回测">
                <InfoCircleOutlined className="text-text-disabled text-[11px] cursor-help" />
              </Tooltip>
            </div>
            {v2Defaults.maxDrawdownStopEnabled && (
              <InputNumber size="small" min={-50} max={0} step={1}
                value={decimalToPct(v2Defaults.maxDrawdownStopPct)}
                onChange={(v) => updateV2('maxDrawdownStopPct', pctToDecimal(v ?? -15))}
                addonAfter="%" controls={false} style={{ width: NUM_W }} />
            )}
          </div>
        </Card>

        <Card className="!bg-bg-panel !border-border-color" size="small" title={<SectionTitle text="指标参数" color="#722ed1" />}>
          <IndRow name="MACD" fields={[
            { sub: '快', val: p.macdFast, min: 2, max: 50, onChange: v => updateInd('macdFast', v ?? 12) },
            { sub: '慢', val: p.macdSlow, min: 2, max: 100, onChange: v => updateInd('macdSlow', v ?? 26) },
            { sub: '信', val: p.macdSignal, min: 2, max: 50, onChange: v => updateInd('macdSignal', v ?? 9) },
          ]} />
          <Divider className="!my-1 !border-border-color/60" />
          <IndRow name="RSI" fields={[
            { sub: '周期', val: p.rsiPeriod, min: 2, max: 50, onChange: v => updateInd('rsiPeriod', v ?? 6) },
          ]} />
          <Divider className="!my-1 !border-border-color/60" />
          <IndRow name="MA" fields={[
            { sub: 'MA5', val: p.ma5, min: 2, max: 120, onChange: v => updateInd('ma5', v ?? 5) },
            { sub: 'MA10', val: p.ma10, min: 2, max: 120, onChange: v => updateInd('ma10', v ?? 10) },
            { sub: 'MA20', val: p.ma20, min: 2, max: 120, onChange: v => updateInd('ma20', v ?? 20) },
            { sub: 'MA60', val: p.ma60, min: 2, max: 120, onChange: v => updateInd('ma60', v ?? 60) },
          ]} />
          <Divider className="!my-1 !border-border-color/60" />
          <IndRow name="BOLL" fields={[
            { sub: '周期', val: p.bollPeriod, min: 5, max: 120, onChange: v => updateInd('bollPeriod', v ?? 20) },
            { sub: 'σ', val: p.bollStd, min: 0.5, max: 5, step: 0.5, onChange: v => updateInd('bollStd', v ?? 2) },
          ]} />
          <Divider className="!my-1 !border-border-color/60" />
          <IndRow name="KDJ" fields={[
            { sub: 'K', val: p.kdjK, min: 2, max: 30, onChange: v => updateInd('kdjK', v ?? 9) },
            { sub: 'D', val: p.kdjD, min: 2, max: 30, onChange: v => updateInd('kdjD', v ?? 3) },
            { sub: 'J', val: p.kdjJ, min: 2, max: 30, onChange: v => updateInd('kdjJ', v ?? 3) },
          ]} />
        </Card>

        <div className="h-4" />
      </div>

      <div className="flex-shrink-0 bg-bg-panel border-t border-border-color px-3 py-2.5 flex justify-end gap-2">
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

export default CombinedBacktestPanel;