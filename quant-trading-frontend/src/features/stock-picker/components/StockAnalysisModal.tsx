// StockAnalysisModal.tsx
// 容器组件 — 负责数据获取、loading/error 状态管理，渲染 KLineChart 展示组件

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Modal, Typography, Spin, Alert, Segmented, Tooltip } from 'antd';
import { fetchKLineData, toFriendlyMessage, type StockItem, type PatternMarker, type KLineDataResult } from '@/features/stock-detail/api';
import { buildChartData, type ChartDataResult } from '@/lib/indicators/chart-adapter';
import { sanitizeNumber, sanitizePct } from '@/lib/indicators/indicators';
import { CHART_THEME } from '@/lib/indicators/chart-config';
import KLineChart, { type MainType, type OscType } from './KLineChart';
import { detectConditions, type ConditionEvent, type ConditionConfig } from '@/lib/indicators/condition-detector';
import type { FilterCondition } from '../types/filterTree';

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
  conditions?: FilterCondition[];
}

type ChartStatus = 'idle' | 'loading' | 'ready' | 'error';

const StockAnalysisModal: React.FC<StockAnalysisModalProps> = ({ open, stock, onClose, conditions }) => {
  const [status, setStatus] = useState<ChartStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [chartData, setChartData] = useState<ChartDataResult | null>(null);
  const [mainType, setMainType] = useState<MainType>('ma');
  const [oscType, setOscType] = useState<OscType>('rsi');
  const [retryCount, setRetryCount] = useState(0);
  const [markers, setMarkers] = useState<ConditionEvent[]>([]);
  const [undetectable, setUndetectable] = useState<{ fieldKey: string; label: string; reason: string }[]>([]);

  // 从 conditions 中提取 fieldKey 和 lookbackDays
  const conditionConfigs = useMemo<ConditionConfig[]>(() => {
    if (!conditions || conditions.length === 0) return [];
    return conditions
      .map(c => ({ fieldKey: c.fieldKey, lookbackDays: c.lookbackDays }))
      .filter(c => Boolean(c.fieldKey));
  }, [conditions]);

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
        const klineResult = await fetchKLineData(
          stock.stock_code,
          { limit: 500, adj: 'forward' },
          abortController.signal,
        );

        if (!klineResult.items || klineResult.items.length === 0) {
          setStatus('error');
          setErrorMsg('未获取到K线数据，请重试');
          return;
        }

        const data = buildChartData(klineResult.items);
        setChartData(data);

        // --- 标记合并逻辑 ---
        // 将 conditionConfigs 拆为 pattern 和非 pattern 两组
        const patternFieldKeys = new Set(
          conditionConfigs.filter(c => c.fieldKey.startsWith('pattern_')).map(c => c.fieldKey)
        );
        const nonPatternConfigs = conditionConfigs.filter(c => !c.fieldKey.startsWith('pattern_'));
        const hasBackendPatterns = klineResult.patternMarkers.length > 0;

        let allEvents: ConditionEvent[] = [];
        const allUndetectable: { fieldKey: string; label: string; reason: string }[] = [];

        // 1) 非 pattern 条件（RSI/MACD 等）— 始终使用本地检测
        if (nonPatternConfigs.length > 0 && data.candles.length > 0) {
          const volLookup = new Map<string, number>();
          data.volume.forEach(v => volLookup.set(String(v.time), v.value));
          const bars = data.candles.map(c => ({
            time: String(c.time),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: volLookup.get(String(c.time)) ?? 0,
          }));
          bars.sort((a, b) => a.time.localeCompare(b.time));
          const result = detectConditions(bars, nonPatternConfigs);
          allEvents = result.events;
          allUndetectable.push(...result.undetectable);
        }

        // 2) pattern 条件 — 优先使用后端 TA-Lib，否则 fallback 到前端 heuristic
        if (patternFieldKeys.size > 0) {
          if (hasBackendPatterns) {
            // 后端 TA-Lib 数据（准确）
            const backendEvents = convertPatternMarkersToEvents(
              klineResult.patternMarkers, conditionConfigs, data.candles
            );
            allEvents = [...allEvents, ...backendEvents];
          } else if (data.candles.length > 0) {
            // fallback: 前端 heuristic 检测（后端还没上线 or 字段尚未就绪）
            const volLookup = new Map<string, number>();
            data.volume.forEach(v => volLookup.set(String(v.time), v.value));
            const bars = data.candles.map(c => ({
              time: String(c.time),
              open: c.open,
              high: c.high,
              low: c.low,
              close: c.close,
              volume: volLookup.get(String(c.time)) ?? 0,
            }));
            bars.sort((a, b) => a.time.localeCompare(b.time));
            const patternConfigs = conditionConfigs.filter(c => c.fieldKey.startsWith('pattern_'));
            const patternResult = detectConditions(bars, patternConfigs);
            allEvents = [...allEvents, ...patternResult.events];
            allUndetectable.push(...patternResult.undetectable);
          }
        }

        setMarkers(allEvents);
        setUndetectable(allUndetectable);

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
      style={{ top: 0, padding: 0, maxWidth: '100vw', margin: 0, paddingBottom: 0 }}
      styles={{
        body: { padding: 0, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' },
        content: { borderRadius: 0, padding: 0, margin: 0, height: '100vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' },
        header: { display: 'none' },
      }}
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
            {/* 条件图例 + 不可标注提示 */}
            {markers.length > 0 && (
              <div className="flex items-center gap-1 ml-2">
                {Array.from(new Set(markers.map(m => m.fieldKey))).map((fk) => {
                  const first = markers.find(m => m.fieldKey === fk);
                  if (!first) return null;
                  return (
                    <Tooltip key={fk} title={`${first.label} (${markers.filter(m => m.fieldKey === fk).length}次)`}>
                      <span
                        className="inline-block w-2 h-2 rounded-full"
                        style={{ background: first.color }}
                      />
                    </Tooltip>
                  );
                })}
              </div>
            )}
            {undetectable.length > 0 && (
              <Tooltip
                title={
                  <div>
                    {undetectable.map(u => (
                      <div key={u.fieldKey}>{u.label}: {u.reason}</div>
                    ))}
                  </div>
                }
              >
                <Text className="text-[#848E9C] text-xs cursor-help ml-2">
                  ⚡ {undetectable.length}项不可标注
                </Text>
              </Tooltip>
            )}
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
          <KLineChart chartData={chartData} mainType={mainType} oscType={oscType} markers={markers} />
        </div>
      </div>
    </Modal>
  );
};

/** 后端 PatternMarker 中 5 种形态的视觉映射 */
export const PATTERN_MARKER_VISUAL_MAP: Record<string, {
  label: string; color: string; shape: ConditionEvent['shape']; direction: ConditionEvent['direction'];
}> = {
  hammer:              { label: '锤子线',   color: '#2962FF', shape: 'arrowUp',  direction: 'buy' },
  morning_star:        { label: '早晨之星', color: '#26A69A', shape: 'arrowUp',  direction: 'buy' },
  evening_star:        { label: '黄昏之星', color: '#EF5350', shape: 'arrowDown', direction: 'sell' },
  bullish_engulfing:   { label: '看涨吞没', color: '#26A69A', shape: 'arrowUp',  direction: 'buy' },
  bearish_engulfing:   { label: '看跌吞没', color: '#EF5350', shape: 'arrowDown', direction: 'sell' },
};

/**
 * 将后端 TA-Lib 返回的 PatternMarker[] 转换为 ConditionEvent[]
 * 仅保留用户选中的 pattern 条件，过滤掉未选中的形态
 */
export function convertPatternMarkersToEvents(
  markers: PatternMarker[],
  allConfigs: ConditionConfig[],
  candles: { time: string | number }[],
): ConditionEvent[] {
  const activePatternKeys = new Set(
    allConfigs.filter(c => c.fieldKey.startsWith('pattern_')).map(c => c.fieldKey)
  );
  const timeSet = new Set(candles.map(c => String(c.time)));
  const events: ConditionEvent[] = [];

  for (const marker of markers) {
    if (!timeSet.has(marker.date)) continue;
    for (const pattern of marker.patterns) {
      const fieldKey = `pattern_${pattern}`;
      if (!activePatternKeys.has(fieldKey)) continue;
      const config = PATTERN_MARKER_VISUAL_MAP[pattern];
      if (!config) continue;
      events.push({
        time: marker.date,
        label: config.label,
        fieldKey,
        color: config.color,
        shape: config.shape,
        direction: config.direction,
      });
    }
  }
  return events;
}

export default StockAnalysisModal;