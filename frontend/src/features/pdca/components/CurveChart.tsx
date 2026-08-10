/**
 * CurveChart.tsx — 资金曲线 SVG 折线图（纯展示组件）
 *
 * 功能：
 * - 接收资金曲线数据，渲染 SVG 折线图
 * - 出入金节点标注（入金绿色三角，出金红色三角）
 * - 调整后净值展示
 */

import React, { useMemo } from 'react';
import type { CapitalCurvePoint } from '../types';

const SVG_WIDTH = 800;
const SVG_HEIGHT = 400;
const PADDING = { top: 30, right: 30, bottom: 40, left: 70 };

interface Props {
  data: CapitalCurvePoint[];
}

const CurveChart: React.FC<Props> = ({ data }) => {
  const chartW = SVG_WIDTH - PADDING.left - PADDING.right;
  const chartH = SVG_HEIGHT - PADDING.top - PADDING.bottom;

  // 派生数据缓存
  const { minVal, valRange, linePath, yLabels, dateLabels } = useMemo(() => {
    if (data.length === 0) {
      return { minVal: 0, valRange: 1, linePath: '', yLabels: [], dateLabels: [] };
    }

    const nv = data.map((p) => p.adjusted_nav ?? p.total_asset);
    const min = Math.min(...nv) * 0.95;
    const max = Math.max(...nv) * 1.05;
    const range = max - min || 1;

    const xScale = (i: number) => PADDING.left + (i / (data.length - 1)) * chartW;
    const yScale = (v: number) => PADDING.top + chartH - ((v - min) / range) * chartH;

    const path = data
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i).toFixed(1)} ${yScale(p.adjusted_nav ?? p.total_asset).toFixed(1)}`)
      .join(' ');

    const ticks = 5;
    const yLabels = Array.from({ length: ticks }, (_, i) => {
      const v = min + (range / (ticks - 1)) * i;
      return { v, y: yScale(v) };
    });

    const step = Math.max(1, Math.floor(data.length / 10));
    const dateLabels = data.map((p, i) => {
      if (i % step !== 0) return null;
      return { x: xScale(i), label: p.date.slice(5) };
    }).filter(Boolean);

    return { minVal: min, valRange: range, linePath: path, yLabels, dateLabels };
  }, [data]);

  if (data.length === 0) return null;

  const xScale = (i: number) => PADDING.left + (i / (data.length - 1)) * chartW;
  const yScale = (v: number) => PADDING.top + chartH - ((v - minVal) / valRange) * chartH;

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} preserveAspectRatio="xMidYMid meet">
      {/* 网格线 */}
      {yLabels.map(({ v, y }) => (
        <g key={v}>
          <line x1={PADDING.left} y1={y} x2={SVG_WIDTH - PADDING.right} y2={y} stroke="#222" strokeWidth={0.5} />
          <text x={PADDING.left - 8} y={y + 4} textAnchor="end" fill="#999" fontSize={11}>
            {v >= 10000 ? `${(v / 10000).toFixed(1)}万` : v.toFixed(0)}
          </text>
        </g>
      ))}

      {/* 折线 */}
      <path d={linePath} fill="none" stroke="#1677ff" strokeWidth={2} />

      {/* 数据点 & 出入金标注 */}
      {data.map((p, i) => {
        const x = xScale(i);
        const y = yScale(p.adjusted_nav ?? p.total_asset);
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={3} fill="#1677ff" />
            {p.deposit > 0 && (
              <>
                <text x={x} y={y - 15} textAnchor="middle" fill="#52c41a" fontSize={10}>
                  +{p.deposit}
                </text>
                <polygon points={`${x},${y - 8} ${x - 5},${y - 3} ${x + 5},${y - 3}`} fill="#52c41a" />
              </>
            )}
            {p.withdrawal > 0 && (
              <>
                <text x={x} y={y - 15} textAnchor="middle" fill="#ff4d4f" fontSize={10}>
                  -{p.withdrawal}
                </text>
                <polygon points={`${x},${y - 3} ${x - 5},${y - 8} ${x + 5},${y - 8}`} fill="#ff4d4f" />
              </>
            )}
          </g>
        );
      })}

      {/* X轴日期标签 */}
      {dateLabels.map((item, i) => {
        if (!item) return null;
        return (
          <text key={i} x={item.x} y={SVG_HEIGHT - 8} textAnchor="middle" fill="#999" fontSize={10}>
            {item.label}
          </text>
        );
      })}
    </svg>
  );
};

export default React.memo(CurveChart);