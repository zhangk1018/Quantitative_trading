import React, { useState, useEffect } from 'react';
import KLineChart from '../components/KLineChart';

interface KLineData {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

const KLinePage: React.FC = () => {
  const [data, setData] = useState<KLineData[]>([]);
  const [loading, setLoading] = useState(true);
  const [stockCode, setStockCode] = useState('000037');

  useEffect(() => {
    fetchKLineData();
  }, [stockCode]);

  const fetchKLineData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`http://localhost:5173/api/kline/${stockCode}`);
      const result = await response.json();
      
      if (result.success && result.data) {
        setData(result.data);
      }
    } catch (error) {
      console.error('获取K线数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-900 text-white">
        <div className="text-xl">加载中...</div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-gray-900 p-4">
      <div className="mb-4 flex items-center gap-4">
        <input
          type="text"
          value={stockCode}
          onChange={(e) => setStockCode(e.target.value)}
          placeholder="输入股票代码"
          className="px-4 py-2 rounded bg-gray-800 text-white border border-gray-700"
        />
        <button
          onClick={fetchKLineData}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          刷新
        </button>
      </div>
      <div className="h-[calc(100%-80px)] bg-gray-800 rounded-lg overflow-hidden">
        <KLineChart data={data} theme="dark" />
      </div>
    </div>
  );
};

export default KLinePage;