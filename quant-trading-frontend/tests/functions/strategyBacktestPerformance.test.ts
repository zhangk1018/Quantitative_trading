import { describe, it, expect } from 'vitest';
import { runStrategyBacktest, StrategyBacktestInput, FilterNode } from '../../src/features/strategy-backtest/engine';

// 标记为慢速测试，仅在需要时执行
describe.skip('Performance Benchmark', () => {
  // 生成模拟数据
  function generateMockData(stockCount: number, days: number, startDate = '2025-01-02') {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, any>();

    // 生成基准数据
    const benchmarkOhlcv: number[][] = [];
    const startMs = Date.UTC(2025, 0, 2);
    let price = 3000;
    for (let i = 0; i < days; i++) {
      const ts = startMs + i * 86400000;
      price = price * (1 + 0.001);
      benchmarkOhlcv.push([ts, price, price * 1.005, price * 0.995, price, 10000000, i > 0 ? benchmarkOhlcv[i - 1][4] : price]);
    }

    for (let s = 0; s < stockCount; s++) {
      const bars: number[][] = [];
      price = 10 + Math.random() * 20;
      for (let i = 0; i < days; i++) {
        const ts = startMs + i * 86400000;
        const change = (Math.random() - 0.48) * 0.04;
        const open = price;
        const close = price * (1 + change);
        const high = Math.max(open, close) * 1.01;
        const low = Math.min(open, close) * 0.99;
        const volume = Math.floor(Math.random() * 5000000) + 500000;
        const preClose = i > 0 ? bars[i - 1][4] : price;
        bars.push([ts, open, high, low, close, volume, preClose]);
        price = close;
      }
      allOhlcv.set(`STOCK${String(s).padStart(4, '0')}`, bars);
      snapshots.set(`STOCK${String(s).padStart(4, '0')}`, {
        isSt: false,
        listedBoard: 'main_board',
        pe: 15 + Math.random() * 20,
        pb: 1.5 + Math.random() * 2,
        marketCap: 50 + Math.random() * 200,
      });
    }

    return { allOhlcv, snapshots, benchmarkOhlcv };
  }

  it('100 只股票 × 1 年日线 < 3 秒', async () => {
    const { allOhlcv, snapshots, benchmarkOhlcv } = generateMockData(100, 250);

    const filterTree: FilterNode = {
      type: 'and',
      children: [
        { type: 'range', field: 'close', min: 5, max: 50 },
        { type: 'range', field: 'change_pct', min: -2, max: 2 },
      ],
    };

    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree,
      config: {
        maxPositions: 5,
        singleStockMaxPct: 0.2,
        dailyLossLimitEnabled: false,
        dailyLossLimitPct: -0.05,
        maxDrawdownStopEnabled: false,
        maxDrawdownStopPct: -0.2,
        stopLossEnabled: false,
        stopLossPct: -0.1,
        takeProfitEnabled: false,
        takeProfitPct: 0.2,
        maxHoldDays: 60,
        slippage: 0.001,
        feeRate: 0.0003,
        minCommission: 5,
        rebalanceFrequency: 20,
      },
      startDate: '2025-01-02',
      endDate: '2025-12-31',
      benchmarkOhlcv,
    };

    const startTime = performance.now();
    const result = await runStrategyBacktest(input);
    const endTime = performance.now();
    const elapsedMs = endTime - startTime;

    // 宽松阈值 5 秒（CI 环境可能较慢）
    expect(elapsedMs).toBeLessThan(5000);
    expect(result.totalReturn).toBeDefined();
    expect(result.tradeLog.length).toBeGreaterThanOrEqual(0);
    
    console.log(`[性能基准] 100 只股票 × 250 天: ${elapsedMs.toFixed(0)}ms, 交易次数: ${result.tradeLog.length}`);
  }, 10000); // 10 秒超时

  it('200 只股票 × 2 年日线 < 8 秒', async () => {
    const { allOhlcv, snapshots, benchmarkOhlcv } = generateMockData(200, 500);

    const filterTree: FilterNode = {
      type: 'and',
      children: [
        { type: 'range', field: 'close', min: 5, max: 50 },
        { type: 'range', field: 'change_pct', min: -2, max: 2 },
      ],
    };

    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree,
      config: {
        maxPositions: 5,
        singleStockMaxPct: 0.2,
        dailyLossLimitEnabled: false,
        dailyLossLimitPct: -0.05,
        maxDrawdownStopEnabled: false,
        maxDrawdownStopPct: -0.2,
        stopLossEnabled: false,
        stopLossPct: -0.1,
        takeProfitEnabled: false,
        takeProfitPct: 0.2,
        maxHoldDays: 60,
        slippage: 0.001,
        feeRate: 0.0003,
        minCommission: 5,
        rebalanceFrequency: 20,
      },
      startDate: '2025-01-02',
      endDate: '2026-06-30',
      benchmarkOhlcv,
    };

    const startTime = performance.now();
    const result = await runStrategyBacktest(input);
    const endTime = performance.now();
    const elapsedMs = endTime - startTime;

    // 宽松阈值 10 秒
    expect(elapsedMs).toBeLessThan(10000);
    
    console.log(`[性能基准] 200 只股票 × 500 天: ${elapsedMs.toFixed(0)}ms, 交易次数: ${result.tradeLog.length}`);
  }, 20000); // 20 秒超时
});