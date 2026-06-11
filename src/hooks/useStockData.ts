import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type { KLineData, StockInfo, TimePeriod } from '../types';

const generateMockData = (): KLineData[] => {
  const data: KLineData[] = [];
  let basePrice = 100;
  
  for (let i = 120; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    const timestamp = Math.floor(date.getTime() / 1000);
    
    const open = basePrice + (Math.random() - 0.5) * 4;
    const close = open + (Math.random() - 0.5) * 6;
    const high = Math.max(open, close) + Math.random() * 2;
    const low = Math.min(open, close) - Math.random() * 2;
    const volume = Math.floor(Math.random() * 10000000) + 1000000;
    
    data.push({
      timestamp,
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      volume,
    });
    
    basePrice = close;
  }
  
  return data;
};

export const useStockData = (code: string, period: TimePeriod = '1d') => {
  const [data, setData] = useState<KLineData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stockInfo, setStockInfo] = useState<StockInfo | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await axios.get<{ data?: any[] }>(`/api/kline/${code}`, {
        params: {
          period,
          limit: 120,
        },
      });
      
      if (response.data && response.data.data) {
        const klineData: KLineData[] = response.data.data.map((item: any) => ({
          timestamp: item.timestamp ? item.timestamp : Math.floor(new Date(item.trade_date).getTime() / 1000),
          open: parseFloat(item.open),
          high: parseFloat(item.high),
          low: parseFloat(item.low),
          close: parseFloat(item.close),
          volume: item.volume,
          ma5: item.ma5 ? parseFloat(item.ma5) : undefined,
          ma10: item.ma10 ? parseFloat(item.ma10) : undefined,
          ma20: item.ma20 ? parseFloat(item.ma20) : undefined,
          ma60: item.ma60 ? parseFloat(item.ma60) : undefined,
          rsi: item.rsi ? parseFloat(item.rsi) : undefined,
          macd: item.macd ? parseFloat(item.macd) : undefined,
          dif: item.dif ? parseFloat(item.dif) : undefined,
          dea: item.dea ? parseFloat(item.dea) : undefined,
        }));
        
        setData(klineData);
        
        if (klineData.length > 0) {
          const lastData = klineData[klineData.length - 1];
          const prevData = klineData[klineData.length - 2];
          const change = lastData.close - (prevData?.close || lastData.close);
          const changePercent = ((change / (prevData?.close || lastData.close)) * 100);
          
          setStockInfo({
            code,
            name: code,
            price: lastData.close,
            change: parseFloat(change.toFixed(2)),
            changePercent: parseFloat(changePercent.toFixed(2)),
          });
        }
      } else {
        console.warn('API 返回空数据，使用模拟数据');
        const mockData = generateMockData();
        setData(mockData);
        
        const lastData = mockData[mockData.length - 1];
        const prevData = mockData[mockData.length - 2];
        const change = lastData.close - (prevData?.close || lastData.close);
        const changePercent = ((change / (prevData?.close || lastData.close)) * 100);
        
        setStockInfo({
          code,
          name: code,
          price: lastData.close,
          change: parseFloat(change.toFixed(2)),
          changePercent: parseFloat(changePercent.toFixed(2)),
        });
      }
    } catch (err) {
      console.error('获取K线数据失败:', err);
      setError('获取K线数据失败，使用模拟数据');
      
      const mockData = generateMockData();
      setData(mockData);
      
      const lastData = mockData[mockData.length - 1];
      const prevData = mockData[mockData.length - 2];
      const change = lastData.close - (prevData?.close || lastData.close);
      const changePercent = ((change / (prevData?.close || lastData.close)) * 100);
      
      setStockInfo({
        code,
        name: code,
        price: lastData.close,
        change: parseFloat(change.toFixed(2)),
        changePercent: parseFloat(changePercent.toFixed(2)),
      });
    } finally {
      setLoading(false);
    }
  }, [code, period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, stockInfo, refetch: fetchData };
};
