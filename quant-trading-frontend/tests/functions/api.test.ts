/**
 * fetchKLineData 单元测试
 *
 * 覆盖：
 * - 返回 KLineDataResult 结构（items + patternMarkers）
 * - pattern_markers 正确解析
 * - 响应中无 pattern_markers 时返回空数组
 * - 错误响应（HTTP 500）
 * - 取消请求
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fetchKLineData } from '@/features/stock-detail/api';
import { server } from '../mocks/server';

describe('fetchKLineData', () => {
  afterEach(() => {
    // 每个测试后重置 MSW handlers（setup.ts 中的 afterEach 已做，这里显式保留备查）
  });

  // ==================== 正常响应 ====================

  it('返回 KLineDataResult 结构（items + patternMarkers）', async () => {
    const result = await fetchKLineData('600036', { limit: 5 });

    expect(result).toBeDefined();
    expect(result).toHaveProperty('items');
    expect(result).toHaveProperty('patternMarkers');
    expect(Array.isArray(result.items)).toBe(true);
    expect(Array.isArray(result.patternMarkers)).toBe(true);
  });

  it('items 为有效的 KLineItem 数组', async () => {
    const result = await fetchKLineData('600036', { limit: 5 });

    expect(result.items.length).toBeGreaterThan(0);
    for (const item of result.items) {
      expect(item).toHaveProperty('time');
      expect(item).toHaveProperty('open');
      expect(item).toHaveProperty('high');
      expect(item).toHaveProperty('low');
      expect(item).toHaveProperty('close');
      expect(item).toHaveProperty('volume');
      expect(typeof item.open).toBe('number');
      expect(typeof item.close).toBe('number');
      expect(isNaN(item.open)).toBe(false);
    }
  });

  it('pattern_markers 正确解析', async () => {
    const result = await fetchKLineData('600036', { limit: 5 });

    expect(result.patternMarkers.length).toBeGreaterThan(0);
    const first = result.patternMarkers[0];
    expect(first).toHaveProperty('date');
    expect(first).toHaveProperty('patterns');
    expect(Array.isArray(first.patterns)).toBe(true);
    expect(first.patterns.length).toBeGreaterThan(0);
  });

  it('pattern_markers 中的日期格式为 YYYY-MM-DD', async () => {
    const result = await fetchKLineData('600036', { limit: 5 });
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;

    for (const pm of result.patternMarkers) {
      expect(pm.date).toMatch(dateRegex);
    }
  });

  it('patterns 数组中的形态名符合预期', async () => {
    const result = await fetchKLineData('600036', { limit: 5 });
    const validPatterns = ['hammer', 'morning_star', 'evening_star', 'bullish_engulfing', 'bearish_engulfing'];

    for (const pm of result.patternMarkers) {
      for (const pattern of pm.patterns) {
        expect(validPatterns).toContain(pattern);
      }
    }
  });

  it('limit 参数生效', async () => {
    const result = await fetchKLineData('600036', { limit: 3 });

    expect(result.items.length).toBeGreaterThan(0);
    expect(result.items.length).toBeLessThanOrEqual(3);
  });

  it('支持字符串 period 参数', async () => {
    const result = await fetchKLineData('600036', 'daily');

    expect(result.items.length).toBeGreaterThan(0);
  });

  // ==================== 降级场景 ====================

  it('响应中无 pattern_markers 字段时返回空数组', async () => {
    // 重载 MSW handler：返回不含 pattern_markers 的响应
    server.use(
      http.get('/api/kline/:code', ({ request }) => {
        const url = new URL(request.url);
        const code = url.pathname.split('/').pop() ?? '600036';
        return HttpResponse.json({
          stock_code: code,
          data: [{ trade_date: '2026-07-01', open: '35.00', high: '35.80', low: '34.90', close: '35.50', volume: '1000000', amount: '35000000' }],
          count: 1,
          adj_method: 'forward',
          // 故意不返回 pattern_markers 字段
        });
      }),
    );

    const result = await fetchKLineData('600036', { limit: 5 });
    expect(result.patternMarkers).toEqual([]);
  });

  // ==================== 错误场景 ====================

  it('HTTP 500 时抛出异常', async () => {
    server.use(
      http.get('/api/kline/:code', () => {
        return HttpResponse.json(
          { code: 500, message: '服务器内部错误', data: null },
          { status: 500 },
        );
      }),
    );

    await expect(
      fetchKLineData('600036', { limit: 5 }),
    ).rejects.toThrow();
  });

  it('取消请求时抛出异常', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      fetchKLineData('600036', { limit: 5 }, controller.signal),
    ).rejects.toThrow();
  });
});
