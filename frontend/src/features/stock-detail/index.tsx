import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Switch, Spin, Descriptions, Tag, Empty, Alert, Button, Skeleton } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { fetchKLineData, fetchSignals, fetchStockDetail, KLineDataResult, SignalItem, StockDetailInfo } from './api';
import { useStockChart } from './hooks/useStockChart';

/** 股票代码格式校验：6 位数字，以 0/3/6/8/9 开头 */
const STOCK_CODE_RE = /^[03689]\d{5}$/;

/** 用户可见的通用错误提示，不暴露内部堆栈 */
const GENERIC_ERROR_MSG = '数据加载失败，请稍后重试';

/**
 * 为不支持 AbortSignal 的请求包装可取消语义
 * 通过在 AbortSignal 上监听 abort 事件来提前 reject
 */
function withAbortSignal<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const onAbort = () => reject(new DOMException('Aborted', 'AbortError'));
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(
      (val) => { signal.removeEventListener('abort', onAbort); resolve(val); },
      (err) => { signal.removeEventListener('abort', onAbort); reject(err); },
    );
  });
}

const StockDetailPage: React.FC = () => {
  const { code } = useParams<{ code: string }>();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [indicators, setIndicators] = useState({ ma5: true, ma10: true, ma20: true });

  const [klineData, setKlineData] = useState<KLineDataResult | null>(null);
  const [isKlineLoading, setIsKlineLoading] = useState(false);
  const [klineError, setKlineError] = useState(false);

  const [signalsData, setSignalsData] = useState<SignalItem[]>([]);
  const [, setIsSignalLoading] = useState(false);
  const [signalError, setSignalError] = useState(false);

  const [detailData, setDetailData] = useState<StockDetailInfo | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);

  const isValidCode = code && STOCK_CODE_RE.test(code);

  const loadData = useCallback((stockCode: string, signal: AbortSignal) => {
    setIsKlineLoading(true);
    setIsSignalLoading(true);
    setIsDetailLoading(true);
    setKlineError(false);
    setSignalError(false);
    setDetailError(false);

    Promise.allSettled([
      withAbortSignal(fetchKLineData(stockCode, undefined, signal), signal),
      withAbortSignal(fetchSignals(stockCode), signal),
      withAbortSignal(fetchStockDetail(stockCode), signal),
    ]).then(([klineResult, signalResult, detailResult]) => {
      if (signal.aborted) return;

      if (klineResult.status === 'fulfilled') {
        setKlineData(klineResult.value);
      } else {
        setKlineError(true);
      }

      if (signalResult.status === 'fulfilled') {
        setSignalsData(signalResult.value);
      } else {
        setSignalError(true);
      }

      if (detailResult.status === 'fulfilled') {
        setDetailData(detailResult.value);
      } else {
        setDetailError(true);
      }

      setIsKlineLoading(false);
      setIsSignalLoading(false);
      setIsDetailLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!isValidCode) return;
    const controller = new AbortController();
    const currentCode = code!;

    loadData(currentCode, controller.signal);

    return () => { controller.abort(); };
  }, [code, isValidCode, loadData]);

  const handleRetry = useCallback(() => {
    if (!isValidCode || !code) return;
    const controller = new AbortController();
    loadData(code, controller.signal);
  }, [code, isValidCode, loadData]);

  useStockChart({
    containerRef: chartContainerRef,
    data: klineData?.items || [],
    signals: signalsData || [],
    indicators,
  });

  if (!isValidCode) return <Empty description={code ? `无效的股票代码: ${code}` : '未指定股票代码'} />;

  const name = detailData?.stock_name || '-';
  const pe = detailData?.pe ?? null;
  const pb = detailData?.pb ?? null;
  const marketCapYi = detailData?.circ_mv
    ? (detailData.circ_mv / 10000).toFixed(2)
    : '-';

  const hasAnyError = klineError || signalError || detailError;

  return (
    <div className="flex h-full gap-4 p-4">
      {/* 左侧：图表区 */}
      <div className="flex-1 flex flex-col gap-4 min-w-0">
        {hasAnyError && (
          <Alert
            message="部分数据加载失败"
            description={GENERIC_ERROR_MSG}
            type="warning"
            showIcon
            action={
              <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>
                重试
              </Button>
            }
            className="shrink-0"
          />
        )}
        <Card
          className="bg-[#1E222D] border-none flex-1 flex flex-col overflow-hidden"
          title={`${name} (${code}) - K线图`}
          styles={{
            header: { color: '#EAECEF', borderBottom: '1px solid #2A2E39' },
            body: { flex: 1, display: 'flex', flexDirection: 'column', padding: 0, position: 'relative' },
          }}
        >
          {isKlineLoading ? (
            <div className="flex items-center justify-center h-full">
              <Spin size="large" />
            </div>
          ) : klineError ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-[#848E9C]">
              <span>K线数据加载失败</span>
              <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>重试</Button>
            </div>
          ) : !klineData?.items || klineData.items.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[#848E9C]">暂无K线数据</div>
          ) : (
            <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
          )}
        </Card>

        {/* 底部：信号状态提示 */}
        {signalError && (
          <Alert
            message="信号数据加载失败（K线图表可能缺少买卖标记）"
            type="warning"
            showIcon
            closable
            className="shrink-0"
          />
        )}

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
              { key: 'ma20', label: 'MA20', color: 'text-pink-500' },
            ].map(item => (
              <label key={item.key} className="flex items-center gap-2 cursor-pointer">
                <Switch
                  size="small"
                  checked={indicators[item.key as keyof typeof indicators]}
                  onChange={(v) => setIndicators(p => ({ ...p, [item.key]: v }))}
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
          {isDetailLoading ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : detailError ? (
            <div className="flex flex-col items-center gap-2 py-4 text-[#848E9C]">
              <span>基本信息加载失败</span>
              <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>重试</Button>
            </div>
          ) : (
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
          )}
        </Card>

        <Card
          title="估值指标"
          className="bg-[#1E222D] border-none text-[#EAECEF]"
          styles={{ header: { color: '#EAECEF', borderBottom: '1px solid #2A2E39' } }}
        >
          {isDetailLoading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : detailError ? (
            <div className="flex flex-col items-center gap-2 py-4 text-[#848E9C]">
              <span>估值数据加载失败</span>
              <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>重试</Button>
            </div>
          ) : (
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
          )}
        </Card>
      </div>
    </div>
  );
};

export default StockDetailPage;