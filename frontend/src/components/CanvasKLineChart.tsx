import { useEffect, useRef, useMemo, useCallback } from 'react'
import type { KLineItem } from '../types'

const RED = '#FF4D4F'
const GREEN = '#52C41A'
const GRID_COLOR = '#F0F0F0'
const TEXT_COLOR = '#8C8C8C'

const MA_COLORS: Record<number, string> = {
  5: '#265FFC',
  10: '#FFAA00',
  20: '#F564B9',
  30: '#00CCC3',
  60: '#733ED6',
}

const HEADER_HEIGHT = 80
const VOLUME_HEIGHT_RATIO = 0.25
const PADDING = { left: 60, right: 60, top: 30, bottom: 30 }
const MA_PERIODS = [5, 10, 20, 30, 60]

interface CanvasKLineChartProps {
  data: KLineItem[]
  loading: boolean
  error: string | null
  stockCode: string | null
  stockName?: string | null
  height?: number
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

function formatDate(dateStr: string): string {
  if (!dateStr || dateStr.length < 10) return dateStr
  return dateStr.slice(5)
}

function formatNumber(n: number, decimals = 2): string {
  return n.toFixed(decimals)
}

export function CanvasKLineChart({
  data,
  loading,
  error,
  stockCode,
  stockName,
  height = 600,
}: CanvasKLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const state = useRef({
    startIndex: 0,
    endIndex: data.length,
    isDragging: false,
    dragStartX: 0,
    dragStartIndex: 0,
  })

  const preparedData = useMemo(() => {
    const reversed = [...data].reverse()
    const closes = reversed.map(d => Number(d.close))
    const mas: Record<number, (number | null)[]> = {}
    MA_PERIODS.forEach(p => {
      mas[p] = sma(closes, p)
    })
    return { reversed, closes, mas }
  }, [data])

  const chartHeight = height - HEADER_HEIGHT
  const klineHeight = chartHeight * (1 - VOLUME_HEIGHT_RATIO)
  const volumeHeight = chartHeight * VOLUME_HEIGHT_RATIO

  const render = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const rect = container.getBoundingClientRect()
    const width = rect.width

    const dpr = Math.max(window.devicePixelRatio || 1, 2)
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.scale(dpr, dpr)

    ctx.fillStyle = '#FFFFFF'
    ctx.fillRect(0, 0, width, height)

    const latest = preparedData.reversed[preparedData.reversed.length - 1]
    const prevClose = preparedData.reversed[preparedData.reversed.length - 2]?.close || latest?.open || 0
    const latestClose = latest?.close || 0
    const change = latestClose - Number(prevClose)
    const changePct = prevClose > 0 ? (change / Number(prevClose)) * 100 : 0
    const changeColor = change > 0 ? RED : change < 0 ? GREEN : TEXT_COLOR
    const changeSign = change > 0 ? '+' : ''

    ctx.fillStyle = '#FFFFFF'
    ctx.fillRect(0, 0, width, HEADER_HEIGHT)
    ctx.strokeStyle = GRID_COLOR
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, HEADER_HEIGHT - 1)
    ctx.lineTo(width, HEADER_HEIGHT - 1)
    ctx.stroke()

    ctx.font = 'bold 20px Arial'
    ctx.fillStyle = '#000000'
    ctx.textBaseline = 'top'
    let xPos = 12
    if (stockName) {
      ctx.fillText(stockName, xPos, 10)
      xPos += ctx.measureText(stockName).width + 10
    }
    if (stockCode) {
      ctx.font = '14px Arial'
      ctx.fillStyle = TEXT_COLOR
      ctx.fillText(stockCode, xPos, 14)
      xPos += ctx.measureText(stockCode).width + 15
    }
    if (latest) {
      ctx.font = 'bold 22px Arial'
      ctx.fillStyle = changeColor
      ctx.fillText(formatNumber(latestClose), xPos, 8)
      xPos += ctx.measureText(formatNumber(latestClose)).width + 10
      ctx.font = '14px Arial'
      ctx.fillText(`${changeSign}${formatNumber(change)}`, xPos, 14)
      xPos += ctx.measureText(`${changeSign}${formatNumber(change)}`).width + 8
      ctx.fillText(`${changeSign}${formatNumber(changePct)}%`, xPos, 14)
    }

    const chartTop = HEADER_HEIGHT
    const klineTop = chartTop
    const volumeTop = chartTop + klineHeight

    const klineWidth = width - PADDING.left - PADDING.right
    const klineDataStart = PADDING.left
    const klineDataEnd = width - PADDING.right

    let startIdx = state.current.startIndex
    let endIdx = state.current.endIndex
    if (endIdx <= startIdx) endIdx = startIdx + 100
    if (endIdx > preparedData.reversed.length) endIdx = preparedData.reversed.length
    if (startIdx < 0) startIdx = 0

    const visibleData = preparedData.reversed.slice(startIdx, endIdx)
    const visibleMas = MA_PERIODS.reduce((acc, p) => {
      acc[p] = preparedData.mas[p].slice(startIdx, endIdx)
      return acc
    }, {} as Record<number, (number | null)[]>)

    if (visibleData.length === 0) return

    let minPrice = Infinity
    let maxPrice = -Infinity
    visibleData.forEach(d => {
      minPrice = Math.min(minPrice, Number(d.low))
      maxPrice = Math.max(maxPrice, Number(d.high))
    })
    MA_PERIODS.forEach(p => {
      visibleMas[p].forEach(v => {
        if (v !== null) {
          minPrice = Math.min(minPrice, v)
          maxPrice = Math.max(maxPrice, v)
        }
      })
    })

    const pricePadding = (maxPrice - minPrice) * 0.1
    minPrice -= pricePadding
    maxPrice += pricePadding

    const candleWidth = (klineWidth) / visibleData.length
    const barWidth = Math.max(candleWidth * 0.7, 1)

    ctx.strokeStyle = GRID_COLOR
    ctx.lineWidth = 0.5
    ctx.setLineDash([4, 4])

    const priceStep = (maxPrice - minPrice) / 4
    for (let i = 0; i <= 4; i++) {
      const y = klineTop + PADDING.top + (klineHeight - PADDING.top - PADDING.bottom) * (1 - i / 4)
      ctx.beginPath()
      ctx.moveTo(klineDataStart, y)
      ctx.lineTo(klineDataEnd, y)
      ctx.stroke()
    }

    ctx.setLineDash([])
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.font = '10px Arial'
    ctx.fillStyle = TEXT_COLOR
    for (let i = 0; i <= 4; i++) {
      const y = klineTop + PADDING.top + (klineHeight - PADDING.top - PADDING.bottom) * (1 - i / 4)
      const price = minPrice + priceStep * i
      ctx.fillText(price.toFixed(2), klineDataStart - 5, y)
    }

    const getY = (price: number): number => {
      const range = maxPrice - minPrice
      return klineTop + PADDING.top + (klineHeight - PADDING.top - PADDING.bottom) * (1 - (price - minPrice) / range)
    }

    visibleData.forEach((d, i) => {
      const x = klineDataStart + i * candleWidth + candleWidth / 2
      const open = Number(d.open)
      const close = Number(d.close)
      const high = Number(d.high)
      const low = Number(d.low)
      const isUp = close >= open
      const color = isUp ? RED : GREEN

      const highY = getY(high)
      const lowY = getY(low)
      const openY = getY(open)
      const closeY = getY(close)

      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x, highY)
      ctx.lineTo(x, lowY)
      ctx.stroke()

      ctx.fillStyle = color
      const top = Math.min(openY, closeY)
      const bottom = Math.max(openY, closeY)
      const w = barWidth
      ctx.fillRect(x - w / 2, top, w, Math.max(bottom - top, 1))
    })

    ctx.lineWidth = 1.5
    MA_PERIODS.forEach(p => {
      const maData = visibleMas[p]
      const color = MA_COLORS[p]
      ctx.strokeStyle = color
      ctx.beginPath()
      let hasStarted = false
      maData.forEach((v, i) => {
        if (v === null) return
        const x = klineDataStart + i * candleWidth + candleWidth / 2
        const y = getY(v)
        if (!hasStarted) {
          ctx.moveTo(x, y)
          hasStarted = true
        } else {
          ctx.lineTo(x, y)
        }
      })
      ctx.stroke()
    })

    const xLabelStep = Math.max(1, Math.floor(visibleData.length / 6))
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.font = '10px Arial'
    ctx.fillStyle = TEXT_COLOR
    for (let i = 0; i < visibleData.length; i += xLabelStep) {
      const x = klineDataStart + i * candleWidth + candleWidth / 2
      const dateStr = formatDate(visibleData[i].trade_date)
      ctx.fillText(dateStr, x, klineTop + klineHeight - PADDING.bottom + 5)
    }

    ctx.fillStyle = '#FFFFFF'
    ctx.fillRect(0, volumeTop, width, volumeHeight)

    ctx.strokeStyle = GRID_COLOR
    ctx.lineWidth = 0.5
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(klineDataStart, volumeTop)
    ctx.lineTo(klineDataEnd, volumeTop)
    ctx.stroke()

    ctx.setLineDash([])
    let maxVolume = 0
    visibleData.forEach(d => {
      maxVolume = Math.max(maxVolume, Number(d.volume))
    })
    const volumeRange = maxVolume || 1

    visibleData.forEach((d, i) => {
      const x = klineDataStart + i * candleWidth + candleWidth / 2
      const open = Number(d.open)
      const close = Number(d.close)
      const isUp = close >= open
      const color = isUp ? RED : GREEN
      const vol = Number(d.volume)
      const volH = (vol / volumeRange) * (volumeHeight - PADDING.top - PADDING.bottom)
      ctx.fillStyle = color
      ctx.fillRect(x - barWidth / 2, volumeTop + volumeHeight - PADDING.bottom - volH, barWidth, volH)
    })

    ctx.textAlign = 'right'
    ctx.textBaseline = 'bottom'
    ctx.font = '10px Arial'
    ctx.fillStyle = TEXT_COLOR
    const volLabel = maxVolume >= 100000000 ? `${(maxVolume / 100000000).toFixed(1)}亿` :
      maxVolume >= 10000 ? `${(maxVolume / 10000).toFixed(1)}万` : maxVolume.toFixed(0)
    ctx.fillText(volLabel, klineDataStart - 5, volumeTop + volumeHeight - PADDING.bottom)

  }, [preparedData, height, stockCode, stockName])

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const visibleCount = state.current.endIndex - state.current.startIndex
    const center = state.current.startIndex + visibleCount / 2
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9
    let newCount = Math.floor(visibleCount * zoomFactor)
    newCount = Math.max(30, Math.min(preparedData.reversed.length, newCount))

    let newStart = Math.floor(center - newCount / 2)
    let newEnd = newStart + newCount

    if (newStart < 0) {
      newStart = 0
      newEnd = newCount
    }
    if (newEnd > preparedData.reversed.length) {
      newEnd = preparedData.reversed.length
      newStart = newEnd - newCount
      if (newStart < 0) newStart = 0
    }

    state.current.startIndex = newStart
    state.current.endIndex = newEnd
    render()
  }, [preparedData, render])

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    state.current.isDragging = true
    state.current.dragStartX = e.clientX
    state.current.dragStartIndex = state.current.startIndex
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!state.current.isDragging) return
    const deltaX = e.clientX - state.current.dragStartX
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const width = rect.width
    const visibleCount = state.current.endIndex - state.current.startIndex
    const candlesPerPixel = visibleCount / (width - PADDING.left - PADDING.right)
    const indexDelta = Math.round(deltaX * candlesPerPixel)
    
    let newStart = state.current.dragStartIndex - indexDelta
    let newEnd = newStart + visibleCount

    if (newStart < 0) {
      newStart = 0
      newEnd = newStart + visibleCount
    }
    if (newEnd > preparedData.reversed.length) {
      newEnd = preparedData.reversed.length
      newStart = newEnd - visibleCount
      if (newStart < 0) newStart = 0
    }

    state.current.startIndex = newStart
    state.current.endIndex = newEnd
    render()
  }, [preparedData, render])

  const handleMouseUp = useCallback(() => {
    state.current.isDragging = false
  }, [])

  const handleMouseLeave = useCallback(() => {
    state.current.isDragging = false
  }, [])

  useEffect(() => {
    if (preparedData.reversed.length > 0) {
      state.current.startIndex = Math.max(0, preparedData.reversed.length - 120)
      state.current.endIndex = preparedData.reversed.length
    }
    render()
  }, [preparedData, render])

  useEffect(() => {
    const handleResize = () => render()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [render])

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden"
      style={{ backgroundColor: '#FFFFFF' }}
    >
      <div
        ref={containerRef}
        className="flex-1 relative"
      >
        <canvas
          ref={canvasRef}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          style={{ display: 'block', cursor: state.current.isDragging ? 'grabbing' : 'grab' }}
        />
        
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 border-4 border-t-transparent border-gray-300 rounded-full animate-spin mb-2" />
              <span className="text-sm text-gray-500">加载中…</span>
            </div>
          </div>
        )}
        
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center text-center p-4">
              <div className="text-2xl mb-2" style={{ color: GREEN }}>⚠️</div>
              <span className="font-medium" style={{ color: GREEN }}>加载失败</span>
              <span className="text-sm mt-1" style={{ color: TEXT_COLOR }}>{error}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
