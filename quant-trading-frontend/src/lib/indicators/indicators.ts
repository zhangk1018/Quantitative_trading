// lib/indicators/indicators.ts
// 纯技术指标算法层 — 零外部依赖，仅操作 number[]
// 可在回测、批量计算等无 UI 场景直接使用

export interface KlineBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CalculatedIndicators {
  ma5: (number | null)[];
  ma10: (number | null)[];
  ma20: (number | null)[];
  ma60: (number | null)[];
  bollUpper: (number | null)[];
  bollLower: (number | null)[];
  dif: (number | null)[];
  dea: (number | null)[];
  macdHist: (number | null)[];
  macdColors: string[];
  rsi6: (number | null)[];
  rsi12: (number | null)[];
  rsi24: (number | null)[];
  kdjK: (number | null)[];
  kdjD: (number | null)[];
  kdjJ: (number | null)[];
  volumeColors: string[];
}

// ---- 通用工具 ----

/**
 * 安全格式化数值：将 null/undefined/NaN 转为占位符 "--"
 * 避免图表界面渲染 "NaN" 或 "undefined"
 */
export function sanitizeNumber(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined) return '--';
  if (!Number.isFinite(v)) return '--';
  return v.toFixed(decimals);
}

/** 安全格式化百分比：含 +/- 符号 */
export function sanitizePct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '--';
  if (!Number.isFinite(v)) return '--';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

// ---- 数据清洗 ----

function toNumber(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

export function cleanBars(bars: KlineBar[]): KlineBar[] {
  return bars.filter(b =>
    Number.isFinite(b.open) &&
    Number.isFinite(b.high) &&
    Number.isFinite(b.low) &&
    Number.isFinite(b.close) &&
    Number.isFinite(b.volume) &&
    b.high >= b.low &&
    b.open > 0 && b.high > 0 && b.low > 0 && b.close > 0
  );
}

// ---- 平滑移动平均（滑动窗口 O(n)） ----

export function sma(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) result[i] = sum / period;
  }
  return result;
}

export function ema(values: (number | null)[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(values.length).fill(null);
  const k = 2 / (period + 1);
  let prev: number | null = null;
  let count = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v === null || !Number.isFinite(v)) {
      if (prev !== null) count++;
      continue;
    }
    if (prev === null) {
      prev = v;
      count = 1;
      if (count >= period) result[i] = prev;
      continue;
    }
    prev = v * k + prev * (1 - k);
    count++;
    result[i] = count >= period ? prev : null;
  }
  return result;
}

// ---- 标准差（样本标准差，分母 n-1） ----

export function sampleStdDev(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(values.length).fill(null);
  const smaVals = sma(values, period);
  for (let i = period - 1; i < values.length; i++) {
    const mean = smaVals[i]!;
    let sqSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const diff = values[j] - mean;
      sqSum += diff * diff;
    }
    result[i] = Math.sqrt(sqSum / (period - 1));
  }
  return result;
}

// ---- 窗口极值（KDJ 用） ----

function windowExtremes(values: number[], period: number, mode: 'min' | 'max'): (number | null)[] {
  const result: (number | null)[] = new Array(values.length).fill(null);
  for (let i = period - 1; i < values.length; i++) {
    let ext = values[i - period + 1];
    for (let j = i - period + 2; j <= i; j++) {
      if (mode === 'min') { if (values[j] < ext) ext = values[j]; }
      else { if (values[j] > ext) ext = values[j]; }
    }
    result[i] = ext;
  }
  return result;
}

// ---- RSI（Wilder 平滑） ----

export function calcRSI(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length <= period) return result;

  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const delta = closes[i] - closes[i - 1];
    if (delta > 0) avgGain += delta;
    else avgLoss -= delta;
  }
  avgGain /= period;
  avgLoss /= period;

  if (avgLoss === 0) result[period] = 100;
  else result[period] = 100 - 100 / (1 + avgGain / avgLoss);

  for (let i = period + 1; i < closes.length; i++) {
    const delta = closes[i] - closes[i - 1];
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? -delta : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    if (avgLoss === 0) result[i] = 100;
    else if (avgGain === 0) result[i] = 0;
    else result[i] = 100 - 100 / (1 + avgGain / avgLoss);
  }
  return result;
}

// ---- KDJ（9/3/3 标准参数） ----

export function calcKDJ(
  highs: number[], lows: number[], closes: number[],
  n = 9, m1 = 3, m2 = 3
): { K: (number | null)[]; D: (number | null)[]; J: (number | null)[] } {
  const llv = windowExtremes(lows, n, 'min');
  const hhv = windowExtremes(highs, n, 'max');
  const K: (number | null)[] = new Array(closes.length).fill(null);
  const D: (number | null)[] = new Array(closes.length).fill(null);
  const J: (number | null)[] = new Array(closes.length).fill(null);

  let prevK = 50;
  let prevD = 50;
  const a1 = (m1 - 1) / m1;
  const b1 = 1 / m1;
  const a2 = (m2 - 1) / m2;
  const b2 = 1 / m2;

  for (let i = 0; i < closes.length; i++) {
    if (llv[i] === null || hhv[i] === null) continue;
    const diff = hhv[i]! - llv[i]!;
    const rsv = diff === 0 ? 50 : ((closes[i] - llv[i]!) / diff) * 100;
    const kVal = a1 * prevK + b1 * rsv;
    const dVal = a2 * prevD + b2 * kVal;
    const jVal = 3 * kVal - 2 * dVal;
    K[i] = kVal;
    D[i] = dVal;
    J[i] = jVal;
    prevK = kVal;
    prevD = dVal;
  }
  return { K, D, J };
}

// ---- 全量指标一次性计算 ----

export function calcAllIndicators(bars: KlineBar[]): CalculatedIndicators {
  const cleaned = cleanBars(bars);
  const closes = cleaned.map(b => b.close);
  const highs = cleaned.map(b => b.high);
  const lows = cleaned.map(b => b.low);

  const ma5 = sma(closes, 5);
  const ma10 = sma(closes, 10);
  const ma20 = sma(closes, 20);
  const ma60 = sma(closes, 60);

  const std20 = sampleStdDev(closes, 20);
  const bollUpper: (number | null)[] = new Array(closes.length).fill(null);
  const bollLower: (number | null)[] = new Array(closes.length).fill(null);
  for (let i = 0; i < closes.length; i++) {
    if (ma20[i] !== null && std20[i] !== null) {
      bollUpper[i] = ma20[i]! + 2 * std20[i]!;
      bollLower[i] = ma20[i]! - 2 * std20[i]!;
    }
  }

  const ema12 = ema(closes as (number | null)[], 12);
  const ema26 = ema(closes as (number | null)[], 26);
  const difRaw: (number | null)[] = new Array(closes.length).fill(null);
  for (let i = 0; i < closes.length; i++) {
    if (ema12[i] !== null && ema26[i] !== null) {
      difRaw[i] = ema12[i]! - ema26[i]!;
    }
  }
  const dea = ema(difRaw, 9);
  const macdHist: (number | null)[] = new Array(closes.length).fill(null);
  const macdColors: string[] = new Array(closes.length).fill('#00d4aa');
  for (let i = 0; i < closes.length; i++) {
    if (difRaw[i] !== null && dea[i] !== null) {
      const d = difRaw[i]!;
      const e = dea[i]!;
      macdHist[i] = 2 * (d - e);
      macdColors[i] = d >= e ? '#f23645' : '#00d4aa';
    }
  }

  const rsi6 = calcRSI(closes, 6);
  const rsi12 = calcRSI(closes, 12);
  const rsi24 = calcRSI(closes, 24);

  const kdj = calcKDJ(highs, lows, closes, 9, 3, 3);

  const volumeColors: string[] = cleaned.map(b =>
    b.close >= b.open ? 'rgba(0,212,170,0.6)' : 'rgba(242,54,69,0.6)'
  );

  return {
    ma5, ma10, ma20, ma60,
    bollUpper, bollLower,
    dif: difRaw, dea, macdHist, macdColors,
    rsi6, rsi12, rsi24,
    kdjK: kdj.K, kdjD: kdj.D, kdjJ: kdj.J,
    volumeColors,
  };
}