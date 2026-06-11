import { useEffect, useRef, useCallback } from 'react';
import * as KLineCharts from 'klinecharts';
import type { KLineData } from '../types';

interface KLineChartProps {
  data: KLineData[];
  height?: number;
}

export const KLineChart = ({ data, height = 600 }: KLineChartProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<KLineCharts.Chart | null>(null);
  const latestDataRef = useRef<KLineCharts.KLineData[]>([]);

  const initChart = useCallback(() => {
    if (!containerRef.current) {
      console.error('容器未找到');
      return;
    }

    // 清理旧图表
    if (chartRef.current) {
      try {
        KLineCharts.dispose(chartRef.current);
      } catch (e) {
        console.warn('清理旧图表失败:', e);
      }
      chartRef.current = null;
    }

    // 初始化新图表
    console.log('正在初始化 KLineCharts...');
    const chart = KLineCharts.init(containerRef.current, {
      styles: {
        grid: {
          vertical: {
            color: '#2a2a4a',
          },
          horizontal: {
            color: '#2a2a4a',
          },
        },
      },
    });

    if (chart) {
      chartRef.current = chart;
      console.log('KLineCharts 初始化成功');

      // 创建指标
      chart.createIndicator('MA');
      chart.createIndicator('Volume');

      // 设置默认周期
      chart.setPeriod({ type: 'day', span: 1 });

      // 如果有缓存数据，立即设置
      if (latestDataRef.current.length > 0) {
        setChartData(latestDataRef.current);
      }
    } else {
      console.error('KLineCharts 初始化失败');
    }
  }, []);

  const setChartData = useCallback((klineData: KLineCharts.KLineData[]) => {
    if (!chartRef.current || klineData.length === 0) {
      return;
    }

    console.log('正在设置图表数据，数据量:', klineData.length);

    // 设置数据加载器
    chartRef.current.setDataLoader({
      getBars: (params) => {
        console.log('DataLoader getBars 被调用，type:', params.type);
        if (params.type === 'init' || params.type === 'update') {
          params.callback(klineData, { forward: false, backward: false });
        } else {
          params.callback([], { forward: false, backward: false });
        }
      },
    });

    // 滚动到最新数据
    setTimeout(() => {
      if (chartRef.current) {
        console.log('滚动到最新数据...');
        chartRef.current.scrollToRealTime();
      }
    }, 150);
  }, []);

  useEffect(() => {
    initChart();

    const handleResize = () => {
      if (chartRef.current) {
        chartRef.current.resize();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        try {
          KLineCharts.dispose(chartRef.current);
        } catch (e) {
          console.warn('清理图表失败:', e);
        }
        chartRef.current = null;
      }
    };
  }, [initChart]);

  useEffect(() => {
    if (data.length > 0) {
      // 格式化数据
      const formattedData: KLineCharts.KLineData[] = data.map((item) => ({
        timestamp: item.timestamp,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
        volume: item.volume,
      }));

      // 缓存数据
      latestDataRef.current = formattedData;

      console.log('KLineChart 收到数据:', data.length, '条');
      console.log('第一条数据:', formattedData[0]);
      console.log('最后一条数据:', formattedData[formattedData.length - 1]);

      // 设置图表数据
      setChartData(formattedData);
    }
  }, [data, setChartData]);

  return (
    <div
      ref={containerRef}
      className="w-full bg-gray-900 rounded-lg"
      style={{ height: `${height}px` }}
    />
  );
};
