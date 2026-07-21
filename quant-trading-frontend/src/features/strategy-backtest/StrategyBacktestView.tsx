// src/features/strategy-backtest/StrategyBacktestView.tsx
// 策略回测主页面 — 有限状态机驱动（Idle→Loading→Running→Success/Failed）

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Alert, Button, Space } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import dayjs from 'dayjs';
import type { FilterNode, StrategyBacktestDefaults, StrategyBacktestResult } from './types';
import { getStrategyBacktestDefaults } from './storage';
import { parseTreeParam, stripUnsupportedFieldsForEngine } from './utils/filterTreeAdapter';
import { loadBacktestData, tryRestoreFromCache, saveToCache, computeCacheHash } from './utils/dataLoader';
import type { ValidationResult } from './utils/dataLoader';
import ConditionsSummary from './components/ConditionsSummary';
import BacktestPanel from './components/BacktestPanel';
import ProgressSection from './components/ProgressSection';
import type { ProgressInfo } from './components/ProgressSection';
import PerformanceMetrics from './components/PerformanceMetrics';
import ChartTabs from './components/ChartTabs';
import { getCustomIndicatorRunner, type BatchProgress } from './utils/customIndicatorRunner';
import { getCustomIndicatorById } from '../stock-picker/utils/customIndicatorStorage';

// ==================== 回测会话管理器（竞态条件防护） ====================

class BacktestSessionManager {
  private sessionId = 0;
  private abortController: AbortController | null = null;
  private worker: Worker | null = null;

  start(): BacktestSession {
    this.sessionId++;
    this.abortController?.abort();
    this.worker?.terminate();
    this.worker = null;
    this.abortController = new AbortController();
    const currentId = this.sessionId;
    return {
      id: currentId,
      signal: this.abortController!.signal,
      isActive: () => this.sessionId === currentId,
    };
  }

  setWorker(w: Worker): void {
    this.worker = w;
  }

  cancel(): void {
    this.abortController?.abort();
    this.worker?.terminate();
    this.worker = null;
  }
}

interface BacktestSession {
  id: number;
  signal: AbortSignal;
  isActive: () => boolean;
}

// ==================== 状态机类型 ====================

type BacktestState = 'idle' | 'loading' | 'running' | 'cancelling' | 'success' | 'failed';

// ==================== 辅助函数 ====================

/** 递归提取 FilterNode 中所有 custom_indicator 节点 */
function extractCustomIndicatorNodes(node: FilterNode | null): Array<{ scriptId: string; version: number }> {
  if (!node) return [];
  switch (node.type) {
    case 'and':
    case 'or':
      return node.children.flatMap(extractCustomIndicatorNodes);
    case 'not':
      return extractCustomIndicatorNodes(node.child);
    case 'custom_indicator':
      return [{ scriptId: node.scriptId, version: node.version }];
    default:
      return [];
  }
}

// ==================== 主组件 ====================

const StrategyBacktestView: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionManager = useRef(new BacktestSessionManager());

  // 状态
  const [state, setState] = useState<BacktestState>('idle');
  const [filterTree, setFilterTree] = useState<FilterNode | null>(null);
  const [strippedFields, setStrippedFields] = useState<string[]>([]);
  const [config, setConfig] = useState<StrategyBacktestDefaults>(getStrategyBacktestDefaults());
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(1, 'year'),
    dayjs(),
  ]);
  const [result, setResult] = useState<StrategyBacktestResult | null>(null);
  const [progress, setProgress] = useState<ProgressInfo>({ stage: 'data', percent: 0, message: '准备中...' });
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [benchmarkMissingRate, setBenchmarkMissingRate] = useState<number | undefined>(undefined);
  const [strategyType, setStrategyType] = useState<'filterTree' | 'filterTreeLayeredTP'>('filterTree');
  const [layeredTPParams, setLayeredTPParams] = useState({
    initialStopLossPct: -0.08,
    firstProfitPct: 0.08,
    firstSellPct: 0.25,
    secondProfitPct: 0.15,
    secondSellPct: 0.25,
    breakevenStopPct: 0.00,
    lockProfitPct: 0.06,
    hardFloorPct: 0.03,
    trailingDrawdownPct: 0.05,
    maPeriod: 20,
    maConfirmDays: 2,
    maExceptionDropPct: 0.07,
    maxHoldDays: 20,
    stopSlippagePct: 0.02,
  });

  // 解析 URL 参数
  useEffect(() => {
    const treeParam = searchParams.get('tree');
    try {
      const { tree, strippedFields: parsedStrippedFields } = parseTreeParam(treeParam);
      setFilterTree(tree);
      setStrippedFields(parsedStrippedFields);
    } catch (e) {
      setError((e as Error).message);
      setState('failed');
    }
  }, [searchParams]);

  // 修改选股条件
  const handleModifyConditions = useCallback(() => {
    const treeParam = searchParams.get('tree');
    navigate(`/picker?tree=${treeParam}`);
  }, [navigate, searchParams]);

  // 开始回测
  const handleStart = useCallback(async () => {
    if (!filterTree) {
      setError('请先配置选股条件');
      setState('failed');
      return;
    }

    // 检查是否有硬错误
    if (validation?.hardErrors && validation.hardErrors.length > 0) {
      setError(validation.hardErrors.join('\n'));
      setState('failed');
      return;
    }

    const startDate = dateRange[0].format('YYYY-MM-DD');
    const endDate = dateRange[1].format('YYYY-MM-DD');

    const session = sessionManager.current.start();
    setState('loading');
    setResult(null);
    setError(null);
    setProgress({ stage: 'data', percent: 0, message: '加载数据中...' });

    try {
      // 尝试从缓存恢复
      const cacheKey = computeCacheHash(
        filterTree,
        startDate,
        endDate,
        config.rebalanceInterval,
        config.maxPositions,
        config.dailyLossLimitEnabled || config.maxDrawdownStopEnabled,
      );
      const cached = await tryRestoreFromCache(cacheKey);
      if (cached && session.isActive()) {
        setProgress({ stage: 'data', percent: 1, message: '从缓存恢复' });
      }

      // 加载数据
      setProgress({ stage: 'data', percent: 0.3, message: '加载候选股票池...' });
      const { data, validation: v } = await loadBacktestData(filterTree, config, session.signal);

      if (!session.isActive()) return;

      setValidation(v);

      // 检查硬错误
      if (v.hardErrors.length > 0) {
        setError(v.hardErrors.join('\n'));
        setState('failed');
        return;
      }

      // 保存到缓存
      await saveToCache(cacheKey, data);

      // 计算基准缺失率
      if (data.benchmarkOhlcv && data.tradeDates.length > 0) {
        const missingRate = 1 - (data.benchmarkOhlcv.length / data.tradeDates.length);
        setBenchmarkMissingRate(missingRate);
      }

      // 预计算自编指标（若 filterTree 包含 custom_indicator 节点）
      const customIndicatorNodes = extractCustomIndicatorNodes(filterTree);
      let customIndicatorValues: Map<string, Map<string, (number | null)[]>> | undefined;

      if (customIndicatorNodes.length > 0 && session.isActive()) {
        setProgress({ stage: 'data', percent: 0.6, message: '加载自编指标脚本...' });

        // 去重（按 scriptId）
        const uniqueScripts = new Map<string, { id: string; name: string; code: string }>();
        for (const node of customIndicatorNodes) {
          if (!uniqueScripts.has(node.scriptId)) {
            const indicator = getCustomIndicatorById(node.scriptId);
            if (indicator) {
              uniqueScripts.set(node.scriptId, {
                id: indicator.id,
                name: indicator.name,
                code: indicator.formula,
              });
            }
          }
        }

        if (uniqueScripts.size > 0) {
          setProgress({ stage: 'data', percent: 0.65, message: '正在加载 Python 解释器（~12MB）...' });
          const runner = getCustomIndicatorRunner();
          await runner.init();

          // 准备脚本数据
          const scripts = Array.from(uniqueScripts.values()).map(s => ({
            id: s.id,
            name: s.name,
            code: s.code,
            stockCodes: Array.from(data.allOhlcv.keys()),
            allOhlcv: data.allOhlcv,
          }));

          // 执行脚本
          const results = await runner.execute(scripts, (batchProgress: BatchProgress) => {
            if (!session.isActive()) return;
            setProgress({
              stage: 'data',
              percent: 0.65 + (batchProgress.done / batchProgress.total) * 0.3,
              message: batchProgress.message,
            });
          });

          // 转换为 Map<scriptId, Map<stockCode, values[]>>
          customIndicatorValues = new Map();
          for (const [scriptId, result] of results) {
            customIndicatorValues.set(scriptId, result.values);
          }
        }
      }

      if (!session.isActive()) return;

      // 在传入引擎前过滤高风险基本面字段（这些字段无法历史回溯，仅用于初始股票池筛选）
      const { tree: engineFilterTree, strippedFields: strippedFundamentalFields } = stripUnsupportedFieldsForEngine(filterTree);
      if (!engineFilterTree) {
        setError('所有选股条件均为无法历史回溯的基本面字段，回测引擎需要至少一个可基于OHLCV计算的条件（如价格、涨跌幅、量比、技术形态等）');
        setState('failed');
        return;
      }

      // 启动 Worker
      setState('running');
      setProgress({ stage: 'indicators', percent: 0, message: '计算技术指标...' });

      const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
      sessionManager.current.setWorker(worker);

      const isLayeredTP = strategyType === 'filterTreeLayeredTP';

      worker.postMessage({
        type: 'start',
        input: {
          allOhlcv: data.allOhlcv,
          snapshots: data.snapshots,
          tradeDates: data.tradeDates,
          benchmarkOhlcv: data.benchmarkOhlcv,
          filterTree: engineFilterTree,
          config,
          startDate,
          endDate,
          strippedFields: [...strippedFields, ...strippedFundamentalFields],
          strategyType: 'filterTree',
          exitMode: isLayeredTP ? 'layeredTakeProfit' : undefined,
          layeredTPParams: isLayeredTP ? layeredTPParams : undefined,
          customIndicatorValues,
        },
      });

      worker.onmessage = (event: MessageEvent) => {
        if (!session.isActive()) {
          worker.terminate();
          return;
        }
        const { type, data: msgData } = event.data;
        if (type === 'progress') {
          setProgress(msgData as ProgressInfo);
        } else if (type === 'result') {
          setResult(msgData as StrategyBacktestResult);
          setState('success');
          setProgress({ stage: 'done', percent: 1, message: '回测完成' });
          worker.terminate();
        } else if (type === 'error') {
          setError(msgData as string);
          setState('failed');
          worker.terminate();
        }
      };

      worker.onerror = (err) => {
        if (session.isActive()) {
          setError(err.message);
          setState('failed');
        }
      };
    } catch (e) {
      if ((e as Error).name === 'AbortError' || !session.isActive()) return;
      setError((e as Error).message);
      setState('failed');
    }
  }, [filterTree, config, validation, dateRange, strategyType, layeredTPParams]);

  // 取消回测
  const handleCancel = useCallback(() => {
    setState('cancelling');
    sessionManager.current.cancel();
    setState('idle');
    setProgress({ stage: 'data', percent: 0, message: '准备中...' });
  }, []);

  // 清空结果
  const handleClear = useCallback(() => {
    setResult(null);
    setError(null);
    setValidation(null);
    setState('idle');
    setProgress({ stage: 'data', percent: 0, message: '准备中...' });
  }, []);

  const isRunning = state === 'loading' || state === 'running' || state === 'cancelling';

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-6xl mx-auto space-y-3">
          {/* 页面标题 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button
                type="text"
                size="small"
                onClick={() => navigate('/picker')}
              >
                ← 返回选股器
              </Button>
              <span className="text-base font-bold">策略回测</span>
            </div>
          </div>

          {/* 策略条件摘要 */}
          <ConditionsSummary
            filterTree={filterTree}
            onModify={handleModifyConditions}
          />

          {/* 回测参数面板 */}
          <BacktestPanel
            config={config}
            onConfigChange={setConfig}
            onStart={handleStart}
            dateRange={dateRange}
            onDateRangeChange={setDateRange}
            disabled={isRunning}
            strategyType={strategyType}
            onStrategyTypeChange={setStrategyType}
            layeredTPParams={layeredTPParams}
            onLayeredTPParamsChange={setLayeredTPParams}
          />

          {/* 基本面数据说明 */}
          {filterTree && (
            <Alert
              type="info"
              showIcon
              message="基本面/行情指标（PE/PB/市值/换手率等）仅用于初始股票池筛选（基于最新数据），回测每日调仓判断基于价格、成交量及技术形态等可历史计算的指标。"
              className="text-xs"
            />
          )}

          {/* 硬错误 */}
          {validation?.hardErrors && validation.hardErrors.length > 0 && (
            <Alert
              type="error"
              showIcon
              message="数据校验失败"
              description={validation.hardErrors.map((e, i) => <div key={i}>{e}</div>)}
              className="text-xs"
            />
          )}

          {/* 软错误 */}
          {validation?.softErrors && validation.softErrors.length > 0 && state !== 'failed' && (
            <Alert
              type="warning"
              showIcon
              message="数据警告"
              description={
                <div>
                  {validation.softErrors.map((e, i) => <div key={i}>{e}</div>)}
                  <div className="mt-1 text-text-disabled">部分数据将使用近似值，回测结果可能存在偏差</div>
                </div>
              }
              className="text-xs"
            />
          )}

          {/* 组合风控提示 */}
          {(config.dailyLossLimitEnabled || config.maxDrawdownStopEnabled) && (
            <Alert
              type="warning"
              showIcon
              message="已启用组合级风控（单日亏损/最大回撤），回测结果包含后验截断"
              className="text-xs"
            />
          )}

          {/* 进度条 */}
          {(state === 'loading' || state === 'running' || state === 'cancelling') && (
            <ProgressSection
              progress={progress}
              onCancel={handleCancel}
              disabled={state === 'cancelling'}
            />
          )}

          {/* 错误提示 */}
          {state === 'failed' && error && (
            <Alert
              type="error"
              showIcon
              message="回测失败"
              description={error}
              className="text-xs"
              closable
              onClose={handleClear}
            />
          )}

          {/* 绩效指标 */}
          {(state === 'success' || state === 'failed') && result && (
            <PerformanceMetrics
              metrics={result.metrics}
              benchmarkMissingRate={benchmarkMissingRate}
            />
          )}

          {/* 图表 + 明细 */}
          {(state === 'success' || state === 'failed') && result && (
            <ChartTabs result={result} />
          )}

          {/* 操作按钮 */}
          {(state === 'success' || state === 'failed') && (
            <div className="flex justify-center gap-2">
              <Button onClick={handleClear}>清空结果</Button>
              <Button onClick={() => {
                setConfig({ ...getStrategyBacktestDefaults() });
                setDateRange([dayjs().subtract(1, 'year'), dayjs()]);
                handleClear();
              }}>
                恢复默认设置
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StrategyBacktestView;