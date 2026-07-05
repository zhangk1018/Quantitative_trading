// KLineChart.tsx
// 展示组件 — 仅接收 chartData 和配置，负责 lightweight-charts 实例的创建/更新/销毁
// 不关心数据来源、loading/error 状态，可独立测试

import React, { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  LineWidth,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
  type LineSeriesOptions,
  type HistogramSeriesOptions,
  type DeepPartial,
} from 'lightweight-charts';
import { makeHorizontalLine, type ChartDataResult } from '@/lib/indicators/chart-adapter';
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

// ---- 类型 ----

export type MainType = 'ma' | 'boll';
export type OscType = 'rsi' | 'kdj';

interface KLineChartProps {
  chartData: ChartDataResult | null;
  mainType: MainType;
  oscType: OscType;
}

// ---- 常量 ----（已移至 chart-config.ts）

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

// ---- 辅助函数 ----

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

// ---- 组件 ----

const KLineChart: React.FC<KLineChartProps> = ({ chartData, mainType, oscType }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<SeriesRefs | null>(null);

  // 创建/重建图表
  useEffect(() => {
    if (!chartData || !containerRef.current) return;

    // 清理旧实例
    if (seriesRef.current) seriesRef.current = null;
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) {}
      chartRef.current = null;
    }

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
        vertLine: { color: CHART_THEME.crosshair, style: LineStyle.Dashed },
        horzLine: { color: CHART_THEME.crosshair, style: LineStyle.Dashed },
      },
      rightPriceScale: { visible: false },
      leftPriceScale: {
        visible: true, minimumWidth: 60, entireTextOnly: true, borderColor: CHART_THEME.border,
      },
      timeScale: {
        timeVisible: false, secondsVisible: false, borderColor: CHART_THEME.border, rightOffset: 5,
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

    // 初始可见性：按当前 mainType 隐藏 BOLL 或 MA
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

    // 设置边距（series 创建后才可调用 priceScale）
    chart.priceScale('left').applyOptions({
      scaleMargins: { top: PANE_RATIOS.main.top, bottom: PANE_RATIOS.main.bottom }, minimumWidth: 60,
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: PANE_RATIOS.volume.top, bottom: PANE_RATIOS.volume.bottom }, visible: false,
    });
    chart.priceScale('macd').applyOptions({
      scaleMargins: { top: PANE_RATIOS.macd.top, bottom: PANE_RATIOS.macd.bottom }, visible: false,
    });
    chart.priceScale('osc').applyOptions({
      scaleMargins: { top: PANE_RATIOS.osc.top, bottom: PANE_RATIOS.osc.bottom }, visible: false,
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

    chart.timeScale().fitContent();

    // 清理：组件卸载时销毁图表
    return () => {
      seriesRef.current = null;
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) {}
        chartRef.current = null;
      }
    };
  }, [chartData]);

  // 主图切换：MA / BOLL
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

  // 副图切换：RSI / KDJ
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

  return <div ref={containerRef} className="absolute inset-0" />;
};

export default KLineChart;