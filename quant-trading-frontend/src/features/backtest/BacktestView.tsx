// BacktestView.tsx — 回测分析主容器

import React, { useState, useCallback, useRef } from 'react';
import { Card, Progress, Tabs, Collapse, Button, message, Divider, Typography, Form } from 'antd';
import { ClearOutlined, PlayCircleOutlined, ReloadOutlined, LoadingOutlined } from '@ant-design/icons';
import BacktestConfigPanel from './BacktestConfigPanel';
import BacktestWarningBar from './BacktestWarningBar';
import BacktestMetrics from './BacktestMetrics';
import BacktestChart from './BacktestChart';
import BacktestEquityCurve from './BacktestEquityCurve';
import BacktestTradeLog from './BacktestTradeLog';
import BacktestDiagnostics from './BacktestDiagnostics';
import { saveResult, clearAllResults } from './backtestStorage';
import { fetchKLineData } from '../stock-detail/api';
import { useBacktestWorker } from './hooks/useBacktestWorker';
import type { KlineBar } from '../../lib/indicators/indicators';
import type {
  BacktestConfig,
  BacktestFormValues,
  BacktestOutput,
  BacktestInput,
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
  /** 当前回测的配置引用（Worker 回调中需要访问 config） */
  const configRef = useRef<BacktestConfig | null>(null);
  /** AbortController 引用，用于取消进行中的网络请求 */
  const abortRef = useRef<AbortController | null>(null);

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

  const { start: startWorker, cancel: cancelWorker, isRunning } = useBacktestWorker({
    onProgress: handleWorkerProgress,
    onResult: handleWorkerResult,
    onError: handleWorkerError,
  });

  const handleReset = useCallback(() => {
    cancelWorker();
    abortRef.current?.abort();
    setProgress(null);
    setOutput(null);
    setBars([]);
    setFocusTrade(null);
    configRef.current = null;
    form.resetFields();
  }, [cancelWorker, form]);

  const handleStart = useCallback(async (config: BacktestConfig) => {
    // 取消上一次可能未完成的请求和 Worker
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    configRef.current = config;
    setOutput(null);
    setProgress({ stage: 'fetching', percent: 0, message: '正在获取K线数据...' });

    try {
      // 1. 拉取K线数据（前复权，包含预热期）
      const fetchStart = new Date(config.startDate);
      fetchStart.setDate(fetchStart.getDate() - PREHEAT_DAYS);
      const fetchStartStr = fetchStart.toISOString().slice(0, 10);

      const klineResult = await fetchKLineData(config.stockCode, {
        adj: 'forward',
        start_date: fetchStartStr,
        end_date: config.endDate,
        limit: KLINE_FETCH_LIMIT,
      }, controller.signal);

      const items = klineResult.items;
      if (!items || items.length === 0) {
        message.error('未获取到K线数据');
        return;
      }

      // 检查数据范围是否覆盖用户请求的起始日期
      const firstBarDate = items[0].time;
      const daysDiff = Math.floor(
        (new Date(firstBarDate).getTime() - new Date(config.startDate).getTime()) / (1000 * 60 * 60 * 24)
      );

      if (daysDiff > 30) {
        message.warning(
          `数据范围提示：您选择的起始日期为 ${config.startDate}，但系统最早的数据为 ${firstBarDate}。回测将从 ${firstBarDate} 开始。`,
          8,
        );
      }

      const klineBars: KlineBar[] = klineResult.items.map((item: any) => ({
        time: item.time,
        open: Number(item.open),
        high: Number(item.high),
        low: Number(item.low),
        close: Number(item.close),
        volume: Number(item.volume),
      }));

      setBars(klineBars);

      // 2. 启动 Web Worker 计算
      const input: BacktestInput = {
        bars: klineBars,
        buyCondition: config.buyCondition,
        config: {
          stockCode: config.stockCode,
          startDate: config.startDate,
          endDate: config.endDate,
          capital: config.capital,
          feeRate: config.feeRate,
          slippage: config.slippage,
          riskFreeRate: config.riskFreeRate,
          executionPrice: config.executionPrice,
          maxDeferDays: config.maxDeferDays,
          indicatorParams: config.indicatorParams,
        },
      };

      startWorker(input);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      message.error(`数据拉取失败: ${msg}`);
    }
  }, [startWorker]);

  const handleCancel = useCallback(() => {
    cancelWorker();
    abortRef.current?.abort();
    setProgress(null);
  }, [cancelWorker]);

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

            {!output && !isRunning && (
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