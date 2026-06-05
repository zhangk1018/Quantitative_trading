import React, { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';

const TestSimpleChart: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) {
      console.log('TestSimpleChart: 容器为 null');
      return;
    }

    console.log('TestSimpleChart: 开始创建图表');

    // 模拟数据
    const data = [
      { time: '2024/01/01', open: 10, high: 12, low: 9, close: 11 },
      { time: '2024/01/02', open: 11, high: 13, low: 10, close: 12 },
      { time: '2024/01/03', open: 12, high: 14, low: 11, close: 13 },
      { time: '2024/01/04', open: 13, high: 15, low: 12, close: 14 },
      { time: '2024/01/05', open: 14, high: 16, low: 13, close: 15 },
    ];

    console.log('TestSimpleChart: 模拟数据', data);

    // 创建图表
    const chart = createChart(containerRef.current, {
      width: 800,
      height: 400,
    });

    console.log('TestSimpleChart: 图表已创建');

    // 添加 K 线系列
    const series = chart.addCandlestickSeries({
      upColor: '#ef4444',
      downColor: '#22c55e',
    });

    console.log('TestSimpleChart: K线系列已添加');

    series.setData(data);

    console.log('TestSimpleChart: 数据已设置');

    chart.timeScale().fitContent();

    console.log('TestSimpleChart: 内容已自适应');

    return () => {
      chart.remove();
    };
  }, []);

  return (
    <div className="w-full h-screen flex flex-col bg-white">
      <div className="p-4 bg-yellow-100 text-center font-bold">
        简化版测试图表
      </div>
      <div 
        ref={containerRef} 
        style={{ 
          width: '800px', 
          height: '400px', 
          border: '2px solid red',
          margin: '20px auto',
          backgroundColor: '#fff'
        }} 
      />
    </div>
  );
};

export default TestSimpleChart;
