import { useEffect, useRef, useMemo } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi } from 'lightweight-charts';
import type { KLineItem, SignalItem } from '../api';
import { detectAllPatterns } from '../../../lib/indicators/patternDetector';
import type { OHLCVArray, PatternType } from '../../../lib/indicators/types';

interface UseStockChartProps {
  containerRef: React.RefObject<HTMLDivElement>;
  data: KLineItem[];
  signals: SignalItem[];
  indicators: { ma5: boolean; ma10: boolean; ma20: boolean };
}

// 形态标记颜色和文本映射
const PATTERN_MARKER_CONFIG: Record<PatternType, { color: string; text: string; shape: 'arrowUp' | 'arrowDown' }> = {
  hammer: { color: '#2962FF', text: '锤子线', shape: 'arrowUp' },
  bullish_engulfing: { color: '#26A69A', text: '看涨吞没', shape: 'arrowUp' },
  bearish_engulfing: { color: '#EF5350', text: '看跌吞没', shape: 'arrowDown' },
  morning_star: { color: '#26A69A', text: '早晨之星', shape: 'arrowUp' },
  evening_star: { color: '#EF5350', text: '黄昏之星', shape: 'arrowDown' },
};

/** 将 KLineItem[] 转换为 OHLCVArray[] */
function toOHLCVArray(klineData: KLineItem[]): OHLCVArray[] {
  return klineData.map((k) => [
    new Date(k.time).getTime() / 1000,
    k.open,
    k.high,
    k.low,
    k.close,
    k.volume,
  ] as OHLCVArray);
}

/** 检测 K 线形态并生成 markers */
function detectPatternMarkers(
  klineData: KLineItem[],
): { time: string; position: 'aboveBar' | 'belowBar'; shape: 'arrowUp' | 'arrowDown'; color: string; text: string }[] {
  if (!klineData || klineData.length < 3) return [];

  const ohlcv = toOHLCVArray(klineData);
  const result = detectAllPatterns('', ohlcv, { lookbackDays: ohlcv.length });

  const markers: { time: string; position: 'aboveBar' | 'belowBar'; shape: 'arrowUp' | 'arrowDown'; color: string; text: string }[] = [];

  for (const patternType of result.hits) {
    const config = PATTERN_MARKER_CONFIG[patternType];
    if (!config) continue;
    const dayIndices = result.hitDays[patternType];
    if (!dayIndices || dayIndices.length === 0) continue;

    // 取最近的命中日做标记
    const lastHitIndex = dayIndices[dayIndices.length - 1];
    if (lastHitIndex < klineData.length) {
      markers.push({
        time: klineData[lastHitIndex].time,
        position: config.shape === 'arrowUp' ? 'belowBar' : 'aboveBar',
        shape: config.shape,
        color: config.color,
        text: config.text,
      });
    }
  }

  return markers;
}

export const useStockChart = ({ containerRef, data, signals, indicators }: UseStockChartProps) => {
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const seriesRefs = useRef<{ [key: string]: ISeriesApi<'Line'> }>({});

  // 计算 K 线形态标记
  const patternMarkers = useMemo(() => detectPatternMarkers(data), [data]);

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

  // 更新数据、信号与形态标记
  useEffect(() => {
    if (!candleSeriesRef.current || !data.length) return;
    
    candleSeriesRef.current.setData(data);
    
    // 合并交易信号和形态标记
    const allMarkers = [
      ...(signals || []).map((s) => ({
        time: s.time,
        position: s.position as 'aboveBar' | 'belowBar',
        shape: s.shape as 'arrowUp' | 'arrowDown' | 'circle' | 'square',
        color: s.color,
        text: s.text || '',
      })),
      ...patternMarkers,
    ];
    
    if (allMarkers.length > 0) {
      candleSeriesRef.current.setMarkers(allMarkers);
    }
  }, [data, signals, patternMarkers]);

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
