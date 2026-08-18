/**
 * record.ts — 交易台账 & 卖出子单 & 日线行情 API
 */
import client from './client';
import { createEntityService } from './factory';
import { API_PREFIX } from '@/config/constants';
import type {
  TradingRecord,
  TradingRecordFormData,
  ExitSlip,
  ExitSlipFormData,
  ListData,
} from '../types';

const BASE = API_PREFIX;

// ── 基础 CRUD（复用工厂） ──
export const recordApi = createEntityService<TradingRecord, TradingRecordFormData>('/records');

// ── 命名别名（兼容旧 import） ──
export const createRecord = (data: TradingRecordFormData) => recordApi.create(data);
export const updateRecord = (id: number, data: Partial<TradingRecordFormData>) => recordApi.update(id, data);
export const deleteRecord = (id: number) => recordApi.delete(id);

// ── 自定义接口 ──

/** 获取交易记录（支持分页/筛选） */
export async function fetchRecords(params: {
  page?: number;
  page_size?: number;
  code?: string;
  entry_date_from?: string;
  entry_date_to?: string;
  cycle_id?: number;
  sort_by?: string;
  sort_asc?: boolean;
}): Promise<{ items: TradingRecord[]; total: number; page: number; page_size: number }> {
  return client.get(`${BASE}/records`, { params });
}

/** 获取买入单的所有卖出子单 */
export async function fetchExitSlips(recordId: number): Promise<ExitSlip[]> {
  const { data } = await client.get<ListData<ExitSlip>>(`${BASE}/records/${recordId}/exit-slips`);
  return data.items;
}

/** 批量新增卖出子单 */
export async function batchCreateExitSlips(
  recordId: number,
  slips: ExitSlipFormData[],
): Promise<{ record_id: number; remain_qty: number; gross_profit: number }> {
  return client.post(`${BASE}/records/${recordId}/exit-slips/batch`, { slips });
}

/** 更新卖出子单 */
export async function updateExitSlip(slipId: number, payload: Partial<ExitSlipFormData>): Promise<void> {
  await client.put(`${BASE}/exit-slips/${slipId}`, payload);
}

/** 删除卖出子单 */
export async function deleteExitSlip(slipId: number): Promise<void> {
  await client.delete(`${BASE}/exit-slips/${slipId}`);
}

// ── 日线行情（用于自动计算得分） ──

export interface DailyOHLC {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

/**
 * 查询股票在指定交易日的 OHLC 数据
 */
export async function fetchDailyOHLC(code: string, date: string): Promise<DailyOHLC | null> {
  try {
    const data: unknown = await client.get(`${BASE}/kline/${code}`, {
      params: { period: 'daily', start_date: date, end_date: date, limit: 1, adj: 'none' },
    });
    const arr = (data as { data?: unknown[] }).data;
    if (arr && arr.length > 0) {
      const item = arr[0] as Record<string, unknown>;
      return {
        trade_date: String(item.trade_date ?? ''),
        open: Number(item.open ?? 0),
        high: Number(item.high ?? 0),
        low: Number(item.low ?? 0),
        close: Number(item.close ?? 0),
      };
    }
    return null;
  } catch {
    return null;
  }
}