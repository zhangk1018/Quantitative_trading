/**
 * utils/indicators.ts - 前端技术指标计算
 *
 * 数据来源决策：
 * - 后端每个 KLineItem 已附带 ma5/ma10/ma20/rsi_6/macd/boll 预计算字段
 * - 但为保证渲染效率和字段完整性，本模块统一计算全部指标（含后端未提供的字段）
 * - 前端计算的指标与 klineCache 缓存配合，避免重复序列化
 * - 如需与后端指标对齐验证，可对比 KLineItem.ma5 与 IndicatorSeries.ma5
 *
 * 数据排序约定：所有收盘价/最高价/最低价数组按日期从新到旧（DESCENDING）
 * - values[0] = 最新交易日
 * - values[length-1] = 最旧交易日
 * - 与 klineCache 存储约定一致
 * - 与轻量级图表组件输入约定相反（图表需要从旧到新）
 *
 * 与后端 technical_indicator.py 算法一致（保持数值同步）：
 * - MA: 简单移动平均
 * - RSI: Wilder 平滑算法
 * - MACD: EMA 差离指标
 * - BOLL: 布林带（20日 SMA ± 2σ）
 * - KDJ: 随机指标
 *
 * 数据按"日期从新到旧"传入（与 KLine API 返回顺序一致）
 */

export interface IndicatorSeries {
  /** 与 K线日期一一对应：data[i] 对应 items[i].trade_date */
  dates: string[]
  ma5: (number | null)[]
  ma10: (number | null)[]
  ma20: (number | null)[]
  ma30: (number | null)[]
  ma60: (number | null)[]
  rsi6: (number | null)[]
  /** MACD 三线：DIF / DEA / MACD */
  macd: { dif: (number | null)[]; dea: (number | null)[]; macd: (number | null)[] }
  /** 布林带：上轨 / 中轨 / 下轨 */
  boll: { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] }
  /** KDJ 三线：K / D / J */
  kdj: { k: (number | null)[]; d: (number | null)[]; j: (number | null)[] }
}

interface KLineLite {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

/**
 * 简单移动平均（MA）
 * @param values 收盘价数组（从新到旧）
 * @param period 周期
 * @returns 同长度数组，前 period-1 个为 null
 */
function sma(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    // values[0] 是最新，values[period-1] 是 period 前的收盘价
    // 即最新 MA = (values[0] + values[1] + ... + values[period-1]) / period
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    result.push(i >= period - 1 ? sum / period : null)
  }
  return result
}

/**
 * EMA 指数移动平均
 * @param values 收盘价数组（从新到旧）
 * @param period 周期
 * @returns 同长度数组，前 period-1 个为 null
 *
 * 算法（与后端保持一致）：先以首期 SMA 种子，再 K=2/(period+1) 递推
 */
function ema(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  const k = 2 / (period + 1)
  let prev: number = 0

  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) {
      result.push(null)
      continue
    }
    if (i === period - 1) {
      // 种子 = 前 period 根的 SMA
      let s = 0
      for (let j = 0; j < period; j++) s += values[j]
      prev = s / period
      result.push(prev)
      continue
    }
    // values[i] 是新一期，prev 是上一期 EMA
    prev = values[i] * k + prev * (1 - k)
    result.push(prev)
  }
  return result
}

/**
 * RSI 相对强弱指标（Wilder 平滑）
 * @param values 收盘价数组（从新到旧）
 * @param period 周期（默认 6，与后端一致）
 * @returns 同长度数组，前 period 个为 null
 */
function rsi(values: number[], period = 6): (number | null)[] {
  const result: (number | null)[] = []
  if (values.length <= period) return values.map(() => null)

  // 变化数组：diff[i] = values[i] - values[i+1]（i 越新，i+1 越旧）
  const diff: number[] = []
  for (let i = 0; i < values.length - 1; i++) {
    diff.push(values[i] - values[i + 1])
  }

  // 前 period 个 rsi 为 null
  for (let i = 0; i < period; i++) result.push(null)

  // rsi[period] 种子：用 diff[0..period-1] 的平均
  let avgGain = 0
  let avgLoss = 0
  for (let i = 0; i < period; i++) {
    if (diff[i] > 0) avgGain += diff[i]
    else avgLoss += -diff[i]
  }
  avgGain /= period
  avgLoss /= period
  // 边界处理：当 avgLoss === 0（全涨或全跌）时，RSI 设为 100
  // 与后端 backend/clean/processor/technical_indicator.py:228-231 保持一致
  result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss))

  // 后续递推：rsi[t] 用 diff[t-period..t-1]
  for (let t = period + 1; t < values.length; t++) {
    const d = diff[t - 1]
    const gain = d > 0 ? d : 0
    const loss = d < 0 ? -d : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    // 边界处理：与种子保持一致
    result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss))
  }
  return result
}

/**
 * MACD 指标（12, 26, 9）
 * DIF = EMA12 - EMA26
 * DEA = EMA9(DIF)
 * MACD = 2 * (DIF - DEA)
 */
function macd(values: number[]): { dif: (number | null)[]; dea: (number | null)[]; macd: (number | null)[] } {
  const ema12 = ema(values, 12)
  const ema26 = ema(values, 26)

  // DIF 数组：ema12[i] - ema26[i]，但 ema26 在前 25 个是 null，所以前 25 个 DIF 也是 null
  const difRaw: (number | null)[] = values.map((_, i) => {
    if (ema12[i] === null || ema26[i] === null) return null
    return (ema12[i] as number) - (ema26[i] as number)
  })

  // DEA 是 DIF 的 EMA9，但 EMA 算法需要数字数组。把 null 替换为 0 处理
  // 更安全：DIF 非 null 的部分单独做 EMA，再映射回去
  const difValues: number[] = []
  const difIndexMap: number[] = [] // 记录每个 dif value 对应的原数组下标
  for (let i = 0; i < difRaw.length; i++) {
    if (difRaw[i] !== null) {
      difValues.push(difRaw[i] as number)
      difIndexMap.push(i)
    }
  }
  const deaCompact = ema(difValues, 9)
  const dea: (number | null)[] = values.map(() => null)
  for (let i = 0; i < deaCompact.length; i++) {
    dea[difIndexMap[i]] = deaCompact[i]
  }

  // MACD = 2 * (DIF - DEA)
  const macdArr: (number | null)[] = values.map((_, i) => {
    if (difRaw[i] === null || dea[i] === null) return null
    return 2 * ((difRaw[i] as number) - (dea[i] as number))
  })

  return { dif: difRaw, dea, macd: macdArr }
}

/**
 * 布林带（20日 SMA ± 2σ）
 */
function boll(values: number[]): { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] } {
  const mid = sma(values, 20)
  const upper: (number | null)[] = []
  const lower: (number | null)[] = []

  for (let i = 0; i < values.length; i++) {
    if (mid[i] === null) {
      upper.push(null)
      lower.push(null)
      continue
    }
    // 计算最近 20 根的标准差
    let sumSq = 0
    for (let j = 0; j < 20; j++) {
      const diff = values[i + j] - (mid[i] as number)
      sumSq += diff * diff
    }
    const std = Math.sqrt(sumSq / 20)
    upper.push((mid[i] as number) + 2 * std)
    lower.push((mid[i] as number) - 2 * std)
  }
  return { upper, mid, lower }
}

/**
 * KDJ 随机指标（9, 3, 3）
 * RSV = (C - L9) / (H9 - L9) * 100
 * K = 2/3 * K_prev + 1/3 * RSV  (K 初始 50)
 * D = 2/3 * D_prev + 1/3 * K    (D 初始 50)
 * J = 3K - 2D
 */
function kdj(
  highs: number[],
  lows: number[],
  closes: number[]
): { k: (number | null)[]; d: (number | null)[]; j: (number | null)[] } {
  const k: (number | null)[] = []
  const d: (number | null)[] = []
  const j: (number | null)[] = []
  const period = 9

  let kPrev = 50
  let dPrev = 50

  for (let i = 0; i < closes.length; i++) {
    if (i > highs.length - period) {
      // 前 period-1 个为 null（需要 period 根数据）
      k.push(null)
      d.push(null)
      j.push(null)
      continue
    }
    // 找最近 9 根的最高/最低（values[0..8]）
    let h9 = -Infinity
    let l9 = Infinity
    for (let p = 0; p < period; p++) {
      if (highs[i + p] > h9) h9 = highs[i + p]
      if (lows[i + p] < l9) l9 = lows[i + p]
    }
    const rsv = h9 === l9 ? 50 : ((closes[i] - l9) / (h9 - l9)) * 100
    const kNew = (2 * kPrev + rsv) / 3
    const dNew = (2 * dPrev + kNew) / 3
    kPrev = kNew
    dPrev = dNew
    k.push(kNew)
    d.push(dNew)
    j.push(3 * kNew - 2 * dNew)
  }
  return { k, d, j }
}

/**
 * 计算所有技术指标
 * @param items K线数据（从新到旧）
 * @returns 指标序列
 */
export function computeAllIndicators(items: KLineLite[]): IndicatorSeries {
  if (items.length === 0) {
    return {
      dates: [],
      ma5: [],
      ma10: [],
      ma20: [],
      ma30: [],
      ma60: [],
      rsi6: [],
      macd: { dif: [], dea: [], macd: [] },
      boll: { upper: [], mid: [], lower: [] },
      kdj: { k: [], d: [], j: [] },
    }
  }

  const dates = items.map(i => i.trade_date)
  const closes = items.map(i => i.close)
  const highs = items.map(i => i.high)
  const lows = items.map(i => i.low)

  return {
    dates,
    ma5: sma(closes, 5),
    ma10: sma(closes, 10),
    ma20: sma(closes, 20),
    ma30: sma(closes, 30),
    ma60: sma(closes, 60),
    rsi6: rsi(closes, 6),
    macd: macd(closes),
    boll: boll(closes),
    kdj: kdj(highs, lows, closes),
  }
}
