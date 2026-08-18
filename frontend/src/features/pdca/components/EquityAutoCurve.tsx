/**
 * EquityAutoCurve.tsx — 资金曲线页（基于股票买卖自动计算）
 *
 * 净值 = 初始本金 + 累计已实现盈亏 + 未平仓浮盈
 * - 数据完全由后端 /snapshots/curve-auto 根据交易记录自动计算
 * - 本页仅负责展示波动情况，不含手动录入
 */

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { App, Spin, Empty, Row, Col, Card, Statistic, Button, Segmented } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { createChart, ColorType, CrosshairMode, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts';
import { CHART_THEME } from '@/lib/indicators/chart-config';
import type { EquityCurveAutoPoint } from '../types';
import { fetchEquityAutoCurve } from '../services/snapshot';

// ── 时间段筛选选项 ──
type RangeKey = '1m' | '3m' | '6m' | '1y';

const RANGE_OPTIONS: { label: string; value: RangeKey; months: number }[] = [
  { label: '1个月', value: '1m', months: 1 },
  { label: '3个月', value: '3m', months: 3 },
  { label: '6个月', value: '6m', months: 6 },
  { label: '1年', value: '1y', months: 12 },
];

// ── 净值曲线（lightweight-charts AreaSeries，复用 K 线暗色主题） ──
interface AutoCurveChartProps {
  data: EquityCurveAutoPoint[]; // 已按时间段过滤后的净值点
  startDate: string; // 时间轴起点（真实日期）
  endDate: string; // 时间轴终点（真实日期）
}

const EQUITY_AREA_COLOR = '#1677ff';

const AutoCurveChart: React.FC<AutoCurveChartProps> = ({ data, startDate, endDate }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    // 清理旧图表
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) {}
      chartRef.current = null;
    }
    seriesRef.current = null;

    const chart = createChart(containerRef.current, {
      height: containerRef.current.clientHeight || 300,
      layout: {
        background: { type: ColorType.Solid, color: CHART_THEME.bg },
        textColor: CHART_THEME.text,
        fontSize: 12,
      },
      grid: {
        vertLines: { color: CHART_THEME.grid },
        horzLines: { color: CHART_THEME.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: CHART_THEME.crosshair, style: 2 as never, labelBackgroundColor: '#363A45' },
        horzLine: { color: CHART_THEME.crosshair, style: 2 as never, labelBackgroundColor: '#363A45' },
      },
      rightPriceScale: {
        borderColor: CHART_THEME.border,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor: CHART_THEME.border,
        timeVisible: false,
        rightOffset: 2,
        tickMarkFormatter: (t: Time) => {
          const str = String(t);
          const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(str);
          return m ? `${m[1]}/${m[2]}` : str;
        },
      },
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    const series = chart.addAreaSeries({
      lineColor: EQUITY_AREA_COLOR,
      topColor: 'rgba(22,119,255,0.28)',
      bottomColor: 'rgba(22,119,255,0.02)',
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      priceFormat: {
        type: 'price',
        precision: 2,
        minMove: 0.01,
      },
    });
    seriesRef.current = series;

    // 设置数据（time 用日期字符串 YYYY-MM-DD）
    series.setData(
      data.map((p) => ({
        time: p.date as Time,
        value: p.equity,
      }))
    );

    // 时间轴范围固定显示 [startDate, endDate]
    try {
      chart.timeScale().setVisibleRange({ from: startDate as Time, to: endDate as Time });
    } catch (_) {}

    // 自适应尺寸
    const chartContainer = containerRef.current;
    const resizeObserver = new ResizeObserver(() => {
      if (chartRef.current && chartContainer) {
        const { clientWidth, clientHeight } = chartContainer;
        if (clientWidth > 0 && clientHeight > 0) {
          chartRef.current.resize(clientWidth, clientHeight);
        }
      }
    });
    resizeObserver.observe(chartContainer);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) {}
        chartRef.current = null;
      }
      seriesRef.current = null;
    };
  }, [data, startDate, endDate]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
};

const EquityAutoCurve: React.FC = () => {
  const { message } = App.useApp();
  const [data, setData] = useState<EquityCurveAutoPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<RangeKey>('1m');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchEquityAutoCurve();
      setData(items);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载资金曲线失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => { loadData(); }, [loadData]);

  // 时间轴范围：以今天为终点，往前推对应月份
  const startDate = useMemo(() => {
    const opt = RANGE_OPTIONS.find((o) => o.value === range)!;
    return dayjs().subtract(opt.months, 'month').format('YYYY-MM-DD');
  }, [range]);
  const endDate = dayjs().format('YYYY-MM-DD');

  // 按时间段（今天往前推）过滤曲线数据
  const filtered = useMemo(() => {
    if (data.length === 0) return data;
    const startMs = dayjs(startDate).valueOf();
    const endMs = dayjs(endDate).endOf('day').valueOf();
    const result = data.filter((p) => {
      const t = dayjs(p.date).valueOf();
      return t >= startMs && t <= endMs;
    });
    // 不足 1 个点无法绘制，回退展示全量数据
    return result.length >= 1 ? result : data;
  }, [data, startDate, endDate]);

  const latest = data.length > 0 ? data[data.length - 1] : null;
  const initial = latest ? latest.equity - latest.realized - latest.unrealized : 0;

  return (
    <div className="h-full flex flex-col p-4 gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 flex-shrink-0">
        <span className="text-text-secondary text-sm">基于股票买卖自动计算：净值 = 初始本金 + 累计已实现盈亏 + 未平仓浮盈</span>
        <div className="flex items-center gap-2">
          <Segmented
            options={RANGE_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
            value={range}
            onChange={(v) => setRange(v as RangeKey)}
            size="small"
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Spin /></div>
      ) : data.length === 0 ? (
        <div className="flex justify-center py-20 bg-bg-panel rounded"><Empty description="暂无交易记录，无法生成资金曲线" /></div>
      ) : (
        <>
          <Row gutter={12}>
            <Col span={6}><Card size="small"><Statistic title="初始本金" value={initial} precision={2} prefix="¥" /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="最新净值" value={latest!.equity} precision={2} prefix="¥" /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="累计已实现盈亏" value={latest!.realized} precision={2} prefix="¥" valueStyle={{ color: latest!.realized >= 0 ? '#52c41a' : '#ff4d4f' }} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="未平仓浮盈" value={latest!.unrealized} precision={2} prefix="¥" valueStyle={{ color: latest!.unrealized >= 0 ? '#52c41a' : '#ff4d4f' }} /></Card></Col>
          </Row>
          <div className="h-[340px] flex-shrink-0 bg-bg-panel rounded p-4">
            <AutoCurveChart data={filtered} startDate={startDate} endDate={endDate} />
          </div>
        </>
      )}
    </div>
  );
};

export default EquityAutoCurve;