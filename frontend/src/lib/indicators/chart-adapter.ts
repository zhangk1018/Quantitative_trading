// lib/indicators/chart-adapter.ts
// 图表适配层 — 将纯指标数据格式化为 lightweight-charts 可消费的数据结构
// 依赖 lightweight-charts 类型 + indicators 纯算法

import type { LineData, HistogramData, Time } from 'lightweight-charts';
import { cleanBars, calcAllIndicators, type KlineBar } from './indicators';
import { getVolumeColors } from './chart-config';

export interface RawBarDetail {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  pe_ttm: number | null;
  turnover_rate: number | null;
  preClose: number | null;
}

// 扩展的 KlineBar，包含额外字段（不影响指标计算）
interface ExtendedKlineBar extends KlineBar {
  amount?: number;
  pe_ttm?: number | null;
  turnover_rate?: number | null;
}

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
  rawBars: RawBarDetail[];
}

/**
 * 将时间数组和值数组转为 LineData
 * 自动过滤掉 value 为 null 的项
 */
function toLineData(times: string[], values: (number | null)[]): LineData<Time>[] {
  const result: LineData<Time>[] = [];
  for (let i = 0; i < values.length; i++) {
    if (values[i] !== null) {
      result.push({ time: times[i] as Time, value: values[i]! });
    }
  }
  return result;
}

/**
 * 构建图表数据 - 核心清洗逻辑
 * 确保返回的所有时间序列均严格升序且无重复时间戳
 */
export function buildChartData(rawBarsInput: ExtendedKlineBar[]): ChartDataResult {
  // 1. 排序（升序）
  const sorted = [...rawBarsInput].sort((a, b) => {
    if (typeof a.time === 'number' && typeof b.time === 'number') return a.time - b.time;
    if (typeof a.time === 'string' && typeof b.time === 'string') return a.time.localeCompare(b.time);
    return String(a.time).localeCompare(String(b.time));
  });

  // 2. 去重（保留第一个，因为已升序）
  const seen = new Set<string>();
  const deduped = sorted.filter((item) => {
    const key = String(item.time);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // 如果数据为空，直接返回空结构（防止后续崩溃）
  if (deduped.length === 0) {
    return {
      candles: [],
      ma5: [],
      ma10: [],
      ma20: [],
      ma60: [],
      bollUpper: [],
      bollMid: [],
      bollLower: [],
      volume: [],
      dif: [],
      dea: [],
      macdHist: [],
      rsi6: [],
      rsi12: [],
      rsi24: [],
      kdjK: [],
      kdjD: [],
      kdjJ: [],
      rawBars: [],
    };
  }

  // 3. 清洗（去除异常值）
  const cleaned = cleanBars(deduped);
  const times = cleaned.map(b => b.time);

  // 4. 计算所有指标（基于清洗后的数据）
  const ind = calcAllIndicators(cleaned);

  // 5. 构建原始数据详情（包含前收盘价用于涨跌计算）
  const rawBars: RawBarDetail[] = cleaned.map((b, i) => {
    const ext = b as ExtendedKlineBar;
    const prevClose = i > 0 ? cleaned[i - 1].close : null;
    return {
      time: b.time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
      amount: ext.amount ?? 0,
      pe_ttm: ext.pe_ttm ?? null,
      turnover_rate: ext.turnover_rate ?? null,
      preClose: prevClose,
    };
  });

  // 6. 构建 candles
  const candles = cleaned.map(b => ({
    time: b.time as Time,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));

  // 7. 成交量（根据涨跌着色）
  const volColors = getVolumeColors();
  const volumeData: HistogramData<Time>[] = cleaned.map((b) => ({
    time: b.time as Time,
    value: b.volume,
    color: b.close >= b.open ? volColors.up : volColors.down,
  }));

  // 8. MACD 柱状图（仅非 null 值）
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

  // 9. 统一返回所有数据（所有指标均基于同一个 times 列表，保证时间对齐）
  return {
    candles,
    ma5: toLineData(times, ind.ma5),
    ma10: toLineData(times, ind.ma10),
    ma20: toLineData(times, ind.ma20),
    ma60: toLineData(times, ind.ma60),
    bollUpper: toLineData(times, ind.bollUpper),
    bollMid: toLineData(times, ind.ma20), // 布林中轨即 MA20
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
    rawBars,
  };
}

/**
 * 生成水平参考线（仅首尾两个点，高效）
 */
export function makeHorizontalLine(
  times: string[],
  value: number,
  _color: string
): LineData<Time>[] {
  if (times.length === 0) return [];
  return [
    { time: times[0] as Time, value },
    { time: times[times.length - 1] as Time, value },
  ];
}