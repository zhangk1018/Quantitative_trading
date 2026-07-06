// KLineChart.tsx
// 展示组件 — 接收 chartData、配置和 markers，负责 lightweight-charts 实例的创建/更新/销毁
// 包含：十字光标浮窗、时间轴格式化、指标图例

import React, { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  LineWidth,
  TickMarkType,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type CandlestickSeriesOptions,
  type LineSeriesOptions,
  type HistogramSeriesOptions,
  type DeepPartial,
  type Time,
  type MouseEventParams,
} from 'lightweight-charts';
import { makeHorizontalLine, type ChartDataResult, type RawBarDetail } from '@/lib/indicators/chart-adapter';
import {
  CHART_THEME,
  MA_COLORS,
  BOLL_COLORS,
  MACD_COLORS,
  RSI_COLORS,
  KDJ_COLORS,
  CANDLE_COLORS,
  PANE_RATIOS,
  REF_LINES,
} from '@/lib/indicators/chart-config';
import type { ConditionEvent } from '@/lib/indicators/condition-detector';
import { sanitizeNumber, sanitizePct } from '@/lib/indicators/indicators';

// ---- 类型 ----

export type MainType = 'ma' | 'boll';
export type OscType = 'rsi' | 'kdj';

interface CrosshairInfo {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  pe_ttm: number | null;
  turnover_rate: number | null;
  preClose: number | null;
  // 副图指标（十字光标位置的值）
  dif: number | null;
  dea: number | null;
  macdHist: number | null;
  rsi6: number | null;
  rsi12: number | null;
  rsi24: number | null;
  kdjK: number | null;
  kdjD: number | null;
  kdjJ: number | null;
}

interface KLineChartProps {
  chartData: ChartDataResult | null;
  mainType: MainType;
  oscType: OscType;
  markers?: ConditionEvent[];
}

// ---- Series 引用类型 ----

interface SeriesRefs {
  candle: ISeriesApi<'Candlestick'>;
  ma5: ISeriesApi<'Line'>;
  ma10: ISeriesApi<'Line'>;
  ma20: ISeriesApi<'Line'>;
  ma60: ISeriesApi<'Line'>;
  bollUpper: ISeriesApi<'Line'>;
  bollMid: ISeriesApi<'Line'>;
  bollLower: ISeriesApi<'Line'>;
  volume: ISeriesApi<'Histogram'>;
  dif: ISeriesApi<'Line'>;
  dea: ISeriesApi<'Line'>;
  macdHist: ISeriesApi<'Histogram'>;
  rsi6: ISeriesApi<'Line'>;
  rsi12: ISeriesApi<'Line'>;
  rsi24: ISeriesApi<'Line'>;
  rsi30: ISeriesApi<'Line'>;
  rsi70: ISeriesApi<'Line'>;
  kdjK: ISeriesApi<'Line'>;
  kdjD: ISeriesApi<'Line'>;
  kdjJ: ISeriesApi<'Line'>;
  kdj20: ISeriesApi<'Line'>;
  kdj80: ISeriesApi<'Line'>;
}

// ---- 工具函数 ----

function formatVolume(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(3)}亿手`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(3)}万手`;
  return `${v.toFixed(0)}手`;
}

function formatAmount(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(3)}亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(3)}万`;
  return `${v.toFixed(2)}`;
}

function getWeekday(dateStr: string): string {
  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const d = new Date(dateStr + 'T00:00:00');
  return days[d.getDay()] || '';
}

function formatTimeAxis(time: Time, tickMarkType: TickMarkType): string {
  const t = String(time);
  const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(t);
  if (!m) return t;
  const year = m[1];
  const month = m[2];
  switch (tickMarkType) {
    case TickMarkType.Year:
      return year;
    case TickMarkType.Month:
      return `${year}/${month}`;
    case TickMarkType.DayOfMonth:
      return month;
    default:
      return `${year}/${month}`;
  }
}

function mkLineSeriesOptions(opts: {
  color: string; priceScaleId: string;
  lineWidth?: LineWidth; lineStyle?: LineStyle;
  lastValueVisible?: boolean; priceLineVisible?: boolean;
  title?: string; visible?: boolean;
}): DeepPartial<LineSeriesOptions> {
  return {
    color: opts.color,
    priceScaleId: opts.priceScaleId,
    lineWidth: (opts.lineWidth ?? 1) as LineWidth,
    lineStyle: opts.lineStyle ?? LineStyle.Solid,
    lastValueVisible: opts.lastValueVisible ?? false,
    priceLineVisible: opts.priceLineVisible ?? false,
    title: opts.title,
    visible: opts.visible ?? true,
  };
}

function mkHistSeriesOptions(opts: {
  priceScaleId: string;
  priceFormat?: HistogramSeriesOptions['priceFormat'];
}): DeepPartial<HistogramSeriesOptions> {
  return {
    priceScaleId: opts.priceScaleId,
    color: 'rgba(0,212,170,0.6)',
    priceFormat: opts.priceFormat,
    priceLineVisible: false,
    lastValueVisible: false,
  };
}

// ---- 十字光标浮窗组件 ----

const CrosshairOverlay: React.FC<{ info: CrosshairInfo | null; oscType: OscType; side: 'left' | 'right' }> = ({ info, oscType, side }) => {
  if (!info) return null;

  const { open, high, low, close, preClose } = info;
  const change = preClose != null ? close - preClose : 0;
  const changePct = preClose != null && preClose > 0 ? (change / preClose) * 100 : 0;
  const isUp = change >= 0;
  const changeColor = isUp ? CANDLE_COLORS.up : CANDLE_COLORS.down;

  const isRsi = oscType === 'rsi';

  const rows: { label: string; value: string; color?: string }[] = [
    { label: '开盘', value: sanitizeNumber(open) },
    { label: '最高', value: sanitizeNumber(high), color: CANDLE_COLORS.up },
    { label: '最低', value: sanitizeNumber(low), color: CANDLE_COLORS.down },
    { label: '收盘', value: sanitizeNumber(close), color: changeColor },
    { label: '涨跌额', value: `${isUp ? '+' : ''}${change.toFixed(2)}`, color: changeColor },
    { label: '涨跌幅', value: sanitizePct(changePct), color: changeColor },
    { label: '成交量', value: formatVolume(info.volume) },
    { label: '成交额', value: formatAmount(info.amount) },
    { label: '换手率', value: info.turnover_rate != null ? `${info.turnover_rate.toFixed(2)}%` : '--' },
    { label: '市盈率', value: info.pe_ttm != null ? info.pe_ttm.toFixed(2) : '--' },
  ];

  const posStyle: React.CSSProperties = side === 'left'
    ? { top: 8, left: 65 }
    : { top: 8, right: 8 };

  return (
    <div
      className="absolute z-10 px-3 py-2 rounded pointer-events-none select-none"
      style={{
        ...posStyle,
        background: 'rgba(20, 26, 37, 0.92)',
        border: `1px solid ${CHART_THEME.border}`,
        color: CHART_THEME.text,
        fontSize: 12,
        lineHeight: '20px',
        minWidth: 180,
      }}
    >
      <div className="text-base font-bold mb-1" style={{ color: CHART_THEME.text }}>
        {info.time.replace(/-/g, '/')} {getWeekday(info.time)}
      </div>
      {rows.map((row) => (
        <div key={row.label} className="flex justify-between gap-4">
          <span style={{ color: '#848E9C' }}>{row.label}</span>
          <span style={{ color: row.color || CHART_THEME.text, fontWeight: row.color ? 600 : 400 }}>
            {row.value}
          </span>
        </div>
      ))}

      {/* MACD 参数 */}
      <div className="border-t mt-2 pt-1" style={{ borderColor: CHART_THEME.border }}>
        <div className="text-xs mb-1" style={{ color: '#848E9C' }}>MACD</div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          <span style={{ color: MACD_COLORS.dif, fontWeight: 600 }}>
            DIF {info.dif != null ? info.dif.toFixed(2) : '--'}
          </span>
          <span style={{ color: MACD_COLORS.dea, fontWeight: 600 }}>
            DEA {info.dea != null ? info.dea.toFixed(2) : '--'}
          </span>
          <span style={{
            color: info.macdHist != null ? (info.macdHist >= 0 ? CANDLE_COLORS.up : CANDLE_COLORS.down) : '#848E9C',
            fontWeight: 600,
          }}>
            Hist {info.macdHist != null ? info.macdHist.toFixed(2) : '--'}
          </span>
        </div>
      </div>

      {/* RSI / KDJ 参数 */}
      <div className="mt-1">
        <div className="text-xs mb-1" style={{ color: '#848E9C' }}>{isRsi ? 'RSI' : 'KDJ'}</div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {isRsi ? (
            <>
              <span style={{ color: RSI_COLORS.rsi6, fontWeight: 600 }}>
                RSI6 {info.rsi6 != null ? info.rsi6.toFixed(2) : '--'}
              </span>
              <span style={{ color: RSI_COLORS.rsi12, fontWeight: 600 }}>
                RSI12 {info.rsi12 != null ? info.rsi12.toFixed(2) : '--'}
              </span>
              <span style={{ color: RSI_COLORS.rsi24, fontWeight: 600 }}>
                RSI24 {info.rsi24 != null ? info.rsi24.toFixed(2) : '--'}
              </span>
            </>
          ) : (
            <>
              <span style={{ color: KDJ_COLORS.k, fontWeight: 600 }}>
                K {info.kdjK != null ? info.kdjK.toFixed(2) : '--'}
              </span>
              <span style={{ color: KDJ_COLORS.d, fontWeight: 600 }}>
                D {info.kdjD != null ? info.kdjD.toFixed(2) : '--'}
              </span>
              <span style={{ color: KDJ_COLORS.j, fontWeight: 600 }}>
                J {info.kdjJ != null ? info.kdjJ.toFixed(2) : '--'}
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// ---- 组件 ----

const KLineChart: React.FC<KLineChartProps> = ({ chartData, mainType, oscType, markers }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<SeriesRefs | null>(null);
  const rawBarsRef = useRef<RawBarDetail[]>([]);
  const indicatorDataRef = useRef<{
    dif: { time: string; value: number }[];
    dea: { time: string; value: number }[];
    macdHist: { time: string; value: number }[];
    rsi6: { time: string; value: number }[];
    rsi12: { time: string; value: number }[];
    rsi24: { time: string; value: number }[];
    kdjK: { time: string; value: number }[];
    kdjD: { time: string; value: number }[];
    kdjJ: { time: string; value: number }[];
  }>({ dif: [], dea: [], macdHist: [], rsi6: [], rsi12: [], rsi24: [], kdjK: [], kdjD: [], kdjJ: [] });
  const [crosshair, setCrosshair] = useState<CrosshairInfo | null>(null);
  const [overlaySide, setOverlaySide] = useState<'left' | 'right'>('left');

  // 创建/重建图表
  useEffect(() => {
    if (!chartData || !containerRef.current) return;

    if (seriesRef.current) seriesRef.current = null;
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) {}
      chartRef.current = null;
    }

    rawBarsRef.current = chartData.rawBars;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_THEME.bg },
        textColor: CHART_THEME.text,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: CHART_THEME.grid },
        horzLines: { color: CHART_THEME.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: CHART_THEME.crosshair, style: LineStyle.Dashed, labelBackgroundColor: '#363A45' },
        horzLine: { color: CHART_THEME.crosshair, style: LineStyle.Dashed, labelBackgroundColor: '#363A45' },
      },
      rightPriceScale: { visible: false },
      leftPriceScale: {
        visible: true, minimumWidth: 60, entireTextOnly: true, borderColor: CHART_THEME.border,
      },
      timeScale: {
        timeVisible: false,
        secondsVisible: false,
        borderColor: CHART_THEME.border,
        rightOffset: 5,
        tickMarkFormatter: formatTimeAxis,
      },
      autoSize: true,
      handleScroll: true,
      handleScale: true,
    });

    chartRef.current = chart;

    // 创建所有 series
    const candle = chart.addCandlestickSeries({
      priceScaleId: 'left',
      upColor: CANDLE_COLORS.up, downColor: CANDLE_COLORS.down,
      borderUpColor: CANDLE_COLORS.up, borderDownColor: CANDLE_COLORS.down,
      wickUpColor: CANDLE_COLORS.up, wickDownColor: CANDLE_COLORS.down,
    } as DeepPartial<CandlestickSeriesOptions>);

    const ma5 = chart.addLineSeries(mkLineSeriesOptions({ color: MA_COLORS.ma5, priceScaleId: 'left', title: 'MA5' }));
    const ma10 = chart.addLineSeries(mkLineSeriesOptions({ color: MA_COLORS.ma10, priceScaleId: 'left', title: 'MA10' }));
    const ma20 = chart.addLineSeries(mkLineSeriesOptions({ color: MA_COLORS.ma20, priceScaleId: 'left', title: 'MA20' }));
    const ma60 = chart.addLineSeries(mkLineSeriesOptions({ color: MA_COLORS.ma60, priceScaleId: 'left', title: 'MA60' }));
    const bollUpper = chart.addLineSeries(mkLineSeriesOptions({
      color: BOLL_COLORS.upper, priceScaleId: 'left', lineStyle: LineStyle.Dashed, title: 'BOLL_U',
    }));
    const bollMid = chart.addLineSeries(mkLineSeriesOptions({
      color: BOLL_COLORS.mid, priceScaleId: 'left', title: 'BOLL',
    }));
    const bollLower = chart.addLineSeries(mkLineSeriesOptions({
      color: BOLL_COLORS.lower, priceScaleId: 'left', lineStyle: LineStyle.Dashed, title: 'BOLL_L',
    }));

    const volume = chart.addHistogramSeries(mkHistSeriesOptions({
      priceScaleId: 'volume',
      priceFormat: { type: 'volume', precision: 0, minMove: 1 },
    }));

    const dif = chart.addLineSeries(mkLineSeriesOptions({ color: MACD_COLORS.dif, priceScaleId: 'macd', title: 'DIF' }));
    const dea = chart.addLineSeries(mkLineSeriesOptions({ color: MACD_COLORS.dea, priceScaleId: 'macd', title: 'DEA' }));
    const macdHist = chart.addHistogramSeries(mkHistSeriesOptions({ priceScaleId: 'macd' }));

    const rsi6 = chart.addLineSeries(mkLineSeriesOptions({ color: RSI_COLORS.rsi6, priceScaleId: 'osc', title: 'RSI6' }));
    const rsi12 = chart.addLineSeries(mkLineSeriesOptions({ color: RSI_COLORS.rsi12, priceScaleId: 'osc', title: 'RSI12' }));
    const rsi24 = chart.addLineSeries(mkLineSeriesOptions({ color: RSI_COLORS.rsi24, priceScaleId: 'osc', title: 'RSI24' }));
    const rsi30 = chart.addLineSeries(mkLineSeriesOptions({
      color: CHART_THEME.refLine, priceScaleId: 'osc', lineStyle: LineStyle.Dashed, lineWidth: 1,
    }));
    const rsi70 = chart.addLineSeries(mkLineSeriesOptions({
      color: CHART_THEME.refLine, priceScaleId: 'osc', lineStyle: LineStyle.Dashed, lineWidth: 1,
    }));

    const kdjK = chart.addLineSeries(mkLineSeriesOptions({ color: KDJ_COLORS.k, priceScaleId: 'osc', title: 'K', visible: false }));
    const kdjD = chart.addLineSeries(mkLineSeriesOptions({ color: KDJ_COLORS.d, priceScaleId: 'osc', title: 'D', visible: false }));
    const kdjJ = chart.addLineSeries(mkLineSeriesOptions({ color: KDJ_COLORS.j, priceScaleId: 'osc', title: 'J', visible: false }));
    const kdj20 = chart.addLineSeries(mkLineSeriesOptions({
      color: CHART_THEME.refLine, priceScaleId: 'osc', lineStyle: LineStyle.Dashed, lineWidth: 1, visible: false,
    }));
    const kdj80 = chart.addLineSeries(mkLineSeriesOptions({
      color: CHART_THEME.refLine, priceScaleId: 'osc', lineStyle: LineStyle.Dashed, lineWidth: 1, visible: false,
    }));

    seriesRef.current = {
      candle, ma5, ma10, ma20, ma60, bollUpper, bollMid, bollLower,
      volume, dif, dea, macdHist,
      rsi6, rsi12, rsi24, rsi30, rsi70,
      kdjK, kdjD, kdjJ, kdj20, kdj80,
    };

    // 初始可见性
    {
      const isMa = mainType === 'ma';
      ma5.applyOptions({ visible: isMa });
      ma10.applyOptions({ visible: isMa });
      ma20.applyOptions({ visible: isMa });
      ma60.applyOptions({ visible: isMa });
      bollUpper.applyOptions({ visible: !isMa });
      bollMid.applyOptions({ visible: !isMa });
      bollLower.applyOptions({ visible: !isMa });
    }

    // 设置边距
    chart.priceScale('left').applyOptions({
      scaleMargins: { top: PANE_RATIOS.main.top, bottom: PANE_RATIOS.main.bottom }, minimumWidth: 60,
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: PANE_RATIOS.volume.top, bottom: PANE_RATIOS.volume.bottom }, visible: false,
    });
    chart.priceScale('macd').applyOptions({
      scaleMargins: { top: PANE_RATIOS.macd.top, bottom: PANE_RATIOS.macd.bottom }, visible: true, minimumWidth: 65,
    });
    chart.priceScale('osc').applyOptions({
      scaleMargins: { top: PANE_RATIOS.osc.top, bottom: PANE_RATIOS.osc.bottom }, visible: true, minimumWidth: 65,
    });

    // 填写数据
    candle.setData(chartData.candles);
    ma5.setData(chartData.ma5);
    ma10.setData(chartData.ma10);
    ma20.setData(chartData.ma20);
    ma60.setData(chartData.ma60);
    bollUpper.setData(chartData.bollUpper);
    bollMid.setData(chartData.bollMid);
    bollLower.setData(chartData.bollLower);
    volume.setData(chartData.volume);
    dif.setData(chartData.dif);
    dea.setData(chartData.dea);
    macdHist.setData(chartData.macdHist);
    rsi6.setData(chartData.rsi6);
    rsi12.setData(chartData.rsi12);
    rsi24.setData(chartData.rsi24);
    kdjK.setData(chartData.kdjK);
    kdjD.setData(chartData.kdjD);
    kdjJ.setData(chartData.kdjJ);

    // 参考线
    const times = chartData.candles.map(c => String(c.time));
    rsi30.setData(makeHorizontalLine(times, REF_LINES.rsi.low, CHART_THEME.refLine));
    rsi70.setData(makeHorizontalLine(times, REF_LINES.rsi.high, CHART_THEME.refLine));
    kdj20.setData(makeHorizontalLine(times, REF_LINES.kdj.low, CHART_THEME.refLine));
    kdj80.setData(makeHorizontalLine(times, REF_LINES.kdj.high, CHART_THEME.refLine));

    // 保存指标数据到 ref（用于十字光标按时间查找）
    indicatorDataRef.current = {
      dif: chartData.dif as { time: string; value: number }[],
      dea: chartData.dea as { time: string; value: number }[],
      macdHist: chartData.macdHist as { time: string; value: number }[],
      rsi6: chartData.rsi6 as { time: string; value: number }[],
      rsi12: chartData.rsi12 as { time: string; value: number }[],
      rsi24: chartData.rsi24 as { time: string; value: number }[],
      kdjK: chartData.kdjK as { time: string; value: number }[],
      kdjD: chartData.kdjD as { time: string; value: number }[],
      kdjJ: chartData.kdjJ as { time: string; value: number }[],
    };

    // 标记
    if (markers && markers.length > 0) {
      const lwcMarkers: SeriesMarker<string>[] = markers.map((m) => ({
        time: m.time,
        position: (m.direction === 'sell' ? 'aboveBar' : 'belowBar') as 'aboveBar' | 'belowBar',
        shape: m.shape as 'circle' | 'square' | 'arrowUp' | 'arrowDown',
        color: m.color,
        text: m.label,
        size: m.direction === 'buy' ? 1.5 : 1,
      }));
      candle.setMarkers(lwcMarkers);
    }

    // 十字光标事件
    const crosshairHandler = (param: MouseEventParams) => {
      if (!param.time || !param.seriesData) {
        setCrosshair(null);
        return;
      }
      const t = String(param.time);
      const bar = rawBarsRef.current.find(b => b.time === t);
      if (bar) {
        // 根据鼠标x坐标决定浮窗左右侧
        if (param.point && containerRef.current) {
          const midX = containerRef.current.clientWidth * 0.45;
          setOverlaySide(param.point.x < midX ? 'right' : 'left');
        }
        // 同时查找各指标在十字光标位置的值
        const data = indicatorDataRef.current;
        const lookup = (arr: { time: string; value: number }[]) => {
          const found = arr.find(d => d.time === t);
          return found ? found.value : null;
        };
        setCrosshair({
          ...bar,
          dif: lookup(data.dif),
          dea: lookup(data.dea),
          macdHist: lookup(data.macdHist),
          rsi6: lookup(data.rsi6),
          rsi12: lookup(data.rsi12),
          rsi24: lookup(data.rsi24),
          kdjK: lookup(data.kdjK),
          kdjD: lookup(data.kdjD),
          kdjJ: lookup(data.kdjJ),
        });
      }
    };
    chart.subscribeCrosshairMove(crosshairHandler);

    chart.timeScale().fitContent();

    return () => {
      chart.unsubscribeCrosshairMove(crosshairHandler);
      seriesRef.current = null;
      rawBarsRef.current = [];
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) {}
        chartRef.current = null;
      }
    };
  }, [chartData]);

  // 主图切换
  useEffect(() => {
    if (!seriesRef.current) return;
    const s = seriesRef.current;
    const isMa = mainType === 'ma';
    s.ma5.applyOptions({ visible: isMa });
    s.ma10.applyOptions({ visible: isMa });
    s.ma20.applyOptions({ visible: isMa });
    s.ma60.applyOptions({ visible: isMa });
    s.bollUpper.applyOptions({ visible: !isMa });
    s.bollMid.applyOptions({ visible: !isMa });
    s.bollLower.applyOptions({ visible: !isMa });
  }, [mainType]);

  // 副图切换
  useEffect(() => {
    if (!seriesRef.current) return;
    const s = seriesRef.current;
    const isRsi = oscType === 'rsi';
    s.rsi6.applyOptions({ visible: isRsi });
    s.rsi12.applyOptions({ visible: isRsi });
    s.rsi24.applyOptions({ visible: isRsi });
    s.rsi30.applyOptions({ visible: isRsi });
    s.rsi70.applyOptions({ visible: isRsi });
    s.kdjK.applyOptions({ visible: !isRsi });
    s.kdjD.applyOptions({ visible: !isRsi });
    s.kdjJ.applyOptions({ visible: !isRsi });
    s.kdj20.applyOptions({ visible: !isRsi });
    s.kdj80.applyOptions({ visible: !isRsi });
  }, [oscType]);

  // 更新条件标记
  useEffect(() => {
    if (!seriesRef.current) return;
    const candle = seriesRef.current.candle;
    if (markers && markers.length > 0) {
      const lwcMarkers: SeriesMarker<string>[] = markers.map((m) => ({
        time: m.time,
        position: (m.direction === 'sell' ? 'aboveBar' : 'belowBar') as 'aboveBar' | 'belowBar',
        shape: m.shape as 'circle' | 'square' | 'arrowUp' | 'arrowDown',
        color: m.color,
        text: m.label,
        size: m.direction === 'buy' ? 1.5 : 1,
      }));
      candle.setMarkers(lwcMarkers);
    } else {
      candle.setMarkers([]);
    }
  }, [markers]);

  return (
    <div className="relative h-full flex flex-col">
      <div ref={containerRef} className="flex-1" />
      <CrosshairOverlay info={crosshair} oscType={oscType} side={overlaySide} />
    </div>
  );
};

export default KLineChart;
