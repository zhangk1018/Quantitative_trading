import React, { useState, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card, Switch, Spin, Descriptions, Tag, Empty, Alert } from 'antd';
import { fetchKLineData, fetchSignals, fetchStockDetail } from './api';
import { useStockChart } from './hooks/useStockChart';

const StockDetailPage: React.FC = () => {
  const { code } = useParams<{ code: string }>();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [indicators, setIndicators] = useState({ ma5: true, ma10: true, ma20: true });

  const { data: klineData, isLoading: isKlineLoading, error: klineError } = useQuery({
    queryKey: ['kline', code],
    queryFn: () => fetchKLineData(code!),
    enabled: !!code,
  });

  const { data: signalsData } = useQuery({
    queryKey: ['signals', code],
    queryFn: () => fetchSignals(code!),
    enabled: !!code,
  });

  const { data: detailData, error: detailError } = useQuery({
    queryKey: ['detail', code],
    queryFn: () => fetchStockDetail(code!),
    enabled: !!code,
  });

  useStockChart({
    containerRef: chartContainerRef,
    data: klineData || [],
    signals: signalsData || [],
    indicators,
  });

  if (!code) return <Empty description="未指定股票代码" />;
  if (isKlineLoading) return <Spin size="large" className="flex justify-center items-center h-[500px]" />;
  if (klineError || detailError) {
    return (
      <Alert 
        message="数据加载失败" 
        description={klineError?.message || detailError?.message} 
        type="error" showIcon 
      />
    );
  }

  const name = detailData?.stock_name || '-';
  const pe = detailData?.pe ?? null;
  const pb = detailData?.pb ?? null;
  const marketCapYi = detailData?.circ_mv 
    ? (detailData.circ_mv / 10000).toFixed(2) 
    : '-';

  return (
    <div className="flex h-full gap-4 p-4">
      {/* 左侧：图表区 */}
      <div className="flex-1 flex flex-col gap-4 min-w-0">
        <Card 
          className="bg-[#1E222D] border-none flex-1 flex flex-col overflow-hidden" 
          title={`${name} (${code}) - K线图`} 
          styles={{ 
            header: { color: '#EAECEF', borderBottom: '1px solid #2A2E39' },
            body: { flex: 1, display: 'flex', flexDirection: 'column', padding: 0, position: 'relative' } // ✅ 关键：body flex + relative
          }}
        >
          {(!klineData || klineData.length === 0) ? (
            <div className="flex items-center justify-center h-full text-[#848E9C]">暂无K线数据</div>
          ) : (
            // ✅ 关键：使用 absolute inset-0 确保图表容器填满 Card Body
            <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
          )}
        </Card>
        
        {/* 底部：指标开关 */}
        <Card 
          className="bg-[#1E222D] border-none h-16 flex items-center px-6 gap-8 shrink-0" 
          styles={{ body: { padding: '0 24px' } }}
        >
          <span className="text-[#848E9C]">技术指标：</span>
          <div className="flex gap-6">
            {[
              { key: 'ma5', label: 'MA5', color: 'text-yellow-500' },
              { key: 'ma10', label: 'MA10', color: 'text-blue-500' },
              { key: 'ma20', label: 'MA20', color: 'text-pink-500' }
            ].map(item => (
              <label key={item.key} className="flex items-center gap-2 cursor-pointer">
                <Switch 
                  size="small" 
                  checked={indicators[item.key as keyof typeof indicators]} 
                  onChange={(v) => setIndicators(p => ({...p, [item.key]: v}))} 
                />
                <span className={`text-sm ${item.color}`}>{item.label}</span>
              </label>
            ))}
          </div>
        </Card>
      </div>

      {/* 右侧：基本面面板 */}
      <div className="w-80 flex flex-col gap-4 shrink-0">
        <Card 
          title="基本信息" 
          className="bg-[#1E222D] border-none text-[#EAECEF]" 
          styles={{ header: { color: '#EAECEF', borderBottom: '1px solid #2A2E39' } }}
        >
          <Descriptions 
            column={1} 
            size="small" 
            styles={{ label: { color: '#848E9C' }, content: { color: '#EAECEF' } }}
          >
            <Descriptions.Item label="股票名称">{name}</Descriptions.Item>
            <Descriptions.Item label="股票代码"><Tag color="blue">{code}</Tag></Descriptions.Item>
            <Descriptions.Item label="所属行业">{detailData?.industry || '-'}</Descriptions.Item>
            <Descriptions.Item label="上市板块">{detailData?.listed_board || '-'}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card 
          title="估值指标" 
          className="bg-[#1E222D] border-none text-[#EAECEF]" 
          styles={{ header: { color: '#EAECEF', borderBottom: '1px solid #2A2E39' } }}
        >
          <div className="grid grid-cols-2 gap-3 text-center">
            <div className="bg-[#2A2E39] p-3 rounded">
              <div className="text-[#848E9C] text-xs mb-1">市盈率 (PE)</div>
              <div className="text-lg font-bold text-[#2962FF]">
                {pe !== null && pe !== undefined ? pe.toFixed(2) : '-'}
              </div>
            </div>
            <div className="bg-[#2A2E39] p-3 rounded">
              <div className="text-[#848E9C] text-xs mb-1">市净率 (PB)</div>
              <div className="text-lg font-bold text-[#2962FF]">
                {pb !== null && pb !== undefined ? pb.toFixed(2) : '-'}
              </div>
            </div>
            <div className="bg-[#2A2E39] p-3 rounded col-span-2">
              <div className="text-[#848E9C] text-xs mb-1">流通市值 (亿)</div>
              <div className="text-xl font-bold text-[#EAECEF]">{marketCapYi}</div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default StockDetailPage;