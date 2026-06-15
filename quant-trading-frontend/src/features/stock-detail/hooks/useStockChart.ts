import { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi } from 'lightweight-charts';
import type { KLineItem, SignalItem } from '../api';

interface UseStockChartProps {
  containerRef: React.RefObject<HTMLDivElement>;
  data: KLineItem[];
  signals: SignalItem[];
  indicators: { ma5: boolean; ma10: boolean; ma20: boolean };
}

export const useStockChart = ({ containerRef, data, signals, indicators }: UseStockChartProps) => {
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const seriesRefs = useRef<{ [key: string]: ISeriesApi<'Line'> }>({});

  // 初始化图表
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1E222D' },
        textColor: '#848E9C',
      },
      grid: {
        vertLines: { color: '#2A2E39' },
        horzLines: { color: '#2A2E39' },
      },
      width: containerRef.current.clientWidth,
      height: 450,
      timeScale: { borderColor: '#2A2E39' },
    });

    chartRef.current = chart;

    // 添加 K 线系列并保存引用
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26A69A', downColor: '#EF5350',
      borderVisible: false, wickUpColor: '#26A69A', wickDownColor: '#EF5350',
    });
    candleSeriesRef.current = candleSeries;

    // 响应式处理
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // 更新数据与信号
  useEffect(() => {
    if (!candleSeriesRef.current || !data.length) return;
    
    candleSeriesRef.current.setData(data);
    if (signals.length > 0) {
      candleSeriesRef.current.setMarkers(signals as any);
    }
  }, [data, signals]);

  // 动态更新均线
  useEffect(() => {
    if (!chartRef.current || !data.length) return;

    const calculateMA = (period: number) => {
      return data.map((item, index) => {
        if (index < period - 1) return { time: item.time, value: NaN };
        const sum = data.slice(index - period + 1, index + 1).reduce((a, b) => a + b.close, 0);
        return { time: item.time, value: sum / period };
      }).filter(d => !isNaN(d.value as number));
    };

    const updateSeries = (key: string, period: number, isActive: boolean, color: string) => {
      if (isActive) {
        if (!seriesRefs.current[key]) {
          const series = chartRef.current!.addLineSeries({ color, lineWidth: 1 });
          seriesRefs.current[key] = series;
        }
        seriesRefs.current[key].setData(calculateMA(period));
      } else {
        if (seriesRefs.current[key]) {
          chartRef.current!.removeSeries(seriesRefs.current[key]);
          delete seriesRefs.current[key];
        }
      }
    };

    updateSeries('ma5', 5, indicators.ma5, '#FBC02D');
    updateSeries('ma10', 10, indicators.ma10, '#2962FF');
    updateSeries('ma20', 20, indicators.ma20, '#E91E63');

  }, [data, indicators]);
};
