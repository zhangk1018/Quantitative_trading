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
import { getUpDownColors } from '@/shared/contexts/SettingsContext';

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
  /** 除权除息日（YYYY-MM-DD，从后端 K 响应 ex_dates 透出，协作单 31.0） */
  exDates?: string[];
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
  const { up, down } = getUpDownColors();
  return data.map((item) => ({
    time: toChartTime(item.time),
    value: item.volume ?? 0,
    color: item.close >= item.open ? up : down,
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

/** 除权除息日标注：K 线下方圆点 + 「除权」文本（协作单 31.0） */
function buildExDateMarkers(exDates: string[]): SeriesMarker<Time>[] {
  return exDates
    .filter((d) => d && !isNaN(Date.parse(d)))
    .map((d) => ({
      time: toChartTime(d),
      position: 'belowBar',
      color: '#B39DDB',
      shape: 'circle',
      text: '除权',
    }));
}

/**
 * 缓解信号拥堵：按信号类型分散采样。
 * 后端信号可能存在单一类型高频（如 RSI 连续超买），旧逻辑「只取最近 N 条」会让
 * 密集同类占满名额、标签重叠。现改为每类最多保留最近的 MAX_PER_TYPE 条，
 * 保证 MACD/RSI/布林等不同类型信号均衡可见；总数再加 MAX_SIGNAL_MARKERS 兜底。
 */
const MAX_PER_TYPE = 3;
const MAX_SIGNAL_MARKERS = 12;
function limitSignalMarkers(signals: SeriesMarker<Time>[]): SeriesMarker<Time>[] {
  if (signals.length <= MAX_PER_TYPE) return signals;
  // 按信号类型标签（text）分组；无标签归入兜底组
  const groups = new Map<string, SeriesMarker<Time>[]>();
  for (const m of signals) {
    const key = m.text || 'signal';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(m);
  }
  // 每组按时间降序取最近 MAX_PER_TYPE 条
  let picked: SeriesMarker<Time>[] = [];
  for (const arr of groups.values()) {
    const recent = [...arr]
      .sort((a, b) => Date.parse(String(b.time)) - Date.parse(String(a.time)))
      .slice(0, MAX_PER_TYPE);
    picked.push(...recent);
  }
  // 总数兜底：仍超出则保留最近 MAX_SIGNAL_MARKERS 条
  if (picked.length > MAX_SIGNAL_MARKERS) {
    picked = [...picked]
      .sort((a, b) => Date.parse(String(b.time)) - Date.parse(String(a.time)))
      .slice(0, MAX_SIGNAL_MARKERS);
  }
  // 转回升序供 lightweight-charts 使用
  return picked.sort((a, b) => Date.parse(String(a.time)) - Date.parse(String(b.time)));
}

export function useStockChart({
  containerRef,
  data,
  signals,
  indicators,
  exDates,
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

    const { up, down } = getUpDownColors();
    const candleSeries = chart.addCandlestickSeries({
      upColor: up,
      downColor: down,
      borderUpColor: up,
      borderDownColor: down,
      wickUpColor: up,
      wickDownColor: down,
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
    const exMarkers = buildExDateMarkers(exDates ?? []);
    // 信号单独去重+限量缓解文本堆叠（除权标注量少独立保留），后端信号为降序统一转升序后渲染
    const allMarkers = [...limitSignalMarkers(markerData), ...exMarkers].sort(
      (a, b) => Date.parse(String(a.time)) - Date.parse(String(b.time)),
    );
    if (allMarkers.length > 0) {
      candleSeries.setMarkers(allMarkers);
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

    // 修复：确保图表创建后读取正确的容器尺寸
    const rafId = requestAnimationFrame(() => {
      const { clientWidth, clientHeight } = container;
      if (clientWidth > 0 && clientHeight > 0) {
        chart.resize(clientWidth, clientHeight);
      }
    });

    return () => {
      cancelAnimationFrame(rafId);
      chart.remove();
    };
  }, [containerRef, data, signals, indicators.ma5, indicators.ma10, indicators.ma20, exDates]);
}
