// StockAnalysisModal.tsx
// 容器组件 — 负责数据获取、loading/error 状态管理，渲染 KLineChart 展示组件

import React, { useEffect, useState, useCallback } from 'react';
import { Modal, Typography, Spin, Alert, Segmented } from 'antd';
import { fetchKLineData, toFriendlyMessage, type StockItem } from '@/features/stock-detail/api';
import { buildChartData, type ChartDataResult } from '@/lib/indicators/chart-adapter';
import { sanitizeNumber, sanitizePct } from '@/lib/indicators/indicators';
import { CHART_THEME } from '@/lib/indicators/chart-config';
import KLineChart, { type MainType, type OscType } from './KLineChart';

const { Text } = Typography;

// StockItem 的 stock_name 字段在 api.ts 中定义为必需，
// 但父组件传递的 stock 可能是 null，用 typescript Pick 保持类型对齐
type ModalStock = Pick<StockItem, 'stock_code' | 'stock_name' | 'close' | 'change_pct' | 'turnover_rate' | 'pe' | 'pb' | 'market_cap' | 'amount'> & {
  listed_board: string | null;
};

interface StockAnalysisModalProps {
  open: boolean;
  stock: ModalStock | null;
  onClose: () => void;
}

type ChartStatus = 'idle' | 'loading' | 'ready' | 'error';

const StockAnalysisModal: React.FC<StockAnalysisModalProps> = ({ open, stock, onClose }) => {
  const [status, setStatus] = useState<ChartStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [chartData, setChartData] = useState<ChartDataResult | null>(null);
  const [mainType, setMainType] = useState<MainType>('ma');
  const [oscType, setOscType] = useState<OscType>('rsi');
  const [retryCount, setRetryCount] = useState(0);

  // 数据获取（支持 AbortSignal 取消过期请求）
  useEffect(() => {
    if (!open) {
      setStatus('idle');
      setErrorMsg('');
      setChartData(null);
      return;
    }
    if (!stock?.stock_code) return;

    const abortController = new AbortController();
    setStatus('loading');
    setErrorMsg('');
    setChartData(null);

    const load = async () => {
      try {
        const klineData = await fetchKLineData(
          stock.stock_code,
          { limit: 500, adj: 'forward' },
          abortController.signal,
        );

        if (!klineData || klineData.length === 0) {
          setStatus('error');
          setErrorMsg('未获取到K线数据，请重试');
          return;
        }

        const data = buildChartData(klineData);
        setChartData(data);
        setStatus('ready');
      } catch (err: any) {
        if (err?.name === 'CanceledError' || abortController.signal.aborted) return;
        console.error('K线图表加载失败:', err);
        setStatus('error');
        setErrorMsg(toFriendlyMessage(err));
      }
    };

    load();

    return () => { abortController.abort(); };
  }, [open, stock?.stock_code, retryCount]);

  const handleRetry = useCallback(() => {
    setRetryCount(c => c + 1);
  }, []);

  const changeColor = (stock?.change_pct ?? 0) >= 0 ? CHART_THEME.green : CHART_THEME.red;

  return (
    <Modal
      title={null}
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      width="100vw"
      style={{ top: 0, padding: 0, maxWidth: '100vw' }}
      styles={{ body: { padding: 0, height: '100vh' } }}
      destroyOnHidden
      maskClosable={false}
      className="stock-analysis-modal"
    >
      <div className="flex flex-col h-full" style={{ background: CHART_THEME.bg }}>
        {/* 顶栏 — 股票信息 + 切换按钮 */}
        <div
          className="flex items-center justify-between px-4 py-1.5 shrink-0 z-10"
          style={{ background: CHART_THEME.bgHeader, borderBottom: `1px solid ${CHART_THEME.border}` }}
        >
          <div className="flex items-center gap-3 min-w-0 flex-wrap">
            <Text className="text-[#EAECEF] text-sm font-bold whitespace-nowrap">
              {stock?.stock_name || '-'}
            </Text>
            <Text className="text-[#848E9C] text-xs">{stock?.stock_code}</Text>
            <Text className="text-base font-bold" style={{ color: changeColor }}>
              {sanitizeNumber(stock?.close)}
            </Text>
            <Text className="text-xs" style={{ color: changeColor }}>
              {stock?.change_pct != null ? sanitizePct(stock.change_pct) : '--'}
            </Text>
            <Text className="text-[#848E9C] text-xs">PE {sanitizeNumber(stock?.pe, 2)}</Text>
            <Text className="text-[#848E9C] text-xs">PB {sanitizeNumber(stock?.pb, 2)}</Text>
            {stock?.market_cap != null && (
              <Text className="text-[#848E9C] text-xs">
                市值 {sanitizeNumber(stock.market_cap / 10000, 2)}亿
              </Text>
            )}
            {stock?.turnover_rate != null && (
              <Text className="text-[#848E9C] text-xs">换手 {sanitizeNumber(stock.turnover_rate, 2)}%</Text>
            )}
            {stock?.listed_board && <Text className="text-[#848E9C] text-xs">{stock.listed_board}</Text>}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Segmented
              value={mainType}
              onChange={(v) => setMainType(v as MainType)}
              options={[
                { label: 'MA', value: 'ma' },
                { label: 'BOLL', value: 'boll' },
              ]}
              size="small"
              style={{ background: CHART_THEME.border }}
            />
            <Segmented
              value={oscType}
              onChange={(v) => setOscType(v as OscType)}
              options={[
                { label: 'RSI', value: 'rsi' },
                { label: 'KDJ', value: 'kdj' },
              ]}
              size="small"
              style={{ background: CHART_THEME.border }}
            />
            <button
              className="text-[#848E9C] hover:text-[#EAECEF] text-base px-2"
              onClick={onClose}
            >
              ✕
            </button>
          </div>
        </div>

        {/* 图表区域 */}
        <div className="flex-1 relative" style={{ borderTop: `1px solid ${CHART_THEME.border}` }}>
          {status === 'loading' && (
            <div className="absolute inset-0 flex items-center justify-center z-20" style={{ background: CHART_THEME.bg }}>
              <Spin />
            </div>
          )}
          {status === 'error' && (
            <div className="absolute inset-0 flex items-center justify-center z-20 p-8" style={{ background: CHART_THEME.bg }}>
              <Alert
                type="error"
                message="K线图表加载失败"
                description={
                  <div>
                    <div>{errorMsg}</div>
                    <a onClick={handleRetry} style={{ color: '#2196f3', cursor: 'pointer', marginTop: 8, display: 'inline-block' }}>
                      点击重试
                    </a>
                  </div>
                }
                showIcon
              />
            </div>
          )}
          <KLineChart chartData={chartData} mainType={mainType} oscType={oscType} />
        </div>
      </div>
    </Modal>
  );
};

export default StockAnalysisModal;