// src/features/strategy-backtest/components/EquityChart.tsx
// 净值曲线图 — 使用 lightweight-charts（懒加载）

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, LineStyle } from 'lightweight-charts';
import type { EquityPoint } from '../types';

interface EquityChartProps {
  equityCurve: EquityPoint[];
  warnings: string[];
}

const EquityChart: React.FC<EquityChartProps> = ({ equityCurve, warnings }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current || equityCurve.length === 0) return;

    // 创建图表
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 320,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#666',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: {
        mode: 0, // CrosshairMode.Normal
      },
      rightPriceScale: {
        borderColor: '#e0e0e0',
      },
      timeScale: {
        borderColor: '#e0e0e0',
        timeVisible: false,
      },
    });

    chartRef.current = chart;

    // 策略净值曲线
    const strategyLine: ISeriesApi<'Line'> = chart.addLineSeries({
      color: '#1677ff',
      lineWidth: 2,
      title: '策略净值',
      lastValueVisible: true,
      priceFormat: {
        type: 'percent',
        precision: 1,
      },
    });

    // 基准净值曲线
    const hasBenchmark = equityCurve.some((p) => p.benchmark !== undefined);
    let benchmarkLine: ISeriesApi<'Line'> | undefined;
    if (hasBenchmark) {
      benchmarkLine = chart.addLineSeries({
        color: '#ff4d4f',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        title: '沪深300',
        lastValueVisible: true,
      });
    }

    // 转换数据
    const strategyData = equityCurve.map((p) => ({
      time: p.date,
      value: p.returnPct * 100,
    }));
    strategyLine.setData(strategyData);

    if (benchmarkLine && hasBenchmark) {
      // 基准净值归一化
      const firstBenchmark = equityCurve.find((p) => p.benchmark !== undefined)?.benchmark ?? 1;
      const benchmarkData = equityCurve
        .filter((p) => p.benchmark !== undefined)
        .map((p) => ({
          time: p.date,
          value: ((p.benchmark! / firstBenchmark) - 1) * 100,
        }));
      benchmarkLine.setData(benchmarkData);
    }

    // 调整大小
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [equityCurve]);

  if (equityCurve.length === 0) {
    return (
      <div className="text-text-disabled text-sm text-center py-8">
        无净值数据
      </div>
    );
  }

  return (
    <div>
      {warnings.length > 0 && (
        <div className="mb-2">
          {warnings.map((w, i) => (
            <div key={i} className="text-warning text-xs">{w}</div>
          ))}
        </div>
      )}
      <div ref={chartContainerRef} data-testid="equity-chart" />
    </div>
  );
};

export default EquityChart;