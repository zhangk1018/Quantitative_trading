import React, { useEffect, useRef, useState } from 'react';
import { Modal, Typography, Spin, Alert } from 'antd';

const { Text } = Typography;

declare global {
  interface Window {
    TradingView?: {
      widget: new (options: Record<string, any>) => { remove: () => void };
    };
    __TV_LOAD_FAILED__?: boolean;
    __TV_READY__?: boolean;
  }
}

type StockItem = {
  stock_code: string;
  stock_name: string;
  close: number | null;
  change_pct: number | null;
  turnover_rate: number | null;
  pe: number | null;
  pe_ttm?: number | null;
  pb: number | null;
  market_cap: number | null;
  amount: number | null;
  listed_board: string | null;
  patterns?: string[];
};

interface StockAnalysisModalProps {
  open: boolean;
  stock: StockItem | null;
  onClose: () => void;
}

const CONTAINER_ID = 'tv_kline_container';

function toTVSymbol(code: string): string {
  const clean = code.replace(/\.(SH|SZ|BJ)$/i, '');
  if (/^(6|5|9)/.test(clean)) return `SH:${clean}`;
  if (/^(0|2|3)/.test(clean)) return `SZ:${clean}`;
  if (/^(4|8)/.test(clean)) return `BJ:${clean}`;
  return `SH:${clean}`;
}

const StockAnalysisModal: React.FC<StockAnalysisModalProps> = ({ open, stock, onClose }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);
  const [tvStatus, setTvStatus] = useState<'loading' | 'ready' | 'failed'>('loading');

  // 轮询TradingView加载状态
  useEffect(() => {
    if (!open) return;
    if (window.TradingView) { setTvStatus('ready'); return; }
    if (window.__TV_LOAD_FAILED__) { setTvStatus('failed'); return; }

    setTvStatus('loading');
    const timer = setInterval(() => {
      if (window.TradingView) {
        setTvStatus('ready');
        clearInterval(timer);
      } else if (window.__TV_LOAD_FAILED__) {
        setTvStatus('failed');
        clearInterval(timer);
      }
    }, 500);

    const failTimeout = setTimeout(() => {
      if (!window.TradingView) setTvStatus('failed');
      clearInterval(timer);
    }, 15000);

    return () => {
      clearInterval(timer);
      clearTimeout(failTimeout);
    };
  }, [open]);

  // 初始化TradingView Widget
  useEffect(() => {
    if (tvStatus !== 'ready' || !open || !stock?.stock_code || !containerRef.current) return;

    if (widgetRef.current) {
      try { widgetRef.current.remove(); } catch (_) {}
      widgetRef.current = null;
    }

    const symbol = toTVSymbol(stock.stock_code);

    widgetRef.current = new window.TradingView!.widget({
      container_id: CONTAINER_ID,
      autosize: true,
      symbol,
      interval: 'D',
      timezone: 'Asia/Shanghai',
      theme: 'dark',
      style: '1',
      locale: 'zh_CN',
      toolbar_bg: '#131722',
      enable_publishing: false,
      allow_symbol_change: true,
      save_image: true,
      hide_top_toolbar: false,
      hide_side_toolbar: true,
      hide_legend: false,
      withdateranges: true,
      details: true,
      hotlist: false,
      calendar: false,
      show_popup_button: true,
      studies: [
        'BB@tv-basicstudies',
        'MACD@tv-basicstudies',
        'Volume@tv-basicstudies',
      ],
      studies_overrides: {
        'Bollinger Bands.median': '#f5a623',
        'Bollinger Bands.upper': '#4a90e2',
        'Bollinger Bands.lower': '#e879a9',
      },
      overrides: {
        'mainSeriesProperties.candleStyle.upColor': '#00d4aa',
        'mainSeriesProperties.candleStyle.downColor': '#f23645',
        'mainSeriesProperties.candleStyle.borderUpColor': '#00d4aa',
        'mainSeriesProperties.candleStyle.borderDownColor': '#f23645',
        'mainSeriesProperties.candleStyle.wickUpColor': '#00d4aa',
        'mainSeriesProperties.candleStyle.wickDownColor': '#f23645',
        'paneProperties.background': '#131722',
        'paneProperties.backgroundType': 'solid',
        'paneProperties.vertGridProperties.color': 'rgba(42,46,57,0.5)',
        'paneProperties.horzGridProperties.color': 'rgba(42,46,57,0.5)',
        'volumePaneSize': 'medium',
      },
      loading_screen: { backgroundColor: '#131722' },
      disabled_features: [
        'header_symbol_search',
        'symbol_search_hot_key',
      ],
    });

    return () => {
      if (widgetRef.current) {
        try { widgetRef.current.remove(); } catch (_) {}
        widgetRef.current = null;
      }
    };
  }, [tvStatus, open, stock?.stock_code]);

  const changeColor = stock?.change_pct != null && stock.change_pct >= 0 ? '#00d4aa' : '#f23645';

  return (
    <Modal
      title={null}
      open={open}
      onCancel={onClose}
      footer={null}
      width="100vw"
      style={{ top: 0, padding: 0, maxWidth: '100vw' }}
      styles={{ body: { padding: 0, height: '100vh' } }}
      destroyOnClose
      maskClosable={false}
      className="stock-analysis-modal"
    >
      <div className="flex flex-col h-full bg-[#131722]">
        {/* 顶部信息条 */}
        <div className="flex items-center justify-between px-4 py-1.5 border-b border-[#2A2E39] shrink-0 bg-[#1E222D] z-10">
          <div className="flex items-center gap-3 min-w-0 flex-wrap">
            <Text className="text-[#EAECEF] text-sm font-bold whitespace-nowrap">
              {stock?.stock_name || '-'}
            </Text>
            <Text className="text-[#848E9C] text-xs">{stock?.stock_code}</Text>
            {stock?.close != null && (
              <Text className="text-base font-bold" style={{ color: changeColor }}>
                {stock.close.toFixed(2)}
              </Text>
            )}
            {stock?.change_pct != null && (
              <Text className="text-xs" style={{ color: changeColor }}>
                {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct.toFixed(2)}%
              </Text>
            )}
            {stock?.pe != null && <Text className="text-[#848E9C] text-xs">PE {stock.pe.toFixed(2)}</Text>}
            {stock?.pb != null && <Text className="text-[#848E9C] text-xs">PB {stock.pb.toFixed(2)}</Text>}
            {stock?.market_cap != null && (
              <Text className="text-[#848E9C] text-xs">
                市值 {(stock.market_cap / 10000).toFixed(2)}亿
              </Text>
            )}
            {stock?.turnover_rate != null && (
              <Text className="text-[#848E9C] text-xs">换手 {stock.turnover_rate.toFixed(2)}%</Text>
            )}
            {stock?.listed_board && <Text className="text-[#848E9C] text-xs">{stock.listed_board}</Text>}
          </div>
          <button
            className="text-[#848E9C] hover:text-[#EAECEF] text-base px-2 flex-shrink-0"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {/* TradingView 图表区域 */}
        <div className="flex-1 relative">
          {tvStatus === 'loading' && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#131722] z-20">
              <Spin tip="正在加载TradingView图表组件..." />
            </div>
          )}
          {tvStatus === 'failed' && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#131722] z-20 p-8">
              <Alert
                type="error"
                message="TradingView 组件加载失败"
                description={
                  <div className="text-sm">
                    <p>无法连接到 TradingView CDN 服务器，可能是网络原因导致。</p>
                    <p className="mt-2">请检查网络连接后刷新页面重试。</p>
                  </div>
                }
                showIcon
                className="max-w-md"
              />
            </div>
          )}
          <div id={CONTAINER_ID} ref={containerRef} className="absolute inset-0" />
        </div>
      </div>
    </Modal>
  );
};

export default StockAnalysisModal;