import React, { useEffect, useRef, useMemo, useState } from 'react';
import {
  createChart,
  Time,
} from 'lightweight-charts';
import type { KLineItem } from '../types';

interface QwenKLineChartProps {
  data: KLineItem[];
  theme?: 'light' | 'dark';
  stockCode?: string;
  stockName?: string;
}

const QwenKLineChart: React.FC<QwenKLineChartProps> = ({ 
  data, 
  theme = 'light',
  stockCode,
  stockName
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const candlestickSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  console.log('QwenKLineChart: 组件已加载，数据长度:', data.length);
  if (data.length > 0) {
    console.log('QwenKLineChart: 第一条数据:', data[0]);
    console.log('QwenKLineChart: 最后一条数据:', data[data.length - 1]);
  }

  // 转换数据格式 - 使用 yyyy-mm-dd 格式，确保时间顺序正确
  const chartData = useMemo(() => {
    // 确保数据按日期升序（从旧到新）
    const sortedData = [...data].sort((a, b) => 
      new Date(a.trade_date).getTime() - new Date(b.trade_date).getTime()
    );

    const result = sortedData.map((item) => {
      // 确保所有值都是数字
      const open = Number(item.open);
      const high = Number(item.high);
      const low = Number(item.low);
      const close = Number(item.close);
      const volume = Number(item.volume);

      return {
        time: item.trade_date as Time, // 直接使用 yyyy-mm-dd 格式
        open: open,
        high: high,
        low: low,
        close: close,
        value: volume,
        color: close >= open ? '#ef4444' : '#22c55e',
      };
    });
    console.log('QwenKLineChart: 转换后的图表数据长度:', result.length);
    if (result.length > 0) {
      console.log('QwenKLineChart: 转换后的第一条:', result[0]);
      console.log('QwenKLineChart: 转换后的最后一条:', result[result.length - 1]);
    }
    return result;
  }, [data]);

  // 初始化图表
  useEffect(() => {
    if (!chartContainerRef.current) {
      console.log('QwenKLineChart: chartContainerRef 为 null');
      return;
    }

    console.log('QwenKLineChart: 开始初始化图表');
    console.log('QwenKLineChart: 容器尺寸:', chartContainerRef.current.clientWidth, chartContainerRef.current.clientHeight);

    // 创建图表
    const chart = createChart(chartContainerRef.current, {
      width: Math.max(chartContainerRef.current.clientWidth, 800),
      height: 600,
    });
    chartRef.current = chart;

    console.log('QwenKLineChart: 图表实例已创建');

    // 设置基本样式
    chart.applyOptions({
      layout: {
        background: { type: 'solid' as any, color: theme === 'dark' ? '#1a1a1a' : '#ffffff' },
        textColor: theme === 'dark' ? '#d1d4dc' : '#191919',
      },
      grid: {
        vertLines: { color: theme === 'dark' ? '#2B2B43' : '#e6e6e6' },
        horzLines: { color: theme === 'dark' ? '#2B2B43' : '#e6e6e6' },
      },
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
    });

    console.log('QwenKLineChart: 样式已应用');

    // K线系列 - 中国股市风格：红涨绿跌
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#ef4444',
      downColor: '#22c55e',
      borderVisible: false,
      wickUpColor: '#ef4444',
      wickDownColor: '#22c55e',
    });
    candlestickSeriesRef.current = candlestickSeries;

    console.log('QwenKLineChart: K线系列已添加');

    // 成交量系列
    const volumeSeries = chart.addHistogramSeries({
      color: '#ef4444',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '',
    });
    volumeSeriesRef.current = volumeSeries;

    console.log('QwenKLineChart: 成交量系列已添加');

    // 设置数据
    if (chartData.length > 0) {
      candlestickSeries.setData(chartData as any);
      volumeSeries.setData(chartData as any);
      console.log('QwenKLineChart: 数据已设置');
      
      // 先使用 fitContent 显示所有数据
      chart.timeScale().fitContent();
      console.log('QwenKLineChart: fitContent() 已调用');
      
      // 然后调整显示最近40天，这样可以看到足够的 K 线并且不会太挤
      if (chartData.length > 40) {
        const startIndex = chartData.length - 40;
        chart.timeScale().setVisibleLogicalRange({
          from: startIndex,
          to: chartData.length,
        });
        console.log('QwenKLineChart: 可见范围已调整为最近40天');
      }
    } else {
      console.warn('QwenKLineChart: 没有数据可以显示');
    }

    // 自适应容器大小
    const handleResize = () => {
      if (chartContainerRef.current) {
        const newWidth = chartContainerRef.current.clientWidth;
        console.log('QwenKLineChart: 容器大小变化，新宽度:', newWidth);
        chart.applyOptions({
          width: newWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [chartData, theme]);

  // 观察容器大小
  useEffect(() => {
    const updateSize = () => {
      if (chartContainerRef.current) {
        setContainerSize({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    updateSize();
    const resizeObserver = new ResizeObserver(updateSize);
    if (chartContainerRef.current) {
      resizeObserver.observe(chartContainerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, []);

  // 计算最新价格和涨跌幅 - 安全处理
  const latestData = data[data.length - 1];
  const prevData = data[data.length - 2];
  
  // 确保所有值都是数字
  const getNumber = (val: any): number => {
    const num = Number(val);
    return isNaN(num) ? 0 : num;
  };

  const currentPrice = latestData ? getNumber(latestData.close) : 0;
  const prevPrice = prevData ? getNumber(prevData.close) : (latestData ? getNumber(latestData.open) : 0);
  const change = currentPrice - prevPrice;
  const changePct = prevPrice > 0 ? (change / prevPrice) * 100 : 0;
  const isRising = change >= 0;

  return (
    <div className="w-full h-full flex flex-col bg-white">
      {/* 头部信息 */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-4 bg-blue-50">
        <div className="flex items-center gap-2">
          {stockName && <span className="text-lg font-bold text-gray-900">{stockName}</span>}
          {stockCode && <span className="text-sm text-gray-500">{stockCode}</span>}
        </div>
        {latestData && (
          <div className="flex items-center gap-3">
            <span className={`text-xl font-bold ${isRising ? 'text-red-500' : 'text-green-500'}`}>
              {currentPrice.toFixed(2)}
            </span>
            <span className={`text-sm ${isRising ? 'text-red-500' : 'text-green-500'}`}>
              {isRising ? '+' : ''}{change.toFixed(2)}
            </span>
            <span className={`text-sm ${isRising ? 'text-red-500' : 'text-green-500'}`}>
              {isRising ? '+' : ''}{changePct.toFixed(2)}%
            </span>
          </div>
        )}
        <div className="ml-auto text-xs text-gray-400">
          数据: {data.length} 条 | 容器: {containerSize.width}x{containerSize.height}
        </div>
      </div>

      {/* 图表区域 - 给一个明确的高度 */}
      <div 
        ref={chartContainerRef} 
        className="flex-1 w-full"
        style={{ 
          minHeight: '600px',
          backgroundColor: '#fafafa',
          border: '1px dashed #ccc'
        }}
      />
    </div>
  );
};

export default QwenKLineChart;
