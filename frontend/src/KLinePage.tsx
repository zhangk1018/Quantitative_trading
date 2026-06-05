import React, { useState, useEffect } from 'react';
import QwenKLineChart from './components/QwenKLineChart';
import { useKLineData } from './hooks/useKLineData';

const KLinePage: React.FC = () => {
  const [code, setCode] = useState<string>('');
  const [name, setName] = useState<string>('');
  const { data, loading, error, fetchData } = useKLineData();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const c = params.get('kline');
    const n = params.get('name');
    if (c) {
      setCode(c);
      setName(n || '');
      fetchData(c);
    }
  }, [fetchData]);

  if (!code) {
    return (
      <div className="flex items-center justify-center h-screen bg-white">
        未指定股票代码
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-white">
        <div className="text-gray-600">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-white">
        <div className="text-red-500">加载失败：{error}</div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-white overflow-hidden">
      <QwenKLineChart 
        data={data} 
        theme="light" 
        stockCode={code}
        stockName={name || undefined}
      />
    </div>
  );
};

export default KLinePage;
