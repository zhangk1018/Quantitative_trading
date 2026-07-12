import { RefObject, useEffect } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  type HistogramData,
  type LineData,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import type { KLineItem, SignalItem } from '../api';
import { validateKLineData, validateSignals } from './chartUtils';

interface StockChartIndicators {
  ma5: boolean;
  ma10: boolean;
  ma20: boolean;
}

interface UseStockChartParams {
  containerRef: RefObject<HTMLDivElement>;
  data: KLineItem[];
  signals: SignalItem[];
  indicators: StockChartIndicators;
}

interface ChartBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

function toChartTime(time: string): Time {
  return time as Time;
}

function buildMovingAverage(data: ChartBar[], period: number): LineData<Time>[] {
  const result: LineData<Time>[] = [];
  for (let i = period - 1; i < data.length; i++) {
    const window = data.slice(i - period + 1, i + 1);
    const sum = window.reduce((acc, item) => acc + item.close, 0);
    result.push({
      time: toChartTime(data[i].time),
      value: Number((sum / period).toFixed(4)),
    });
  }
  return result;
}

function buildVolumeData(data: ChartBar[]): HistogramData<Time>[] {
  return data.map((item) => ({
    time: toChartTime(item.time),
    value: item.volume ?? 0,
    color: item.close >= item.open ? '#26A69A' : '#EF5350',
  }));
}

function buildMarkers(signals: SignalItem[]): SeriesMarker<Time>[] {
  return signals.map((signal) => ({
    time: toChartTime(signal.time),
    position: signal.position === 'inBar' ? 'aboveBar' : signal.position,
    color: signal.color,
    shape: signal.shape,
    text: signal.text,
  }));
}

export function useStockChart({
  containerRef,
  data,
  signals,
  indicators,
}: UseStockChartParams): void {
  useEffect(() => {
    const container = containerRef.current;
    const klineData = validateKLineData(data);
    if (!container || klineData.length === 0) return;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: '#1E222D' },
        textColor: '#848E9C',
      },
      grid: {
        vertLines: { color: '#2A2E39' },
        horzLines: { color: '#2A2E39' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: '#2A2E39',
      },
      timeScale: {
        borderColor: '#2A2E39',
        timeVisible: false,
      },
      autoSize: true,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26A69A',
      downColor: '#EF5350',
      borderUpColor: '#26A69A',
      borderDownColor: '#EF5350',
      wickUpColor: '#26A69A',
      wickDownColor: '#EF5350',
    });

    candleSeries.setData(
      klineData.map((item) => ({
        time: toChartTime(item.time),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      }))
    );

    const markerData = buildMarkers(validateSignals(signals));
    if (markerData.length > 0) {
      candleSeries.setMarkers(markerData);
    }

    const volumeSeries = chart.addHistogramSeries({
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(buildVolumeData(klineData));

    const maSeries = [
      { enabled: indicators.ma5, period: 5, color: '#FBC02D', title: 'MA5' },
      { enabled: indicators.ma10, period: 10, color: '#2962FF', title: 'MA10' },
      { enabled: indicators.ma20, period: 20, color: '#E91E63', title: 'MA20' },
    ];

    maSeries.forEach((ma) => {
      if (!ma.enabled) return;
      const series = chart.addLineSeries({
        color: ma.color,
        lineWidth: 1,
        title: ma.title,
      });
      series.setData(buildMovingAverage(klineData, ma.period));
    });

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
    };
  }, [containerRef, data, signals, indicators.ma5, indicators.ma10, indicators.ma20]);
}
