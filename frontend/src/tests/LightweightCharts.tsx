import { useEffect, useRef, useState, useCallback } from 'react'
import {
  IChartApi,
  ISeriesApi,
  createChart,
  Time,
} from 'lightweight-charts'
import type { KLineItem } from '../types'

// ============================================
// 常量定义
// ============================================
const VOLUME_SCALE_ID = 'volume'
const UP_COLOR = '#FF4D4F'
const DOWN_COLOR = '#52C41A'
const BORDER_UP_COLOR = '#FF4D4F'
const BORDER_DOWN_COLOR = '#52C41A'
const WICK_UP_COLOR = '#FF4D4F'
const WICK_DOWN_COLOR = '#52C41A'

// ============================================
// 类型定义
// ============================================
interface LightweightChartProps {
  data: KLineItem[]
  loading: boolean
  error: string | null
  stockCode: string | null
  stockName?: string | null
  height?: number
}

interface CandleData {
  time: Time
  open: number
  high: number
  low: number
  close: number
}

interface VolumeData {
  time: Time
  value: number
  color: string
}

interface LineData {
  time: Time
  value: number
}

// ============================================
// 辅助函数
// ============================================

/**
 * 将日期字符串转换为 light-weight-charts 需要的 Time 格式
 */
function toTime(dateStr: string): Time {
  // 处理 YYYY-MM-DD 格式
  const [year, month, day] = dateStr.split('-').map(Number)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/**
 * 转换 KLineItem 为 candle 数据
 */
function prepareCandleData(data: KLineItem[]): CandleData[] {
  return data.map(item => ({
    time: toTime(item.trade_date),
    open: Number(item.open),
    high: Number(item.high),
    low: Number(item.low),
    close: Number(item.close),
  }))
}

/**
 * 转换 KLineItem 为 volume 数据
 */
function prepareVolumeData(data: KLineItem[]): VolumeData[] {
  return data.map(item => {
    const isUp = Number(item.close) >= Number(item.open)
    return {
      time: toTime(item.trade_date),
      value: Number(item.volume),
      color: isUp ? `${UP_COLOR}40` : `${DOWN_COLOR}40`, // 60% 透明度
    }
  })
}

/**
 * 计算 SMA（简单移动平均线）
 */
function calculateSMA(data: KLineItem[], period: number): LineData[] {
  const result: LineData[] = []
  let sum = 0
  
  for (let i = 0; i < data.length; i++) {
    sum += Number(data[i].close)
    if (i >= period) {
      sum -= Number(data[i - period].close)
    }
    if (i >= period - 1) {
      result.push({
        time: toTime(data[i].trade_date),
        value: sum / period,
      })
    }
  }
  
  return result
}

// ============================================
// 组件实现
// ============================================
export function LightweightCharts({
  data,
  loading,
  error,
  stockCode,
  stockName,
  height = 600,
}: LightweightChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainChartRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeChartRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const ma5Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ma10Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ma20Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ma30Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ma60Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const [chartReady, setChartReady] = useState(false)

  // ============================================
  // 初始化图表
  // ============================================
  const initChart = useCallback(() => {
    if (!containerRef.current) return
    
    const container = containerRef.current
    const width = container.clientWidth
    const chartHeight = height - 80 // 预留80px给头部信息

    // 创建图表实例
    const chart = createChart(container, {
      width,
      height: chartHeight,
      layout: {
        background: { type: 'solid' as any, color: '#ffffff' },
        textColor: '#333333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: {
        mode: 1, // 1 = Normal
        vertLine: {
          width: 1,
          color: 'rgba(150, 150, 150, 0.4)',
          style: 3, // 3 = Dashed
        },
        horzLine: {
          width: 1,
          color: 'rgba(150, 150, 150, 0.4)',
          style: 3,
        },
      },
      localization: {
        timeFormatter: (time: Time) => {
          return typeof time === 'string' ? time : ''
        },
      },
    })

    // 设置时间刻度
    chart.timeScale().applyOptions({
      borderColor: '#e0e0e0',
      timeVisible: true,
      secondsVisible: false,
    })

    // ============================================
    // 创建主图 - K线
    // ============================================
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderUpColor: BORDER_UP_COLOR,
      borderDownColor: BORDER_DOWN_COLOR,
      wickUpColor: WICK_UP_COLOR,
      wickDownColor: WICK_DOWN_COLOR,
    })
    mainChartRef.current = candlestickSeries

    // ============================================
    // 创建均线
    // ============================================
    const ma5 = chart.addLineSeries({
      color: '#265FFC',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    ma5Ref.current = ma5

    const ma10 = chart.addLineSeries({
      color: '#FFAA00',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    ma10Ref.current = ma10

    const ma20 = chart.addLineSeries({
      color: '#F564B9',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    ma20Ref.current = ma20

    const ma30 = chart.addLineSeries({
      color: '#00CCC3',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    ma30Ref.current = ma30

    const ma60 = chart.addLineSeries({
      color: '#733ED6',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    ma60Ref.current = ma60

    // ============================================
    // 创建成交量图
    // ============================================
    const volumeSeries = chart.addHistogramSeries({
      color: '#FF4D4F',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: VOLUME_SCALE_ID,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    volumeChartRef.current = volumeSeries

    // 设置成交量的价格刻度
    chart.priceScale(VOLUME_SCALE_ID).applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    })

    // 设置主图的价格刻度
    chart.priceScale('right').applyOptions({
      scaleMargins: {
        top: 0.1,
        bottom: 0.4,
      },
    })

    chartRef.current = chart
    setChartReady(true)

    // ============================================
    // 窗口大小变化处理
    // ============================================
    const handleResize = () => {
      if (containerRef.current) {
        const newWidth = containerRef.current.clientWidth
        chart.applyOptions({ width: newWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [height])

  // ============================================
  // 更新图表数据
  // ============================================
  const updateChartData = useCallback(() => {
    if (!chartReady || !data.length) return
    if (!mainChartRef.current || !volumeChartRef.current) return
    if (!ma5Ref.current || !ma10Ref.current || !ma20Ref.current || !ma30Ref.current || !ma60Ref.current) return

    const candleData = prepareCandleData(data)
    const volumeData = prepareVolumeData(data)

    mainChartRef.current.setData(candleData)
    volumeChartRef.current.setData(volumeData)

    // 设置均线数据
    ma5Ref.current.setData(calculateSMA(data, 5))
    ma10Ref.current.setData(calculateSMA(data, 10))
    ma20Ref.current.setData(calculateSMA(data, 20))
    ma30Ref.current.setData(calculateSMA(data, 30))
    ma60Ref.current.setData(calculateSMA(data, 60))

    // 自适应显示所有数据
    chartRef.current?.timeScale().fitContent()
  }, [chartReady, data])

  // ============================================
  // 生命周期管理
  // ============================================
  useEffect(() => {
    return initChart()
  }, [initChart])

  useEffect(() => {
    updateChartData()
  }, [updateChartData])

  // ============================================
  // 头部信息计算
  // ============================================
  const latest = data[data.length - 1]
  const prev = data[data.length - 2]
  const change = latest ? Number(latest.close) - Number(prev?.close ?? latest.open) : 0
  const changePct = latest && prev ? (change / Number(prev.close)) * 100 : 0
  const changeColor = change > 0 ? 'text-red-500' : change < 0 ? 'text-green-500' : 'text-gray-600'
  const changeSign = change > 0 ? '+' : ''

  return (
    <div className="w-full h-full flex flex-col bg-white">
      {/* 头部信息栏 */}
      <div className="p-4 border-b border-gray-200 flex items-center gap-6">
        <div className="flex items-center gap-3">
          {stockName && (
            <span className="text-xl font-bold text-gray-900">{stockName}</span>
          )}
          {stockCode && (
            <span className="text-sm text-gray-500">{stockCode}</span>
          )}
        </div>
        {latest && (
          <div className="flex items-center gap-4">
            <span className={`text-2xl font-bold ${changeColor}`}>
              {Number(latest.close).toFixed(2)}
            </span>
            <span className={`text-lg ${changeColor}`}>
              {changeSign}{change.toFixed(2)}
            </span>
            <span className={`text-lg ${changeColor}`}>
              {changeSign}{changePct.toFixed(2)}%
            </span>
            <div className="text-sm text-gray-500 ml-6">
              <span className="mr-4">高: {Number(latest.high).toFixed(2)}</span>
              <span className="mr-4">低: {Number(latest.low).toFixed(2)}</span>
              <span className="mr-4">开: {Number(latest.open).toFixed(2)}</span>
              <span>成交量: {Number(latest.volume).toLocaleString()}</span>
            </div>
          </div>
        )}
      </div>

      {/* 图表区域 */}
      <div className="flex-1 relative">
        <div ref={containerRef} className="w-full h-full" />
        
        {/* 加载状态 */}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 border-4 border-t-transparent border-gray-300 rounded-full animate-spin mb-2" />
              <span className="text-sm text-gray-500">加载中...</span>
            </div>
          </div>
        )}

        {/* 错误状态 */}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center text-center p-4">
              <div className="text-4xl mb-2">⚠️</div>
              <span className="font-medium text-red-500">加载失败</span>
              <span className="text-sm mt-1 text-gray-600">{error}</span>
            </div>
          </div>
        )}
      </div>

      {/* 底部图例 */}
      <div className="p-2 border-t border-gray-200 flex items-center gap-4 text-sm">
        <div className="flex items-center gap-1">
          <div className="w-3 h-1" style={{ backgroundColor: '#265FFC' }} />
          <span className="text-gray-600">MA5</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1" style={{ backgroundColor: '#FFAA00' }} />
          <span className="text-gray-600">MA10</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1" style={{ backgroundColor: '#F564B9' }} />
          <span className="text-gray-600">MA20</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1" style={{ backgroundColor: '#00CCC3' }} />
          <span className="text-gray-600">MA30</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1" style={{ backgroundColor: '#733ED6' }} />
          <span className="text-gray-600">MA60</span>
        </div>
      </div>
    </div>
  )
}
