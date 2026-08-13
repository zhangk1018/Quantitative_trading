/**
 * PDCA API 函数单元测试
 *
 * 覆盖：
 * - fetchRecords 正常返回分页数据
 * - fetchRecords 按代码筛选
 * - createRecord 成功创建
 * - updateRecord 成功更新
 * - deleteRecord 成功删除
 * - deleteRecord 删除不存在的记录返回 404
 * - fetchCapitalCurve 返回资金曲线
 * - fetchCycles 按状态筛选
 * - searchStocks 按关键字搜索
 * - exportRecords 返回 Blob
 * - backupDatabase 返回 Blob
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { server } from '../mocks/server';
import { pdcaHandlers, resetMockData } from '../mocks/pdcaHandlers';
import {
  fetchRecords,
  createRecord,
  updateRecord,
  deleteRecord,
  fetchCapitalCurve,
  fetchCycles,
  searchStocks,
  exportRecords,
  backupDatabase,
  fetchBrokerAdapters,
  fetchConfig,
  updateConfig,
} from '@/features/pdca/api';
import type { TradingRecordFormData } from '@/features/pdca/types';

describe('PDCA API', () => {
  beforeEach(() => {
    resetMockData();
    server.use(...pdcaHandlers);
  });

  // ── fetchRecords ──

  it('fetchRecords 返回分页数据', async () => {
    const res = await fetchRecords({ page: 1, page_size: 20 });
    expect(res.code).toBe(200);
    expect(res.data.total).toBeGreaterThan(0);
    expect(res.data.items.length).toBeGreaterThan(0);
    expect(res.data.items[0]).toHaveProperty('id');
    expect(res.data.items[0]).toHaveProperty('code');
  });

  it('fetchRecords 按代码筛选', async () => {
    const res = await fetchRecords({ page: 1, page_size: 20, code: '600036' });
    expect(res.code).toBe(200);
    expect(res.data.items.every((r) => r.code.includes('600036'))).toBe(true);
  });

  // ── createRecord ──

  it('createRecord 成功创建', async () => {
    const formData: TradingRecordFormData = {
      code: '300750',
      security_name: '宁德时代',
      instrument_type: 'stock',
      long_short: 'long',
      order_type: 'limit',
      entry_date: '2026-08-10',
      entry_price: 235.80,
      quantity: 500,
      commission_entry: 5.0,
      commission_exit: 5.0,
      slip_point: 0.01,
    };
    const res = await createRecord(formData);
    expect(res.code).toBe(200);
    expect(res.data.code).toBe('300750');
    expect(res.data.id).toBeGreaterThan(0);
  });

  // ── updateRecord ──

  it('updateRecord 成功更新', async () => {
    const res = await updateRecord(1, { exit_price: 37.00, gross_profit: 1800 });
    expect(res.code).toBe(200);
    expect(res.data.exit_price).toBe(37.00);
  });

  // ── deleteRecord ──

  it('deleteRecord 成功删除', async () => {
    const res = await deleteRecord(1);
    expect(res.code).toBe(200);
  });

  it('deleteRecord 删除不存在的记录返回错误信息', async () => {
    await expect(deleteRecord(9999)).rejects.toThrow('记录不存在');
  });

  // ── fetchCapitalCurve ──

  it('fetchCapitalCurve 返回资金曲线数据', async () => {
    const res = await fetchCapitalCurve();
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBeGreaterThan(0);
    expect(res.data.items[0]).toHaveProperty('date');
    expect(res.data.items[0]).toHaveProperty('total_asset');
    expect(res.data.items[0]).toHaveProperty('adjusted_nav');
    expect(res.data.items[0]).toHaveProperty('deposit');
    expect(res.data.items[0]).toHaveProperty('withdrawal');
    expect(res.data.items[0]).toHaveProperty('realized_pnl');
  });

  // ── fetchCycles ──

  it('fetchCycles 按状态筛选', async () => {
    const res = await fetchCycles({ status: 'DO' });
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBeGreaterThan(0);
    expect(res.data.items[0].status).toBe('DO');
  });

  it('fetchCycles 返回空列表当无匹配状态', async () => {
    const res = await fetchCycles({ status: 'CHECK' });
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBe(0);
  });

  // ── searchStocks ──

  it('searchStocks 按关键字搜索', async () => {
    const res = await searchStocks('招商');
    expect(res.code).toBe(200);
    expect(res.data.length).toBeGreaterThan(0);
    expect(res.data[0]).toHaveProperty('code');
    expect(res.data[0]).toHaveProperty('name');
  });

  // ── exportRecords ──

  it('exportRecords 返回 Blob', async () => {
    const blob = await exportRecords();
    expect(blob).toBeInstanceOf(Blob);
  });

  // ── backupDatabase ──

  it('backupDatabase 返回 Blob', async () => {
    const blob = await backupDatabase();
    expect(blob).toBeInstanceOf(Blob);
  });

  // ── fetchBrokerAdapters ──

  it('fetchBrokerAdapters 返回券商列表', async () => {
    const res = await fetchBrokerAdapters();
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBeGreaterThan(0);
    expect(res.data.items[0]).toHaveProperty('broker_name');
    expect(res.data.items[0]).toHaveProperty('display_name');
  });

  // ── fetchConfig ──

  it('fetchConfig 返回系统配置', async () => {
    const res = await fetchConfig();
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBeGreaterThan(0);
    expect(res.data.items[0]).toHaveProperty('config_key');
  });

  // ── updateConfig ──

  it('updateConfig 成功更新配置', async () => {
    const res = await updateConfig('risk_per_trade', {
      numeric_value: 3,
      modify_reason: '测试调整',
    });
    expect(res.code).toBe(200);
    expect(res.data.config_key).toBe('risk_per_trade');
  });

  // ── 错误场景 ──

  it('createRecord 缺少必填字段返回 400 错误', async () => {
    const invalidData: TradingRecordFormData = {
      code: '', security_name: '', instrument_type: 'stock', long_short: 'long', order_type: 'limit',
      entry_date: '', entry_price: 0, quantity: 0, commission_entry: 0, commission_exit: 0, slip_point: 0,
    };
    await expect(createRecord(invalidData)).rejects.toThrow('缺少必填字段');
  });

  it('updateRecord 更新不存在的记录返回 404 错误', async () => {
    await expect(updateRecord(9999, { exit_price: 37.00 })).rejects.toThrow('记录不存在');
  });

  it('fetchRecords 请求超页返回空列表', async () => {
    const res = await fetchRecords({ page: 999, page_size: 20 });
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBe(0);
    expect(res.data.total).toBe(2);
  });

  it('fetchRecords 组合筛选（代码+日期范围）', async () => {
    const res = await fetchRecords({ page: 1, page_size: 20, code: '600036', entry_date_from: '2026-08-01', entry_date_to: '2026-08-10' });
    expect(res.code).toBe(200);
    expect(res.data.items.length).toBe(1);
    expect(res.data.items[0].code).toBe('600036');
  });
});