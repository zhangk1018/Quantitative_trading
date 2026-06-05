import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useEchartsTheme } from '../hooks/useEchartsTheme'
import { MA_PERIODS, getMaColor, MA_LEGEND_NAMES } from '../config/klineTheme'
import type { KLineItem } from '../types'

interface KLineChartProps {
  data: KLineItem[]
  loading: boolean
  error: string | null
  stockCode: string | null
  stockName?: string | null
  height?: number
}

const HEADER_HEIGHT = 88

export function KLineChart({
  data,
  loading,
  error,
  stockCode,
  stockName,
  height = 500
}: KLineChartProps) {
  const { theme, resolvedMode } = useEchartsTheme('auto')
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)

  const chartHeight = Math.max(height - HEADER_HEIGHT, 200)

  const prepared = useMemo(() => {
    const reversed = [...data].reverse()
    console.log('KLineChart: 原始数据长度', data.length)
    const dates = reversed.map(d => d.trade_date.slice(5))
    const ohlc: [number, number, number, number][] = reversed.map(d => [
      Number(d.open), Number(d.close), Number(d.low), Number(d.high)
    ])
    const closes = reversed.map(d => Number(d.close))
    const volumes = reversed.map(d => {
      const isUp = Number(d.close) >= Number(d.open)
      return {
        value: Number(d.volume),
        itemStyle: { color: isUp ? theme.up : theme.down }
      }
    })
    const ma: Record<number, (number | null)[]> = {}
    MA_PERIODS.forEach(p => { ma[p] = sma(closes, p) })
    const normalized = reversed.map(d => ({
      trade_date: d.trade_date,
      open: Number(d.open),
      high: Number(d.high),
      low: Number(d.low),
      close: Number(d.close),
      volume: Number(d.volume),
      amount: Number(d.amount)
    }))
    return { dates, ohlc, volumes, ma, reversed: normalized }
  }, [data, theme.up, theme.down])

  const latest = prepared.reversed[prepared.reversed.length - 1] ?? null
  const prev = prepared.reversed[prepared.reversed.length - 2] ?? null
  const preClose = prev?.close ?? latest?.open ?? 0
  const change = latest ? latest.close - preClose : 0
  const changePct = preClose > 0 ? (change / preClose) * 100 : 0
  const changeColor = change > 0 ? theme.up : change < 0 ? theme.down : theme.textMuted
  const changeSign = change > 0 ? '+' : ''

  const option: EChartsOption = useMemo(() => ({
    backgroundColor: theme.panelBg,
    animation: false,
    legend: {
      show: true,
      top: 6,
      left: 10,
      itemWidth: 24,
      itemHeight: 2,
      textStyle: { color: theme.textMuted, fontSize: 11 },
      data: MA_PERIODS.map(p => ({ name: MA_LEGEND_NAMES[p] }))
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: {
        backgroundColor: theme.mode === 'dark' ? '#1a1a1a' : '#ffffff',
        color: theme.text,
        borderColor: theme.axisLine,
        fontSize: 10
      }
    },
    grid: [
      {
        left: 60,
        right: 60,
        top: 30,
        bottom: '25%',
        containLabel: true
      },
      {
        left: 60,
        right: 60,
        top: '78%',
        bottom: 10,
        containLabel: true
      }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: theme.mode === 'dark' ? 'rgba(20,20,20,0.92)' : 'rgba(255,255,255,0.92)',
      borderColor: theme.axisLine,
      textStyle: { color: theme.text, fontSize: 12 },
      formatter: (params: any) => {
        if (!params || params.length === 0) return ''
        const p = Array.isArray(params) ? params : [params]
        const kline = p.find((x: any) => x.seriesName === 'K线')
        if (!kline) return kline?.axisValue || ''
        const idx = kline.dataIndex
        const d = prepared.reversed[prepared.reversed.length - 1 - idx]
        if (!d) return kline.axisValue || ''
        const isUp = d.close >= d.open
        const chg = d.close - (prepared.reversed[prepared.reversed.length - 2 - idx]?.close ?? d.open)
        const chgPct = chg / (prepared.reversed[prepared.reversed.length - 2 - idx]?.close ?? d.open) * 100
        const color = isUp ? theme.up : theme.down
        const sign = chg > 0 ? '+' : ''
        let html = `<div style="font-size:12px;margin-bottom:2px">${d.trade_date}</div>`
        html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 14px;font-size:11px">`
        html += `<span>开: <b>${d.open.toFixed(2)}</b></span><span>高: <b>${d.high.toFixed(2)}</b></span>`
        html += `<span>低: <b>${d.low.toFixed(2)}</b></span><span>收: <b style="color:${color}">${d.close.toFixed(2)}</b> ${sign}${chg.toFixed(2)} ${sign}${chgPct.toFixed(2)}%</span>`
        html += `<span>成交量: <b>${formatVolume(d.volume)}</b></span><span>成交额: <b>${formatAmount(d.amount)}</b></span>`
        html += `</div>`
        const maLines = p.filter((x: any) => x.seriesName?.startsWith('MA'))
        if (maLines.length > 0) {
          html += `<div style="display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:6px;padding-top:6px;border-top:1px solid ${theme.axisLine};font-size:11px">`
          maLines.forEach((m: any) => {
            if (m.value != null) {
              html += `<span style="color:${m.color}">${m.seriesName}: <b>${Number(m.value).toFixed(2)}</b></span>`
            }
          })
          html += `</div>`
        }
        return html
      }
    },
    xAxis: [
      {
        type: 'category',
        data: prepared.dates,
        gridIndex: 0,
        boundaryGap: false,
        axisLine: { lineStyle: { color: theme.axisLine, width: 1 } },
        axisLabel: { show: false },
        splitLine: { show: true, lineStyle: { color: theme.gridLine, type: 'dashed', width: 1 } },
        axisTick: { show: false }
      },
      {
        type: 'category',
        data: prepared.dates,
        gridIndex: 1,
        boundaryGap: false,
        axisLine: { lineStyle: { color: theme.axisLine, width: 1 } },
        axisLabel: { color: theme.textMuted, fontSize: 10 },
        splitLine: { show: false },
        axisTick: { show: false }
      }
    ],
    yAxis: [
      {
        scale: true,
        position: 'right',
        gridIndex: 0,
        axisLine: { show: false },
        axisLabel: {
          showMinLabel: true,
          showMaxLabel: true,
          inside: false,
          color: theme.textMuted,
          fontSize: 10
        },
        splitLine: { show: true, lineStyle: { color: theme.gridLine, type: 'dashed', width: 1 } },
        axisTick: { show: false }
      },
      {
        scale: true,
        position: 'right',
        gridIndex: 1,
        axisLine: { show: false },
        axisLabel: {
          showMinLabel: true,
          showMaxLabel: true,
          inside: false,
          color: theme.textMuted,
          fontSize: 10
        },
        splitLine: { show: false },
        axisTick: { show: false }
      }
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 0,
        end: 100,
        minSpan: 10
      }
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: prepared.ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: theme.up,
          color0: theme.down,
          borderColor: theme.up,
          borderColor0: theme.down,
          borderWidth: 1
        }
      },
      ...MA_PERIODS.map(p => ({
        name: MA_LEGEND_NAMES[p],
        type: 'line' as const,
        data: prepared.ma[p],
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: getMaColor(p, resolvedMode), width: 1.2 }
      })),
      {
        name: 'VOL',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: prepared.volumes
      }
    ]
  }), [prepared, theme, resolvedMode])

  useEffect(() => {
    if (!chartContainerRef.current) return
    const dpr = Math.max(window.devicePixelRatio || 1, 2)
    const instance = echarts.init(chartContainerRef.current, undefined, {
      renderer: 'canvas',
      devicePixelRatio: dpr
    })
    chartInstanceRef.current = instance
    const onResize = () => instance.resize({ animation: { duration: 0 } })
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      instance.dispose()
      chartInstanceRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!chartInstanceRef.current || !option || prepared.ohlc.length === 0) return
    chartInstanceRef.current.setOption(option, {
      notMerge: false,
      lazyUpdate: false
    })
    setTimeout(() => {
      chartInstanceRef.current?.resize()
    }, 100)
  }, [option, prepared.ohlc.length])

  useEffect(() => {
    chartInstanceRef.current?.resize()
  }, [chartHeight])

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden"
      style={{ backgroundColor: theme.panelBg, color: theme.text }}
    >
      <div
        className="px-4 pt-3 pb-2 border-b"
        style={{ backgroundColor: theme.panelBg, borderColor: theme.gridLine }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <div className="flex items-baseline gap-2">
              {stockName && (
                <span className="text-xl font-bold leading-tight">{stockName}</span>
              )}
              {stockCode && (
                <span className="text-sm" style={{ color: theme.textMuted }}>{stockCode}</span>
              )}
            </div>
            {latest && (
              <>
                <span
                  className="text-2xl font-bold leading-tight"
                  style={{ color: changeColor }}
                >
                  {latest.close.toFixed(2)}
                </span>
                <span
                  className="text-sm leading-tight"
                  style={{ color: changeColor }}
                >
                  {changeSign}{change.toFixed(2)} {changeSign}{changePct.toFixed(2)}%
                </span>
              </>
            )}
          </div>
          {latest && (
            <div
              className="grid grid-cols-6 gap-x-4 gap-y-1 text-xs"
              style={{ color: theme.textMuted }}
            >
              <div className="flex items-center gap-1.5">
                <span>高:</span>
                <span style={{ color: theme.up }}>{latest.high.toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>低:</span>
                <span style={{ color: theme.down }}>{latest.low.toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>开:</span>
                <span style={{ color: theme.text }}>{latest.open.toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>市值:</span>
                <span style={{ color: theme.text }}>75.93亿</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>流通:</span>
                <span style={{ color: theme.text }}>75.93亿</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>量比:</span>
                <span style={{ color: theme.text }}>1.04</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>换:</span>
                <span style={{ color: theme.text }}>0.47%</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>市盈TTM:</span>
                <span style={{ color: theme.text }}>7.14</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span>额:</span>
                <span style={{ color: theme.text }}>3569.95万</span>
              </div>
            </div>
          )}
          <div className="flex items-center gap-3 text-sm" style={{ color: theme.textMuted }}>
            <span className="flex items-center gap-1">
              日K
            </span>
          </div>
        </div>
      </div>
      <div style={{ height: chartHeight, position: 'relative', width: '100%' }}>
        <div
          ref={chartContainerRef}
          style={{
            width: '100%',
            height: '100%',
            position: 'absolute',
            top: 0,
            left: 0,
            boxSizing: 'border-box'
          }}
        />
        {loading && (
          <div
            className="absolute inset-0 flex items-center justify-center z-10"
            style={{ backgroundColor: theme.mode === 'dark' ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.7)' }}
          >
            <div className="flex flex-col items-center">
              <div
                className="w-8 h-8 border-4 border-t-transparent rounded-full animate-spin mb-2"
                style={{ borderColor: theme.axisLine, borderTopColor: 'transparent' }}
              />
              <span className="text-sm" style={{ color: theme.textMuted }}>加载中…</span>
            </div>
          </div>
        )}
        {error && (
          <div
            className="absolute inset-0 flex items-center justify-center z-10"
            style={{ backgroundColor: theme.mode === 'dark' ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.7)' }}
          >
            <div className="flex flex-col items-center text-center p-4">
              <div className="text-2xl mb-2" style={{ color: theme.down }}>⚠️</div>
              <span className="font-medium" style={{ color: theme.down }}>加载失败</span>
              <span className="text-sm mt-1" style={{ color: theme.textMuted }}>{error}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function sma(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    result.push(i >= period - 1 ? sum / period : null)
  }
  return result
}

function formatVolume(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿手`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万手`
  return `${v.toFixed(0)}手`
}

function formatAmount(a: number): string {
  if (a >= 1e8) return `${(a / 1e8).toFixed(2)}亿元`
  if (a >= 1e4) return `${(a / 1e4).toFixed(2)}万元`
  return `${a.toFixed(0)}元`
}
