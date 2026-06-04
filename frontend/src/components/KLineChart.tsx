import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, Time, ColorType } from 'lightweight-charts'
import type { KLineItem } from '../types'

interface KLineChartProps {
  data: KLineItem[]
  loading: boolean
  error: string | null
  stockCode: string | null
  height?: number
}

/** 成交量面板占总高度比例 */
const VOLUME_RATIO = 0.28

export function KLineChart({
  data,
  loading,
  error,
  stockCode,
  height = 500
}: KLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  // ---- 创建单个 Chart，使用 priceScaleId 实现 K线/成交量分离 ----
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#555',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#e0e0e0',
      },
      rightPriceScale: {
        borderColor: '#e0e0e0',
        scaleMargins: {
          top: 0.05,           // K线顶部留 5% 边距
          bottom: VOLUME_RATIO + 0.02,  // K线底部留出成交量空间 + 2% 分隔
        },
      },
      crosshair: {
        mode: 0, // CrosshairMode.Normal
      },
    })

    // K线主图：使用默认 right price scale
    const candle = chart.addCandlestickSeries({
      upColor: '#ef4444',
      downColor: '#22c55e',
      borderDownColor: '#22c55e',
      borderUpColor: '#ef4444',
      wickDownColor: '#22c55e',
      wickUpColor: '#ef4444',
    })

    // 成交量：使用 overlay 方式，从底部显示
    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume_scale', // 自定义价格轴 ID，与 K线主轴独立
      color: '#22c55e',
    })

    // 配置成交量的价格轴：放在底部、显示更多刻度
    chart.priceScale('volume_scale').applyOptions({
      scaleMargins: {
        top: 1 - VOLUME_RATIO - 0.01,  // 成交量区域从 71% 开始
        bottom: 0,                      // 一直延伸到图表底部
      },
      borderColor: '#e0e0e0',
      visible: true,
      ticksVisible: true,
    })

    // 成交量的刻度密度调整
    volume.priceScale().applyOptions({
      autoScale: true,
    })

    chartRef.current = chart
    candlestickSeriesRef.current = candle
    volumeSeriesRef.current = volume

    // ---- 响应式 ----
    const onResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height,
        })
      }
    }

    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.remove()
    }
  }, [height])

  // ---- 数据更新 ----
  useEffect(() => {
    if (!candlestickSeriesRef.current || !volumeSeriesRef.current) return

    if (data.length > 0) {
      const candleData = data.map<Parameters<typeof candlestickSeriesRef.current.setData>[0][0]>((item) => ({
        time: item.trade_date as Time,
        open: Number(item.open),
        high: Number(item.high),
        low: Number(item.low),
        close: Number(item.close),
      }))

      const volumeData = data.map((item) => {
        const isUp = Number(item.close) >= Number(item.open)
        return {
          time: item.trade_date as Time,
          value: item.volume,
          color: isUp ? 'rgba(239, 68, 68, 0.5)' : 'rgba(34, 197, 94, 0.5)',
        }
      })

      candlestickSeriesRef.current.setData(candleData)
      volumeSeriesRef.current.setData(volumeData)

      // 数据设置后自动适配可见范围
      chartRef.current?.timeScale().fitContent()
    } else {
      candlestickSeriesRef.current.setData([])
      volumeSeriesRef.current.setData([])
    }
  }, [data])

  return (
    <div className="w-full h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-white">
          {stockCode ? `${stockCode} - K线图` : 'K线图'}
        </h3>
      </div>

      <div className="relative">
        {/* 单个图表容器，K线和成交量叠加显示 */}
        <div
          ref={containerRef}
          className="w-full border border-gray-200 overflow-hidden"
          style={{ height }}
        />

        {/* 加载遮罩 */}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
              <span className="text-gray-600">加载中...</span>
            </div>
          </div>
        )}

        {/* 错误遮罩 */}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center text-center p-4">
              <div className="text-red-500 text-2xl mb-2">⚠️</div>
              <span className="text-red-600 font-medium">加载失败</span>
              <span className="text-gray-500 text-sm mt-1">{error}</span>
            </div>
          </div>
        )}

        {/* 空状态 */}
        {!loading && !error && data.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="text-center text-gray-500">
              <div className="text-4xl mb-2">📊</div>
              <p>请选择股票查看K线图</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
