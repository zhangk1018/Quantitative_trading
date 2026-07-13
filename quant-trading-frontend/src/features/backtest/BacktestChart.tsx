// BacktestChart.tsx — K线图 + 买卖标记（叠加 Canvas 层）

import React, { useRef, useEffect, useMemo } from 'react';
import { Empty } from 'antd';
import type { KlineBar } from '../../lib/indicators/indicators';
import type { Trade } from './backtestTypes';

interface BacktestChartProps {
  bars: KlineBar[];
  trades: Trade[];
  height?: number;
  /** 点击定位到某笔交易的买入日期 */
  focusTrade?: Trade | null;
}

const BacktestChart: React.FC<BacktestChartProps> = ({
  bars,
  trades,
  height = 400,
  focusTrade,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // 构建买卖标记点
  const markers = useMemo(() => {
    const result: { time: string; price: number; color: string; label: string; shape: 'up' | 'down' }[] = [];
    for (const t of trades) {
      if (t.direction === 'buy') {
        result.push({ time: t.entryTime, price: t.entryPrice, color: '#e74c3c', label: 'B', shape: 'up' });
      } else if (t.direction === 'sell' || t.direction === 'close') {
        result.push({ time: t.exitTime, price: t.exitPrice, color: '#27ae60', label: t.isForcedClose ? 'C' : 'S', shape: 'down' });
      }
    }
    return result;
  }, [trades]);

  const focusTime = focusTrade?.entryTime || null;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || bars.length === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = height + 'px';

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = height;
    const padding = { top: 20, right: 40, bottom: 50, left: 55 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    ctx.clearRect(0, 0, w, h);

    const visibleBars = bars.length;
    const barWidth = Math.max(1, Math.min(8, plotW / visibleBars - 1));
    const candleWidth = barWidth * 0.7;

    const maxPrice = Math.max(...bars.map((b) => b.high));
    const minPrice = Math.min(...bars.map((b) => b.low));
    const priceRange = maxPrice - minPrice || 1;

    const scaleX = (i: number) => padding.left + (i / (visibleBars - 1 || 1)) * plotW;
    const scaleY = (price: number) => padding.top + (1 - (price - minPrice) / priceRange) * plotH;

    // 网格
    ctx.strokeStyle = '#f0f0f0';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (i / 4) * plotH;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();
    }

    // 绘制K线
    for (let i = 0; i < visibleBars; i++) {
      const bar = bars[i];
      const x = scaleX(i);
      const isUp = bar.close >= bar.open;
      const color = isUp ? '#e74c3c' : '#27ae60';

      // 影线
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, scaleY(bar.high));
      ctx.lineTo(x, scaleY(bar.low));
      ctx.stroke();

      // 实体
      const y1 = scaleY(bar.open);
      const y2 = scaleY(bar.close);
      const bodyH = Math.max(1, Math.abs(y2 - y1));
      ctx.fillStyle = isUp ? '#e74c3c' : '#27ae60';
      ctx.fillRect(x - candleWidth / 2, Math.min(y1, y2), candleWidth, bodyH);
    }

    // 绘制买卖标记
    for (const marker of markers) {
      const idx = bars.findIndex((b) => b.time === marker.time);
      if (idx < 0) continue;

      const x = scaleX(idx);
      const y = marker.shape === 'up' ? scaleY(marker.price) - 15 : scaleY(marker.price) + 15;

      // 高亮当前聚焦的标记
      const isFocused = focusTime === marker.time;
      const radius = isFocused ? 8 : 6;

      ctx.fillStyle = marker.color;
      ctx.beginPath();
      if (marker.shape === 'up') {
        ctx.moveTo(x, y - radius);
        ctx.lineTo(x - radius, y + radius);
        ctx.lineTo(x + radius, y + radius);
      } else {
        ctx.moveTo(x, y + radius);
        ctx.lineTo(x - radius, y - radius);
        ctx.lineTo(x + radius, y - radius);
      }
      ctx.closePath();
      ctx.fill();

      if (isFocused) {
        ctx.strokeStyle = '#ff9800';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
        ctx.stroke();
      }

      // 标签
      ctx.fillStyle = '#fff';
      ctx.font = `bold ${isFocused ? '10px' : '9px'} sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(marker.label, x, y);
    }

    // Y轴标签
    ctx.fillStyle = '#333';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
      const price = minPrice + (i / 4) * priceRange;
      const y = scaleY(price);
      ctx.fillText(price.toFixed(2), padding.left - 8, y + 4);
    }

    // X轴日期标签
    ctx.textAlign = 'center';
    const labelCount = Math.min(6, visibleBars);
    for (let i = 0; i < labelCount; i++) {
      const idx = Math.floor((i / (labelCount - 1 || 1)) * (visibleBars - 1));
      const x = scaleX(idx);
      ctx.fillText(bars[idx].time.slice(5), x, h - padding.bottom + 18);
    }
  }, [bars, markers, height, focusTime]);

  if (bars.length === 0) {
    return <Empty description="暂无K线数据" />;
  }

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height }}
    />
  );
};

export default BacktestChart;