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
import { saveResult, getAllResults, clearAllResults } from './backtestStorage';
import { fetchKLineData } from '../stock-detail/api';
import type { KlineBar } from '../../lib/indicators/indicators';
import type {
  BacktestConfig,
  BacktestOutput,
  BacktestInput,
  ProgressInfo,
  Trade,
  StoredBacktestResult,
} from './backtestTypes';

const { Text } = Typography;

const BacktestView: React.FC = () => {
  const [form] = Form.useForm<BacktestConfig>();
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [output, setOutput] = useState<BacktestOutput | null>(null);
  const [bars, setBars] = useState<KlineBar[]>([]);
  const [focusTrade, setFocusTrade] = useState<Trade | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const abortRef = useRef(false);

  // 清理 Worker
  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  const handleReset = useCallback(() => {
    // 取消正在进行的回测
    abortRef.current = true;
    workerRef.current?.terminate();
    workerRef.current = null;
    setLoading(false);
    setProgress(null);
    setOutput(null);
    setBars([]);
    setFocusTrade(null);
    // 重置表单
    form.resetFields();
  }, [form]);

  const handleStart = useCallback(async (config: BacktestConfig) => {
    setLoading(true);
    setOutput(null);
    setProgress({ stage: 'fetching', percent: 0, message: '正在获取K线数据...' });
    abortRef.current = false;

    try {
      // 1. 拉取K线数据（前复权，包含预热期）
      const preheatDays = 60;
      const fetchStart = new Date(config.startDate);
      fetchStart.setDate(fetchStart.getDate() - preheatDays);
      const fetchStartStr = fetchStart.toISOString().slice(0, 10);

      const klineResult = await fetchKLineData(config.stockCode, {
        adj: 'forward',
        start_date: fetchStartStr,
        end_date: config.endDate,
      });

      if (abortRef.current) return;

      const items = klineResult.items;
      if (!items || items.length === 0) {
        message.error('未获取到K线数据');
        setLoading(false);
        return;
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
        buyConditions: config.buyConditions,
        config: {
          stockCode: config.stockCode,          // 新增：传递股票代码
          capital: config.capital,
          feeRate: config.feeRate,
          slippage: config.slippage,
          riskFreeRate: config.riskFreeRate,
          executionPrice: config.executionPrice,
          signalConfirmBars: config.signalConfirmBars,
          maxDeferDays: config.maxDeferDays,
          indicatorParams: config.indicatorParams,
        },
      };

      const worker = new Worker(
        new URL('./backtest.worker.ts', import.meta.url),
        { type: 'module' },
      );
      workerRef.current = worker;

      worker.onmessage = (e) => {
        if (abortRef.current) {
          worker.terminate();
          return;
        }

        const { type, data } = e.data;
        if (type === 'progress') {
          setProgress(data as ProgressInfo);
        } else if (type === 'result') {
          const result = data as BacktestOutput;
          setOutput(result);
          setProgress({ stage: 'done', percent: 100, message: '回测完成' });
          setLoading(false);

          // 保存到 IndexedDB
          const stored: StoredBacktestResult = {
            id: `${config.stockCode}_${Date.now()}`,
            createdAt: new Date().toISOString(),
            config,
            output: result,
          };
          saveResult(stored).catch(() => {});

          worker.terminate();
        } else if (type === 'error') {
          message.error(`回测失败: ${data}`);
          setLoading(false);
          worker.terminate();
        }
      };

      worker.onerror = (err) => {
        message.error('Worker 异常崩溃');
        setLoading(false);
        worker.terminate();
      };

      worker.postMessage({ type: 'run', input });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(`数据拉取失败: ${msg}`);
      setLoading(false);
    }
  }, []);

  const handleCancel = useCallback(() => {
    abortRef.current = true;
    workerRef.current?.terminate();
    workerRef.current = null;
    setLoading(false);
    setProgress(null);
  }, []);

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
        {/* 左侧配置面板 — 参照选股视图侧边栏设计 */}
        <div
          className="w-[280px] flex-shrink-0 bg-bg-panel border-r border-border-color flex flex-col h-full"
        >
          <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0">
            <BacktestConfigPanel
              onStart={handleStart}
              loading={loading}
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
                  loading ? 'bg-color-accent/60 cursor-not-allowed' : 'bg-color-accent hover:bg-color-accent/80'
                }`}
                icon={loading ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
                onClick={() => form.submit()}
                disabled={loading}
              >
                {loading ? '计算中...' : '开始回测'}
              </Button>
              {loading ? (
                <Button
                  onClick={handleCancel}
                  danger
                  className="flex-1"
                >
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
            {loading && progress && (
              <Card size="small" className="!bg-bg-panel !border-border-color !mb-3">
                <Progress
                  percent={progress.percent}
                  status="active"
                  strokeColor="#2962FF"
                />
                <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {progress.message}
                </Text>
              </Card>
            )}

            {output && (
              <>
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
              </>
            )}

            {!output && !loading && (
              <div
                className="flex items-center justify-center h-[300px] rounded
                           bg-bg-panel border border-border-color text-text-secondary"
              >
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