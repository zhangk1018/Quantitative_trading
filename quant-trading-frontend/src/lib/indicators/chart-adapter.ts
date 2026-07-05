// lib/indicators/chart-adapter.ts
// 图表适配层 — 将纯指标数据格式化为 lightweight-charts 可消费的数据结构
// 依赖 lightweight-charts 类型 + indicators 纯算法

import type { LineData, HistogramData, Time } from 'lightweight-charts';
import { cleanBars, calcAllIndicators, type KlineBar } from './indicators';

export interface ChartDataResult {
  candles: { time: Time; open: number; high: number; low: number; close: number }[];
  ma5: LineData<Time>[];
  ma10: LineData<Time>[];
  ma20: LineData<Time>[];
  ma60: LineData<Time>[];
  bollUpper: LineData<Time>[];
  bollMid: LineData<Time>[];
  bollLower: LineData<Time>[];
  volume: HistogramData<Time>[];
  dif: LineData<Time>[];
  dea: LineData<Time>[];
  macdHist: HistogramData<Time>[];
  rsi6: LineData<Time>[];
  rsi12: LineData<Time>[];
  rsi24: LineData<Time>[];
  kdjK: LineData<Time>[];
  kdjD: LineData<Time>[];
  kdjJ: LineData<Time>[];
}

function toLineData(times: string[], values: (number | null)[]): LineData<Time>[] {
  const result: LineData<Time>[] = [];
  for (let i = 0; i < values.length; i++) {
    if (values[i] !== null) {
      result.push({ time: times[i] as Time, value: values[i]! });
    }
  }
  return result;
}

function toHistogramData(
  times: string[], values: (number | null)[], colors: string[]
): HistogramData<Time>[] {
  const result: HistogramData<Time>[] = [];
  for (let i = 0; i < values.length; i++) {
    if (values[i] !== null) {
      result.push({ time: times[i] as Time, value: values[i]!, color: colors[i] });
    }
  }
  return result;
}

export function buildChartData(rawBars: KlineBar[]): ChartDataResult {
  const cleaned = cleanBars(rawBars);
  const ind = calcAllIndicators(cleaned);
  const times = cleaned.map(b => b.time);

  const candles = cleaned.map(b => ({
    time: b.time as Time,
    open: b.open, high: b.high, low: b.low, close: b.close,
  }));

  const volumeData: HistogramData<Time>[] = cleaned.map((b, i) => ({
    time: b.time as Time,
    value: b.volume,
    color: ind.volumeColors[i],
  }));

  const macdHistData: HistogramData<Time>[] = [];
  for (let i = 0; i < cleaned.length; i++) {
    if (ind.macdHist[i] !== null) {
      macdHistData.push({
        time: times[i] as Time,
        value: ind.macdHist[i]!,
        color: ind.macdColors[i],
      });
    }
  }

  return {
    candles,
    ma5: toLineData(times, ind.ma5),
    ma10: toLineData(times, ind.ma10),
    ma20: toLineData(times, ind.ma20),
    ma60: toLineData(times, ind.ma60),
    bollUpper: toLineData(times, ind.bollUpper),
    bollMid: toLineData(times, ind.ma20),  // BOLL中轨 = SMA(20)
    bollLower: toLineData(times, ind.bollLower),
    volume: volumeData,
    dif: toLineData(times, ind.dif),
    dea: toLineData(times, ind.dea),
    macdHist: macdHistData,
    rsi6: toLineData(times, ind.rsi6),
    rsi12: toLineData(times, ind.rsi12),
    rsi24: toLineData(times, ind.rsi24),
    kdjK: toLineData(times, ind.kdjK),
    kdjD: toLineData(times, ind.kdjD),
    kdjJ: toLineData(times, ind.kdjJ),
  };
}

export function makeHorizontalLine(
  times: string[], value: number, color: string
): LineData<Time>[] {
  // 只需首尾两点，图表库会自动连线，大幅减少内存分配
  if (times.length === 0) return [];
  return [
    { time: times[0] as Time, value },
    { time: times[times.length - 1] as Time, value },
  ];
}