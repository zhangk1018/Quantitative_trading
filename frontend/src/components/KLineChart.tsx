/**
 * KlineChart.tsx - K线图组件（基于 klinecharts 9.8）
 *
 * Phase 4.3.4 K线图集成
 *
 * 核心设计：
 * - data 变化时 clearData + applyNewData（避免增量错位）
 * - 组件卸载时 dispose（风险点 5：内存泄漏）
 * - 监听容器尺寸变化调用 resize() 自适应
 * - trade_date 字符串 → timestamp 毫秒
 * - 主题色与项目一致：#131722 背景，#26a69a 涨，#ef5350 跌
 *
 * 风险点应对：
 * - 风险点 4（跨周期数据不一致）：周期切换时清空图表，避免日/周线混淆
 * - 风险点 5（频繁切换内存泄漏）：useEffect cleanup 中 dispose
 *
 * 后续任务：
 * - 4.3.5 买卖信号叠加（tradeMarker 覆盖物）通过 props.signals 传入
 */

import { useEffect, useRef } from 'react';
import {
  init,
  dispose,
  LineType,
  type LayoutChild,
  type Chart,
  type KLineData,
} from 'klinecharts';
import type { KLineItem, SignalItem } from '../types';
import {
  ensureTradeMarkerRegistered,
  buildTradeMarkerPoints,
  TRADE_MARKER_NAME,
} from '../utils/tradeMarker';

interface KlineChartProps {
  /** K线数据（按日期从新到旧，DESCENDING） */
  data: KLineItem[];
  /** 买卖信号（可选，4.3.5 集成） */
  signals?: SignalItem[];
  /** 容器高度（默认 400） */
  height?: number;
  /** 周期标签（用于显示） */
  period?: string;
  /** 复权方式（用于显示） */
  adj?: string;
  /** 副图指标（默认 VOL） */
  subIndicator?: 'VOL' | 'MACD' | 'RSI' | 'KDJ';
}

// ============================================
// 工具：trade_date (YYYY-MM-DD) → timestamp (ms)
// ============================================

function toTimestamp(tradeDate: string): number {
  // YYYY-MM-DD → 当天 00:00:00 本地时区对应的 UTC 毫秒
  // klinecharts 会用本地时区解释 timestamp
  const t = Date.parse(tradeDate);
  return Number.isNaN(t) ? Date.now() : t;
}

// ============================================
// 工具：KLineItem[] → klinecharts KLineData[]
// klinecharts 需要按时间从旧到新（ASCENDING）
// 后端返回已经是 ASCENDING（旧→新），不需要反转
// ============================================

function toChartData(items: KLineItem[]): KLineData[] {
  return items.map((it) => ({
    timestamp: toTimestamp(it.trade_date),
    // 后端 Pydantic Decimal 序列化为 string，klinecharts 内部算法（尤其 MACD）要求 number
    // RSI/KDJ 内部有 Number() 兜底所以正常，MACD 直接 NaN（v9.8.12 实测）
    open: Number(it.open),
    high: Number(it.high),
    low: Number(it.low),
    close: Number(it.close),
    volume: it.volume ?? 0,
    turnover: Number(it.amount ?? 0),
  }))
}

// ============================================
// 主题样式：与项目设计语言一致
// ============================================

const klineStyles = {
  grid: {
    show: true,
    horizontal: {
      show: true,
      color: '#1e222d',
      style: LineType.Dashed,
    },
    vertical: {
      show: true,
      color: '#1e222d',
      style: LineType.Dashed,
    },
  },
  candle: {
    bar: {
      upColor: '#26a69a',
      downColor: '#ef5350',
      noChangeColor: '#888888',
      upBorderColor: '#26a69a',
      downBorderColor: '#ef5350',
      noChangeBorderColor: '#888888',
      upWickColor: '#26a69a',
      downWickColor: '#ef5350',
      noChangeWickColor: '#888888',
    },
    priceMark: {
      last: {
        line: {
          show: true,
          color: '#888888',
          dashedValue: [4, 4],
        },
        text: {
          show: true,
          color: '#eaecef',
          backgroundColor: '#26a69a',
          size: 11,
        },
      },
      high: {
        color: '#26a69a',
        textSize: 11,
      },
      low: {
        color: '#ef5350',
        textSize: 11,
      },
    },
    tooltip: {
      // 格式：TooltipLegend[] = { title: string, value: string }[]
      // 注意 klinecharts 用 {time} 占位日期，不是 {date}
      custom: [
        { title: '时间', value: '{time}' },
        { title: '开盘', value: '{open}' },
        { title: '收盘', value: '{close}' },
        { title: '最高', value: '{high}' },
        { title: '最低', value: '{low}' },
        { title: '成交量', value: '{volume}' },
        { title: '成交额', value: '{turnover}' },
        { title: '涨跌幅', value: '{change}' },
      ],
    },
  },
  indicator: {
    tooltip: {
      showName: true,
      showParams: true,
    },
  },
  xAxis: {
    axisLine: { color: '#2a2e39' },
    tickText: { color: '#8a8e99', size: 10 },
    tickLine: { color: '#2a2e39' },
  },
  yAxis: {
    axisLine: { color: '#2a2e39' },
    tickText: { color: '#8a8e99', size: 10 },
    tickLine: { color: '#2a2e39' },
  },
};

// ============================================
// 主组件
// ============================================

export default function KlineChart({
  data,
  signals,
  height = 400,
  period = 'daily',
  adj = 'forward',
  subIndicator = 'VOL',
}: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  // ========== 初始化图表（仅一次） ==========
  useEffect(() => {
    if (!containerRef.current) return;

    // 注册自定义覆盖物（仅一次）
    ensureTradeMarkerRegistered();

    // 副图固定 paneId，方便切换时精准删除
    const SUB_PANE_ID = 'sub_pane';

    const chart = init(containerRef.current, {
      styles: klineStyles,
      // 使用 layout 明确指定布局：主图 + 1 个副图
      // 注意：MA 是主图指标，不放副图 content
      // 字符串字面量通过 as LayoutChild 类型断言（klinecharts 9.8 const enum + isolatedModules 限制）
      layout: [
        { type: 'candle' } as LayoutChild, // 主图（K线 + MA）
        {
          type: 'indicator',
          content: [subIndicator], // 副图：当前选中的副图指标
          options: { id: SUB_PANE_ID, height: 100, minHeight: 60 },
        } as LayoutChild,
      ],
    });
    if (!chart) {
      console.error('[KlineChart] klinecharts init failed');
      return;
    }
    chartRef.current = chart;

    // 创建主图 MA 指标（叠加在 candle pane）
    chart.createIndicator('MA', false, { id: 'candle_pane' });

    // 监听容器尺寸变化（Modal 弹出/窗口缩放/侧边栏切换）
    const observer = new ResizeObserver(() => {
      chart.resize();
    });
    observer.observe(containerRef.current);
    resizeObserverRef.current = observer;

    return () => {
      // 风险点 5：必须 dispose 防止内存泄漏
      observer.disconnect();
      resizeObserverRef.current = null;
      if (chartRef.current) {
        dispose(chartRef.current);
        chartRef.current = null;
      }
    };
  }, []);

  // ========== 副图指标切换（4.3.6） ==========
  // 跟踪当前副图指标名，避免重复操作
  // 初始化为初始 subIndicator，首次 useEffect 直接跳过（init layout 已建好 sub_pane）
  const currentSubIndicatorRef = useRef<string | null>(subIndicator);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (!subIndicator) return;

    const SUB_PANE_ID = 'sub_pane';

    // 首次加载由 init layout 创建了 sub_pane + subIndicator，
    // 跳过重复创建（避免销毁-重建导致渲染异常）
    if (currentSubIndicatorRef.current === subIndicator) {
      return;
    }
    currentSubIndicatorRef.current = subIndicator;

    // 1. 删除副图上所有已有指标（klinecharts 内部：空 pane 会被销毁）
    try {
      const paneIndicators = chart.getIndicatorByPaneId(SUB_PANE_ID) as
        | Map<string, unknown>
        | null;
      if (paneIndicators && paneIndicators.size > 0) {
        paneIndicators.forEach((_ind, name) => {
          chart.removeIndicator(SUB_PANE_ID, name);
        });
      }
    } catch (e) {
      console.debug(`[KlineChart] removeIndicator on ${SUB_PANE_ID} failed:`, e);
    }

    // 2. 等下一帧再创建新指标，确保 chart 已完成 removeIndicator 的 adjustPaneViewport
    requestAnimationFrame(() => {
      const chart2 = chartRef.current;
      if (!chart2) return;
      try {
        const result = chart2.createIndicator(
          subIndicator,
          false,
          { id: SUB_PANE_ID, height: 100, minHeight: 60 }
        );
        if (!result) {
          console.warn(
            `[KlineChart] createIndicator ${subIndicator} on ${SUB_PANE_ID} returned null`
          );
        } else {
          console.info(
            `[KlineChart] switched sub-pane to ${subIndicator} (id=${result})`
          );
        }
      } catch (e) {
        console.error(`[KlineChart] createIndicator ${subIndicator} failed:`, e);
      }
    });
  }, [subIndicator]);

  // ========== 数据更新 ==========
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (!data || data.length === 0) {
      chart.clearData();
      // 清理所有 tradeMarker
      chart.removeOverlay({ name: TRADE_MARKER_NAME });
      return;
    }

    const chartData = toChartData(data);
    chart.applyNewData(chartData);
    chart.scrollToRealTime();

    // ========== 叠加买卖信号（4.3.5） ==========
    // 风险点 3：数据层去重（buildTradeMarkerPoints 内部已做）
    // 风险点 2：使用同一套复权（K线数据 + 信号价格均来自后端 adj_factor）
    if (signals && signals.length > 0) {
      const points = buildTradeMarkerPoints(signals, data);
      if (points.length > 0) {
        // 清理旧 marker，避免叠加
        chart.removeOverlay({ name: TRADE_MARKER_NAME });
        // 为每个 point 创建一个覆盖物（klinecharts 不支持单个 overlay 多 point 动态绘制）
        for (const pt of points) {
          chart.createOverlay(
            {
              name: TRADE_MARKER_NAME,
              lock: true, // 防止拖拽误操作（项目硬约束）
              needDefaultPointFigure: false,
              points: [pt],
              extendData: pt.extendData as unknown as Record<string, unknown>,
            },
            'candle_pane'
          );
        }
      } else {
        chart.removeOverlay({ name: TRADE_MARKER_NAME });
      }
    } else {
      chart.removeOverlay({ name: TRADE_MARKER_NAME });
    }
  }, [data, signals]);

  return (
    <div
      ref={containerRef}
      style={{ height: `${height}px`, width: '100%' }}
      data-testid="kline-chart"
      data-period={period}
      data-adj={adj}
    />
  );
}
