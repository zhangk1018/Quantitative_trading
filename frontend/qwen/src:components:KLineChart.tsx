import React, { useEffect, useRef, useMemo } from 'react';
import {
  createChart,
  ChartOptions,
  CandlestickSeries,
  HistogramSeries,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';

interface KLineData {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

interface KLineChartProps {
  data: KLineData[];
  theme?: 'light' | 'dark';
}

const KLineChart: React.FC<KLineChartProps> = ({ data, theme = 'dark' }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const candlestickSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);

  // 转换数据格式
  const chartData = useMemo(() => {
    return data.map((item) => ({
      time: item.trade_date.replace(/-/g, '/') as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
      value: item.volume,
      color: item.close >= item.open ? '#26a69a' : '#ef5350',
    }));
  }, [data]);

  // 初始化图表
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // 图表配置
    const chartOptions: ChartOptions = {
      layout: {
        background: { type: 'solid', color: theme === 'dark' ? '#1a1a1a' : '#ffffff' },
        textColor: theme === 'dark' ? '#d1d4dc' : '#191919',
      },
      grid: {
        vertLines: { color: theme === 'dark' ? '#2B2B43' : '#e6e6e6' },
        horzLines: { color: theme === 'dark' ? '#2B2B43' : '#e6e6e6' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 600,
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: theme === 'dark' ? '#2B2B43' : '#e6e6e6',
      },
      timeScale: {
        borderColor: theme === 'dark' ? '#2B2B43' : '#e6e6e6',
        timeVisible: true,
        secondsVisible: false,
      },
    };

    // 创建图表
    const chart = createChart(chartContainerRef.current, chartOptions);
    chartRef.current = chart;

    // K线系列
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });
    candlestickSeriesRef.current = candlestickSeries;

    // 成交量系列
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '',
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });
    volumeSeriesRef.current = volumeSeries;

    // 设置数据
    candlestickSeries.setData(chartData as any);
    volumeSeries.setData(chartData as any);

    // 自适应容器大小
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [chartData, theme]);

  return <div ref={chartContainerRef} className="w-full h-full" />;
};

export default KLineChart;