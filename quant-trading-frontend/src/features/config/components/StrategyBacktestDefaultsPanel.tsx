/**
 * 策略回测默认设置面板
 *
 * 5 个 Card 分组：基础参数 / 调仓与仓位 / 交易成本 / 风险控制 / 指标参数
 * 风格与 BacktestDefaultsPanel 保持一致
 */

import React, { useState } from 'react';
import {
  Card,
  Radio,
  InputNumber,
  Button,
  App,
  Tooltip,
  Divider,
  Switch,
  Select,
  Modal,
} from 'antd';
import {
  SaveOutlined,
  UndoOutlined,
  InfoCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
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

const INPUT_W = 80;

// ---------------------------------------------------------------------------
// 子组件：统一行布局
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
// Card 标题（带彩色竖线）
// ---------------------------------------------------------------------------
interface SectionTitleProps {
  text: string;
  color: string;
}

const SectionTitle: React.FC<SectionTitleProps> = ({ text, color }) => (
  <div className="flex items-center gap-2">
    <div className="w-1 h-4 rounded-sm" style={{ backgroundColor: color }} />
    <span className="text-sm font-medium">{text}</span>
  </div>
);

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------
const StrategyBacktestDefaultsPanel: React.FC = () => {
  const { message, modal } = App.useApp();
  const [defaults, setDefaults] = useState<StrategyBacktestDefaults>(
    () => getStrategyBacktestDefaults(),
  );

  const updateField = <K extends keyof StrategyBacktestDefaults>(
    key: K,
    value: StrategyBacktestDefaults[K],
  ) => {
    setDefaults((prev) => ({ ...prev, [key]: value }));
  };

  // 组合级风控二次确认
  const handlePortfolioRiskToggle = (
    field: 'dailyLossLimitEnabled' | 'maxDrawdownStopEnabled',
    checked: boolean,
  ) => {
    if (checked) {
      Modal.confirm({
        title: '启用组合级风控',
        icon: <ExclamationCircleOutlined />,
        content: (
          <div className="text-sm">
            <p className="text-warning mb-2">
              ⚠️ 启用组合级风控可能引入过拟合，回测业绩可能偏乐观。
            </p>
            <p className="text-text-secondary mb-2">
              实盘中此类风控触发即清仓，一旦误判会永久踏空。
            </p>
            <p className="text-text-disabled">
              建议仅在验证策略稳健性时使用，不作为实盘参考。
            </p>
          </div>
        ),
        okText: '确认启用',
        cancelText: '取消',
        onOk: () => updateField(field, true),
      });
    } else {
      updateField(field, false);
    }
  };

  const handleSave = () => {
    saveStrategyBacktestDefaults(defaults);
    message.success('策略回测设置已保存');
  };

  const handleReset = () => {
    const fresh = { ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS };
    setDefaults(fresh);
    saveStrategyBacktestDefaults(fresh);
    message.info('已恢复默认设置');
  };

  return (
    <div className="flex flex-col gap-4">
      {/* ==================== Card 1: 基础参数 ==================== */}
      <Card
        className="!bg-bg-panel !border-border-color"
        size="small"
        title={<SectionTitle text="基础参数" color="#13c2c2" />}
      >
        <Row label="初始资金">
          <InputNumber
            size="small"
            min={10}
            max={10000}
            value={fenToWanYuan(defaults.initialCapital)}
            onChange={(v) => updateField('initialCapital', wanYuanToFen(v ?? 100))}
            controls={false}
            addonAfter="万"
            style={{ width: INPUT_W }}
          />
        </Row>
        <Row label="基准指数">
          <Select
            size="small"
            value={defaults.benchmarkCode}
            onChange={(v) => updateField('benchmarkCode', v)}
            style={{ width: 140 }}
            options={[
              { value: '000300.SH', label: '沪深300' },
              { value: '000905.SH', label: '中证500' },
              { value: '000016.SH', label: '上证50' },
              { value: '399006.SZ', label: '创业板指' },
            ]}
          />
        </Row>
        <Row label="基准全收益指数" tooltip="开启使用 H00300.CSI（含分红），需后端支持">
          <Switch
            size="small"
            checked={defaults.benchmarkTotalReturn}
            onChange={(v) => updateField('benchmarkTotalReturn', v)}
          />
        </Row>
        <Row label="无风险利率" tooltip="夏普比率计算用，参考一年期国债 3%">
          <InputNumber
            size="small"
            min={0}
            max={10}
            step={0.1}
            value={decimalToPct(defaults.riskFreeRate)}
            onChange={(v) => updateField('riskFreeRate', pctToDecimal(v ?? 3))}
            controls={false}
            addonAfter="%"
            style={{ width: INPUT_W }}
          />
        </Row>
        <Row label="预热天数" tooltip="指标冷启动所需历史数据天数">
          <InputNumber
            size="small"
            min={20}
            max={250}
            value={defaults.warmupDays}
            onChange={(v) => updateField('warmupDays', v ?? 60)}
            controls={false}
            addonAfter="天"
            style={{ width: INPUT_W }}
          />
        </Row>
      </Card>

      {/* ==================== Card 2: 调仓与仓位 ==================== */}
      <Card
        className="!bg-bg-panel !border-border-color"
        size="small"
        title={<SectionTitle text="调仓与仓位" color="#1677ff" />}
      >
        <Row label="调仓频率">
          <Radio.Group
            value={defaults.rebalanceInterval}
            onChange={(e) => updateField('rebalanceInterval', e.target.value as RebalanceInterval)}
            size="small"
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value={1}>每日</Radio.Button>
            <Radio.Button value={5}>每周</Radio.Button>
            <Radio.Button value={21}>每月</Radio.Button>
          </Radio.Group>
        </Row>
        <div className="grid grid-cols-2 gap-4 py-1">
          <div>
            <div className="text-text-secondary text-xs mb-1">最大持仓数</div>
            <InputNumber
              size="small"
              min={3}
              max={50}
              value={defaults.maxPositions}
              onChange={(v) => updateField('maxPositions', v ?? 10)}
              controls={false}
              addonAfter="只"
              className="!w-full"
            />
          </div>
          <div>
            <div className="text-text-secondary text-xs mb-1">仓位分配</div>
            <Radio.Group
              value={defaults.positionAlloc}
              onChange={(e) => updateField('positionAlloc', e.target.value as PositionAlloc)}
              size="small"
              optionType="button"
              buttonStyle="solid"
              className="!w-full"
            >
              <Radio.Button value="equal">等权</Radio.Button>
              <Radio.Button value="marketCap">市值</Radio.Button>
            </Radio.Group>
          </div>
        </div>
        <Row
          label="单股最大仓位"
          tooltip="例如 20% 表示单只股票最多占总资产 20%，超出部分闲置。默认 100% 不限制，即完全等权分配。"
        >
          <div className="flex items-center gap-1">
            <InputNumber
              size="small"
              min={5}
              max={100}
              value={decimalToPct(defaults.singleStockMaxPct)}
              onChange={(v) => updateField('singleStockMaxPct', pctToDecimal(v ?? 100))}
              controls={false}
              addonAfter="%"
              style={{ width: INPUT_W }}
            />
            <Tooltip title="例如 20% 表示单只股票最多占总资产 20%，超出部分闲置。默认 100% 不限制，即完全等权分配。">
              <InfoCircleOutlined className="text-text-disabled text-[11px] cursor-help" />
            </Tooltip>
          </div>
        </Row>
        <Row label="剩余现金处理">
          <Radio.Group
            value={defaults.idleCashReturn}
            onChange={(e) => updateField('idleCashReturn', e.target.value as IdleCashReturn)}
            size="small"
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="none">闲置</Radio.Button>
            <Radio.Button value="moneyMarket">模拟货基</Radio.Button>
          </Radio.Group>
        </Row>
        {defaults.idleCashReturn === 'moneyMarket' && (
          <Row label="货基年化利率">
            <InputNumber
              size="small"
              min={0}
              max={5}
              step={0.1}
              value={decimalToPct(defaults.idleCashRate)}
              onChange={(v) => updateField('idleCashRate', pctToDecimal(v ?? 2))}
              controls={false}
              addonAfter="%"
              style={{ width: INPUT_W }}
            />
          </Row>
        )}
      </Card>

      {/* ==================== Card 3: 交易成本 ==================== */}
      <Card
        className="!bg-bg-panel !border-border-color"
        size="small"
        title={<SectionTitle text="交易成本" color="#fa8c16" />}
      >
        <div className="grid grid-cols-2 gap-4 py-1">
          <div>
            <div className="text-text-secondary text-xs mb-1">手续费率</div>
            <InputNumber
              size="small"
              min={0}
              max={30}
              step={0.1}
              value={feeRateToDisplay(defaults.feeRate)}
              onChange={(v) => updateField('feeRate', displayToFeeRate(v ?? 0))}
              addonAfter="万分之"
              controls={false}
              className="!w-full"
            />
          </div>
          <div>
            <div className="text-text-secondary text-xs mb-1">滑点</div>
            <InputNumber
              size="small"
              min={0}
              max={30}
              step={0.1}
              value={slippageToDisplay(defaults.slippage)}
              onChange={(v) => updateField('slippage', displayToSlippage(v ?? 0))}
              addonAfter="万分之"
              controls={false}
              className="!w-full"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 py-1">
          <div>
            <div className="text-text-secondary text-xs mb-1">印花税</div>
            <InputNumber
              size="small"
              min={0}
              max={5}
              step={0.1}
              value={stampDutyToDisplay(defaults.stampDuty)}
              onChange={(v) => updateField('stampDuty', displayToStampDuty(v ?? 0))}
              addonAfter="‰"
              controls={false}
              className="!w-full"
            />
          </div>
          <div>
            <div className="text-text-secondary text-xs mb-1">最小佣金</div>
            <InputNumber
              size="small"
              min={0}
              max={100}
              value={defaults.minCommission / 100}
              onChange={(v) => updateField('minCommission', Math.round((v ?? 5) * 100))}
              addonAfter="元"
              controls={false}
              className="!w-full"
            />
          </div>
        </div>
      </Card>

      {/* ==================== Card 4: 风险控制 ==================== */}
      <Card
        className="!bg-bg-panel !border-border-color"
        size="small"
        title={<SectionTitle text="风险控制" color="#f5222d" />}
      >
        <div className="grid grid-cols-2 gap-4 py-1">
          <div>
            <div className="text-text-secondary text-xs mb-1">止损比例</div>
            <InputNumber
              size="small"
              min={-50}
              max={0}
              step={1}
              value={decimalToPct(defaults.stopLossPct)}
              onChange={(v) => updateField('stopLossPct', pctToDecimal(v ?? -8))}
              addonAfter="%"
              controls={false}
              className="!w-full"
            />
          </div>
          <div>
            <div className="text-text-secondary text-xs mb-1">止盈比例</div>
            <InputNumber
              size="small"
              min={0}
              max={200}
              step={1}
              value={decimalToPct(defaults.takeProfitPct)}
              onChange={(v) => updateField('takeProfitPct', pctToDecimal(v ?? 25))}
              addonAfter="%"
              controls={false}
              className="!w-full"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 py-1">
          <div>
            <div className="text-text-secondary text-xs mb-1">最大持仓天数</div>
            <InputNumber
              size="small"
              min={1}
              max={250}
              value={defaults.maxHoldDays}
              onChange={(v) => updateField('maxHoldDays', v ?? 20)}
              addonAfter="天"
              controls={false}
              className="!w-full"
            />
          </div>
          <div>
            <div className="text-text-secondary text-xs mb-1">最大顺延天数</div>
            <InputNumber
              size="small"
              min={0}
              max={10}
              value={defaults.maxDeferDays}
              onChange={(v) => updateField('maxDeferDays', v ?? 3)}
              addonAfter="天"
              controls={false}
              className="!w-full"
            />
          </div>
        </div>
        <Row label="顺延失败处理">
          <Select
            size="small"
            value={defaults.deferFailAction}
            onChange={(v) => updateField('deferFailAction', v as DeferFailAction)}
            style={{ width: 140 }}
            options={[
              { value: 'abandon', label: '放弃交易' },
              { value: 'atClose', label: '按收盘价' },
            ]}
          />
        </Row>

        <Divider className="!my-2 !border-border-color/60" />

        {/* 组合级风控（默认关闭） */}
        <div className="text-text-disabled text-xs mb-2 text-center">
          ── 组合级风控（默认关闭）──
        </div>

        <div className="flex items-center justify-between h-8">
          <div className="flex items-center gap-2">
            <Switch
              size="small"
              checked={defaults.dailyLossLimitEnabled}
              onChange={(v) => handlePortfolioRiskToggle('dailyLossLimitEnabled', v)}
            />
            <span className="text-text-secondary text-sm">单日最大亏损</span>
            <Tooltip title="触发条件：扣除当日交易费用后的日收益率 ≤ 阈值；触发后次日空仓">
              <InfoCircleOutlined className="text-text-disabled text-[11px] cursor-help" />
            </Tooltip>
          </div>
          {defaults.dailyLossLimitEnabled && (
            <InputNumber
              size="small"
              min={-50}
              max={0}
              step={1}
              value={decimalToPct(defaults.dailyLossLimitPct)}
              onChange={(v) => updateField('dailyLossLimitPct', pctToDecimal(v ?? -5))}
              addonAfter="%"
              controls={false}
              style={{ width: INPUT_W }}
            />
          )}
        </div>

        <div className="flex items-center justify-between h-8">
          <div className="flex items-center gap-2">
            <Switch
              size="small"
              checked={defaults.maxDrawdownStopEnabled}
              onChange={(v) => handlePortfolioRiskToggle('maxDrawdownStopEnabled', v)}
            />
            <span className="text-text-secondary text-sm">最大回撤止损</span>
            <Tooltip title="触发后全部清仓并停止回测">
              <InfoCircleOutlined className="text-text-disabled text-[11px] cursor-help" />
            </Tooltip>
          </div>
          {defaults.maxDrawdownStopEnabled && (
            <InputNumber
              size="small"
              min={-50}
              max={0}
              step={1}
              value={decimalToPct(defaults.maxDrawdownStopPct)}
              onChange={(v) => updateField('maxDrawdownStopPct', pctToDecimal(v ?? -15))}
              addonAfter="%"
              controls={false}
              style={{ width: INPUT_W }}
            />
          )}
        </div>
      </Card>

      {/* ==================== 操作按钮 ==================== */}
      <div className="flex justify-end gap-2">
        <Button
          icon={<UndoOutlined />}
          onClick={handleReset}
          data-testid="reset-strategy-backtest-defaults"
        >
          恢复默认
        </Button>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSave}
          data-testid="save-strategy-backtest-defaults"
        >
          保存设置
        </Button>
      </div>
    </div>
  );
};

export default StrategyBacktestDefaultsPanel;
