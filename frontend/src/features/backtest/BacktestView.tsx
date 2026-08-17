// BacktestView.tsx — 回测分析主容器

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Card, Progress, Tabs, Collapse, Button, message, Divider, Typography, Form } from 'antd';
import { ClearOutlined, PlayCircleOutlined, ReloadOutlined, LoadingOutlined } from '@ant-design/icons';
import BacktestConfigPanel from './BacktestConfigPanel';
import BacktestWarningBar from './BacktestWarningBar';
import BacktestMetrics from './BacktestMetrics';
import BacktestChart from './BacktestChart';
import BacktestEquityCurve from './BacktestEquityCurve';
import BacktestTradeLog from './BacktestTradeLog';
import BacktestDiagnostics from './BacktestDiagnostics';
import BacktestUniverseResult from './BacktestUniverseResult';
import { saveResult, clearAllResults } from './backtestStorage';
import { fetchKLineData } from '../stock-detail/api';
import { useBacktestWorker } from './hooks/useBacktestWorker';
import type { KlineBar } from '../../lib/indicators/indicators';
import type {
  BacktestConfig,
  BacktestFormValues,
  BacktestOutput,
  BacktestInput,
  BacktestEngineConfig,
  BacktestStock,
  BacktestUniverseResult as UniverseResult,
  ProgressInfo,
  Trade,
  StoredBacktestResult,
} from './backtestTypes';
import { PREHEAT_DAYS, KLINE_FETCH_LIMIT, STORAGE_SCHEMA_VERSION } from './constants';
import { BacktestErrorBoundary } from './ErrorBoundary';

const { Text } = Typography;

const BacktestView: React.FC = () => {
  const [form] = Form.useForm<BacktestFormValues>();
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [output, setOutput] = useState<BacktestOutput | null>(null);
  const [bars, setBars] = useState<KlineBar[]>([]);
  const [focusTrade, setFocusTrade] = useState<Trade | null>(null);
  /** 批量回测结果列表 */
  const [universeResults, setUniverseResults] = useState<UniverseResult[] | null>(null);
  /** 批量回测当前查看的股票索引 */
  const [activeStockIndex, setActiveStockIndex] = useState(0);
  /** 当前回测的配置引用（Worker 回调中需要访问 config） */
  const configRef = useRef<BacktestConfig | null>(null);
  /** AbortController 引用，用于取消进行中的网络请求 */
  const abortRef = useRef<AbortController | null>(null);
  /** 批量回测中存活的一次性 Worker 集合（取消/卸载时统一终止） */
  const universeWorkersRef = useRef<Set<Worker>>(new Set());
  /** 批量回测是否正在运行 */
  const [isBatchRunning, setIsBatchRunning] = useState(false);

  // Worker 回调
  const handleWorkerProgress = useCallback((info: ProgressInfo) => {
    setProgress(info);
  }, []);

  const handleWorkerResult = useCallback((result: BacktestOutput) => {
    setOutput(result);
    setProgress({ stage: 'done', percent: 100, message: '回测完成' });

    // 保存到 IndexedDB（含版本号）
    const config = configRef.current;
    if (config) {
      const stored: StoredBacktestResult = {
        id: `${config.stockCode}_${Date.now()}`,
        createdAt: new Date().toISOString(),
        version: STORAGE_SCHEMA_VERSION,
        config,
        output: result,
      };
      saveResult(stored).catch(() => {});
    }
  }, []);

  const handleWorkerError = useCallback((errorMsg: string) => {
    message.error(`回测失败: ${errorMsg}`);
  }, []);

  const { start: startWorker, cancel: cancelWorker, isRunning: isSingleRunning } = useBacktestWorker({
    onProgress: handleWorkerProgress,
    onResult: handleWorkerResult,
    onError: handleWorkerError,
  });

  /** 合并单股回测和批量回测的运行状态 */
  const isRunning = isSingleRunning || isBatchRunning;

  /** 终止批量回测中所有存活 Worker */
  const terminateUniverseWorkers = useCallback(() => {
    for (const w of universeWorkersRef.current) w.terminate();
    universeWorkersRef.current.clear();
  }, []);

  // 组件卸载时清理批量 Worker
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      terminateUniverseWorkers();
    };
  }, [terminateUniverseWorkers]);

  const handleReset = useCallback(() => {
    cancelWorker();
    terminateUniverseWorkers();
    abortRef.current?.abort();
    setIsBatchRunning(false);
    setProgress(null);
    setOutput(null);
    setBars([]);
    setFocusTrade(null);
    setUniverseResults(null);
    setActiveStockIndex(0);
    configRef.current = null;
    form.resetFields();
  }, [cancelWorker, terminateUniverseWorkers, form]);

  /** 拉取单只股票 K 线并转换为 KlineBar（返回 null 表示无数据） */
  const fetchAndBuildBars = useCallback(async (
    code: string,
    config: BacktestConfig,
    signal: AbortSignal,
  ): Promise<KlineBar[] | null> => {
    const fetchStart = new Date(config.startDate);
    fetchStart.setDate(fetchStart.getDate() - PREHEAT_DAYS);
    const fetchStartStr = fetchStart.toISOString().slice(0, 10);

    const klineResult = await fetchKLineData(code, {
      adj: 'forward',
      start_date: fetchStartStr,
      end_date: config.endDate,
      limit: KLINE_FETCH_LIMIT,
    }, signal);

    const items = klineResult.items;
    if (!items || items.length === 0) return null;

    return items.map((item: any) => ({
      time: item.time,
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
      volume: Number(item.volume),
    }));
  }, []);

  /** 构造引擎配置（批量模式下每只股票替换 stockCode） */
  const buildEngineConfig = useCallback((config: BacktestConfig, stockCode: string): BacktestEngineConfig => ({
    stockCode,
    startDate: config.startDate,
    endDate: config.endDate,
    capital: config.capital,
    sellStrategy: config.sellStrategy,
    trailingStopPct: config.trailingStopPct,
    atrPeriod: config.atrPeriod,
    atrMultiplier: config.atrMultiplier,
    emaShort: config.emaShort,
    emaLong: config.emaLong,
    feeRate: config.feeRate,
    slippage: config.slippage,
    riskFreeRate: config.riskFreeRate,
    executionPrice: config.executionPrice,
    maxDeferDays: config.maxDeferDays,
    indicatorParams: config.indicatorParams,
  }), []);

  /** 批量模式下单只股票的一次性 Worker 回测（Promise 化） */
  const runStockInWorker = useCallback((input: BacktestInput): Promise<BacktestOutput> => {
    return new Promise<BacktestOutput>((resolve, reject) => {
      let worker: Worker;
      try {
        worker = new Worker(
          new URL('./backtest.worker.ts', import.meta.url),
          { type: 'module' },
        );
      } catch (err) {
        reject(new Error(`Worker 创建失败: ${err instanceof Error ? err.message : String(err)}`));
        return;
      }
      universeWorkersRef.current.add(worker);

      worker.onmessage = (e: MessageEvent) => {
        const { type, data } = e.data;
        if (type === 'progress') {
          setProgress(data as ProgressInfo);
        } else if (type === 'result') {
          universeWorkersRef.current.delete(worker);
          worker.terminate();
          resolve(data as BacktestOutput);
        } else if (type === 'error') {
          universeWorkersRef.current.delete(worker);
          worker.terminate();
          reject(new Error((data as string) || '未知 Worker 错误'));
        }
      };

      worker.onerror = (ev: ErrorEvent) => {
        universeWorkersRef.current.delete(worker);
        worker.terminate();
        reject(new Error(`Worker 异常崩溃: ${ev.message || ev.filename || '未知错误'}`));
      };

      worker.postMessage({ type: 'run', input });
    });
  }, []);

  const handleStart = useCallback(async (config: BacktestConfig) => {
    // 取消上一次可能未完成的请求和 Worker
    abortRef.current?.abort();
    terminateUniverseWorkers();
    const controller = new AbortController();
    abortRef.current = controller;

    const stocks: BacktestStock[] = Array.isArray(config.stocks) && config.stocks.length > 1
      ? config.stocks
      : [{ stockCode: config.stockCode, stockName: config.stockName }];

    configRef.current = config;
    setOutput(null);
    setUniverseResults(null);
    setActiveStockIndex(0);
    setProgress({ stage: 'fetching', percent: 0, message: '正在获取K线数据...' });

    try {
      // 单股回测（保留原逻辑）
      if (stocks.length === 1) {
        const stock = stocks[0];
        const klineBars = await fetchAndBuildBars(stock.stockCode, config, controller.signal);
        if (klineBars === null) {
          message.error('未获取到K线数据');
          return;
        }

        // 检查数据范围是否覆盖用户请求的起始日期
        const firstBarDate = klineBars[0].time;
        const daysDiff = Math.floor(
          (new Date(firstBarDate).getTime() - new Date(config.startDate).getTime()) / (1000 * 60 * 60 * 24)
        );
        if (daysDiff > 30) {
          message.warning(
            `数据范围提示：您选择的起始日期为 ${config.startDate}，但系统最早的数据为 ${firstBarDate}。回测将从 ${firstBarDate} 开始。`,
            8,
          );
        }

        setBars(klineBars);

        const input: BacktestInput = {
          bars: klineBars,
          buyCondition: config.buyCondition,
          config: buildEngineConfig(config, stock.stockCode),
        };
        startWorker(input);
        return;
      }

      // 批量回测：逐股拉取 K 线 + 逐股回测，收集结果
      setIsBatchRunning(true);
      const results: UniverseResult[] = [];
      try {
        for (let i = 0; i < stocks.length; i++) {
          const stock = stocks[i];
          if (controller.signal.aborted) break;
          setProgress({
            stage: 'fetching',
            percent: Math.round((i / stocks.length) * 100),
            message: `正在回测 (${i + 1}/${stocks.length}) ${stock.stockName || stock.stockCode}`,
          });

          const klineBars = await fetchAndBuildBars(stock.stockCode, config, controller.signal);
          if (klineBars === null || klineBars.length === 0) {
            results.push({
              stockCode: stock.stockCode,
              stockName: stock.stockName,
              bars: [],
              output: {
                trades: [],
                equityCurve: [],
                summary: {
                  totalReturn: 0, annualizedReturn: 0, winRate: 0, profitLossRatio: 0,
                  maxDrawdown: 0, maxConsecutiveLoss: 0, avgHoldDays: 0, sharpeRatio: 0,
                  totalTrades: 0, forcedCloseCount: 0, benchmarkReturn: 0, tradingDays: 0, warmupDays: 0,
                },
                warnings: ['未获取到K线数据'],
                diagnostics: [],
              },
              error: '未获取到K线数据',
            });
            continue;
          }

          const input: BacktestInput = {
            bars: klineBars,
            buyCondition: config.buyCondition,
            config: buildEngineConfig(config, stock.stockCode),
          };
          const stockOutput = await runStockInWorker(input);
          results.push({
            stockCode: stock.stockCode,
            stockName: stock.stockName,
            bars: klineBars,
            output: stockOutput,
          });
        }
      } finally {
        setIsBatchRunning(false);
      }

      setUniverseResults(results);
      setProgress({ stage: 'done', percent: 100, message: '回测完成' });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      message.error(`回测失败: ${msg}`);
    }
  }, [startWorker, fetchAndBuildBars, buildEngineConfig, runStockInWorker, terminateUniverseWorkers, setIsBatchRunning]);

  // 浏览器自测用：暴露 form 和 handleStart 到 window
  useEffect(() => {
    (window as any).__backtestForm = form;
    (window as any).__backtestHandleStart = handleStart;
    (window as any).__backtestSetOutput = setOutput;
    (window as any).__backtestSetProgress = setProgress;
    return () => {
      delete (window as any).__backtestForm;
      delete (window as any).__backtestHandleStart;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCancel = useCallback(() => {
    cancelWorker();
    abortRef.current?.abort();
    terminateUniverseWorkers();
    setIsBatchRunning(false);
    setProgress(null);
  }, [cancelWorker, terminateUniverseWorkers]);

  const handleClearCache = useCallback(async () => {
    await clearAllResults();
    message.success('本地缓存已清空');
  }, []);

  const handleTradeClick = useCallback((trade: Trade) => {
    setFocusTrade(trade);
  }, []);

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* 左侧配置面板 */}
        <div className="w-[280px] flex-shrink-0 bg-bg-panel border-r border-border-color flex flex-col h-full">
          <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0">
            <BacktestConfigPanel
              onStart={handleStart}
              loading={isRunning}
              onCancel={handleCancel}
              form={form}
            />
          </div>
          {/* 底部固定按钮栏 */}
          <div className="p-3 border-t border-border-color bg-bg-panel">
            <div className="flex gap-2">
              <Button
                type="primary"
                data-testid="start-backtest"
                className={`flex-1 border-color-accent ${
                  isRunning ? 'bg-color-accent/60 cursor-not-allowed' : 'bg-color-accent hover:bg-color-accent/80'
                }`}
                icon={isRunning ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
                onClick={() => form.submit()}
                disabled={isRunning}
              >
                {isRunning ? '计算中...' : '开始回测'}
              </Button>
              {isRunning ? (
                <Button onClick={handleCancel} danger className="flex-1">
                  取消
                </Button>
              ) : (
                <Button
                  data-testid="reset-backtest"
                  className="flex-1 bg-bg-card border-border-color text-text-secondary hover:text-text-primary"
                  icon={<ReloadOutlined />}
                  onClick={handleReset}
                >
                  重置
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* 右侧结果区 */}
        <div className="flex-1 flex flex-col h-full min-h-0 overflow-y-auto">
          <div style={{ padding: 16 }}>
            {/* 进度条 */}
            {isRunning && progress && (
              <Card size="small" className="!bg-bg-panel !border-border-color !mb-3">
                <Progress percent={progress.percent} status="active" strokeColor="#2962FF" />
                <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {progress.message}
                </Text>
              </Card>
            )}

            {universeResults && (
              <BacktestErrorBoundary onReset={handleReset} errorTitle="批量回测结果渲染失败">
                <BacktestUniverseResult
                  results={universeResults}
                  activeIndex={activeStockIndex}
                  onSelectStock={setActiveStockIndex}
                  initialCapital={configRef.current?.capital ?? 100000}
                />
              </BacktestErrorBoundary>
            )}

            {output && (
              <BacktestErrorBoundary onReset={handleReset} errorTitle="回测结果渲染失败">
                {/* 警告面板 */}
                <BacktestWarningBar
                  warnings={output.warnings}
                  showPriceReturnNote
                  showFeeFreeNote
                />

                {/* 指标卡片 */}
                <BacktestMetrics summary={output.summary} />

                {/* 图表 Tab */}
                <Card size="small" style={{ marginBottom: 12 }}>
                  <Tabs
                    defaultActiveKey="kline"
                    items={[
                      {
                        key: 'kline',
                        label: 'K线图',
                        children: (
                          <BacktestChart
                            bars={bars}
                            trades={output.trades}
                            height={400}
                            focusTrade={focusTrade}
                          />
                        ),
                      },
                      {
                        key: 'equity',
                        label: '资金曲线',
                        children: (
                          <>
                            <BacktestEquityCurve
                              equityCurve={output.equityCurve}
                              initialCapital={100000}
                              height={300}
                            />
                            <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                              左轴：净值金额 &nbsp;|&nbsp; 右轴：收益率%
                            </Text>
                          </>
                        ),
                      },
                    ]}
                  />
                </Card>

                {/* 交易明细 */}
                <Collapse
                  ghost
                  size="small"
                  items={[
                    {
                      key: 'trades',
                      label: `交易明细 (${output.trades.filter((t) => t.direction !== 'buy').length} 笔)`,
                      children: (
                        <BacktestTradeLog
                          trades={output.trades}
                          onTradeClick={handleTradeClick}
                        />
                      ),
                    },
                  ]}
                />

                {/* 诊断报告 */}
                <Collapse
                  ghost
                  size="small"
                  items={[
                    {
                      key: 'diagnostics',
                      label: `诊断报告 (${output.diagnostics?.length || 0} 条)`,
                      children: <BacktestDiagnostics diagnostics={output.diagnostics} />,
                    },
                  ]}
                />

                <Divider />

                {/* 清空缓存 */}
                <Button
                  size="small"
                  icon={<ClearOutlined />}
                  onClick={handleClearCache}
                  danger
                  ghost
                >
                  清空本地缓存
                </Button>
              </BacktestErrorBoundary>
            )}

            {!output && !universeResults && !isRunning && (
              <div className="flex items-center justify-center h-[300px] rounded bg-bg-panel border border-border-color text-text-secondary">
                <span>请在左侧配置策略后点击"开始回测"</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BacktestView;