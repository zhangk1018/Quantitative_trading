// src/features/strategy-backtest/components/PerformanceMetrics.tsx
// 绩效指标网格 — 三级指标状态（有效/不可计算/不适用）

import React from 'react';
import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { StrategyMetrics } from '../types';

interface PerformanceMetricsProps {
  metrics: StrategyMetrics | null;
  benchmarkMissingRate?: number;
}

interface MetricCard {
  label: string;
  value: string | number | null;
  tooltip: string;
  status: 'valid' | 'unavailable' | 'na';
}

function formatPct(v: number | null, decimals = 1): string {
  if (v === null || v === undefined) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(decimals)}%`;
}

function formatRatio(v: number | null, decimals = 2): string {
  if (v === null || v === undefined) return '--';
  return v.toFixed(decimals);
}

const PerformanceMetrics: React.FC<PerformanceMetricsProps> = ({ metrics, benchmarkMissingRate }) => {
  if (!metrics) {
    return (
      <div className="bg-bg-panel rounded-lg border border-border-color p-4">
        <div className="text-text-disabled text-sm text-center py-4">
          运行回测后将显示绩效指标
        </div>
      </div>
    );
  }

  const cards: MetricCard[] = [
    // 第一行
    { label: '总收益', value: formatPct(metrics.totalReturn), tooltip: '回测期间总收益率', status: 'valid' },
    { label: '年化收益', value: formatPct(metrics.annualReturn), tooltip: '年化收益率（复利）', status: 'valid' },
    { label: '夏普比率', value: formatRatio(metrics.sharpeRatio), tooltip: '单位风险超额收益', status: 'valid' },
    { label: '最大回撤', value: formatPct(metrics.maxDrawdown), tooltip: '历史最大回撤幅度', status: 'valid' },
    { label: '胜率', value: formatPct(metrics.winRate), tooltip: '盈利交易占比', status: 'valid' },
    { label: '盈亏比', value: formatRatio(metrics.profitLossRatio), tooltip: '平均盈利/平均亏损', status: 'valid' },
    // 第二行
    { label: 'Alpha', value: formatPct(metrics.alpha), tooltip: '超额收益，需沪深300基准数据', status: metrics.alpha !== null ? 'valid' : 'unavailable' },
    { label: 'Beta', value: formatRatio(metrics.beta), tooltip: '市场风险暴露，需沪深300基准数据', status: metrics.beta !== null ? 'valid' : 'unavailable' },
    { label: '卡玛比率', value: formatRatio(metrics.calmarRatio), tooltip: '年化收益/最大回撤', status: 'valid' },
    { label: '信息比率', value: formatRatio(metrics.informationRatio), tooltip: '超额收益/跟踪误差，需沪深300基准数据', status: metrics.informationRatio !== null ? 'valid' : 'unavailable' },
    { label: '月度胜率', value: formatPct(metrics.monthlyWinRate), tooltip: '正收益月份占比', status: 'valid' },
    { label: '交易次数', value: metrics.totalTrades, tooltip: '总交易笔数', status: 'valid' },
  ];

  return (
    <div className="bg-bg-panel rounded-lg border border-border-color p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium">绩效指标</span>
        {benchmarkMissingRate !== undefined && benchmarkMissingRate > 5 && (
          <span className="text-warning text-xs">
            ⚠ 基准缺失率 {benchmarkMissingRate.toFixed(1)}%，Alpha/Beta 参考价值有限
          </span>
        )}
      </div>
      <div className="grid grid-cols-6 gap-2">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-bg-card rounded-lg p-2 flex flex-col items-center"
          >
            <div className="flex items-center gap-1">
              <span className="text-text-disabled text-[10px]">{card.label}</span>
              {card.status === 'unavailable' && (
                <Tooltip title={`不可计算：${card.tooltip}`}>
                  <InfoCircleOutlined className="text-text-disabled text-[10px] cursor-help" />
                </Tooltip>
              )}
            </div>
            <span
              className={`text-sm font-bold mt-1 ${
                card.status === 'valid'
                  ? typeof card.value === 'string' && card.value.startsWith('+')
                    ? 'text-profit'
                    : typeof card.value === 'string' && card.value.startsWith('-')
                      ? 'text-loss'
                      : 'text-text-primary'
                  : 'text-text-disabled'
              }`}
            >
              {card.status === 'valid' ? card.value : '--'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default PerformanceMetrics;