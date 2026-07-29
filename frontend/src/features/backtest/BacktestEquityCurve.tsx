// BacktestEquityCurve.tsx — 资金曲线图（双Y轴：左轴净值金额，右轴收益率%）

import React, { useRef, useEffect, useMemo } from 'react';
import { Empty } from 'antd';
import type { EquityPoint } from './backtestTypes';

interface EquityCurveProps {
  equityCurve: EquityPoint[];
  initialCapital: number;
  /** 宽度，默认 100% */
  width?: number;
  height?: number;
}

const BacktestEquityCurve: React.FC<EquityCurveProps> = ({
  equityCurve,
  initialCapital,
  width,
  height = 300,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const data = useMemo(() => {
    return equityCurve.map((p) => ({
      time: p.time,
      equity: p.equity,
      returnPct: ((p.equity - initialCapital) / initialCapital) * 100,
    }));
  }, [equityCurve, initialCapital]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length === 0) return;

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
    const padding = { top: 20, right: 60, bottom: 40, left: 60 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    // 清空
    ctx.clearRect(0, 0, w, h);

    // 计算范围
    const minEquity = Math.min(...data.map((d) => d.equity));
    const maxEquity = Math.max(...data.map((d) => d.equity));
    const minPct = (minEquity - initialCapital) / initialCapital * 100;
    const maxPct = (maxEquity - initialCapital) / initialCapital * 100;
    const pctRange = maxPct - minPct || 1;

    const scaleX = (i: number) => padding.left + (i / (data.length - 1 || 1)) * plotW;
    const scaleY = (val: number) => padding.top + (1 - (val - minEquity) / (maxEquity - minEquity || 1)) * plotH;
    const scaleYPct = (pct: number) => padding.top + (1 - (pct - minPct) / pctRange) * plotH;

    // 绘制网格
    ctx.strokeStyle = '#f0f0f0';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (i / 4) * plotH;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();
    }

    // 基线
    const baselineY = scaleY(initialCapital);
    ctx.strokeStyle = '#d9d9d9';
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(padding.left, baselineY);
    ctx.lineTo(w - padding.right, baselineY);
    ctx.stroke();
    ctx.setLineDash([]);

    // 净值曲线
    ctx.strokeStyle = '#1677ff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const x = scaleX(i);
      const y = scaleY(data[i].equity);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 净值填充
    ctx.fillStyle = 'rgba(22, 119, 255, 0.06)';
    ctx.lineTo(scaleX(data.length - 1), baselineY);
    ctx.lineTo(scaleX(0), baselineY);
    ctx.closePath();
    ctx.fill();

    // Y轴标签（左轴：净值）
    ctx.fillStyle = '#333';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
      const val = minEquity + (i / 4) * (maxEquity - minEquity);
      const y = scaleY(val);
      ctx.fillText((val / 10000).toFixed(1) + '万', padding.left - 8, y + 4);
    }

    // Y轴标签（右轴：收益率）
    ctx.textAlign = 'left';
    for (let i = 0; i <= 4; i++) {
      const pct = minPct + (i / 4) * pctRange;
      const y = scaleYPct(pct);
      ctx.fillText(pct.toFixed(1) + '%', w - padding.right + 8, y + 4);
    }

    // X轴标签（部分日期）
    ctx.textAlign = 'center';
    const labelCount = Math.min(6, data.length);
    for (let i = 0; i < labelCount; i++) {
      const idx = Math.floor((i / (labelCount - 1 || 1)) * (data.length - 1));
      const x = scaleX(idx);
      ctx.fillText(data[idx].time.slice(5), x, h - padding.bottom + 18);
    }
  }, [data, height, initialCapital]);

  if (equityCurve.length === 0) {
    return <Empty description="暂无净值数据" />;
  }

  return (
    <canvas
      ref={canvasRef}
      style={{ width: width || '100%', height }}
    />
  );
};

export default BacktestEquityCurve;