/**
 * act-record.ts — 迭代处理记录 API
 */
import { apiGet, apiPost, apiPut, apiDelete } from './client';
import { API_PREFIX } from '@/config/constants';
import type { ActRecord, ActRecordFormData, ListData } from '../types';

const BASE = API_PREFIX;

/** 获取指定周期的所有迭代处理记录 */
export async function fetchActRecords(cycleId: number): Promise<ActRecord[]> {
  const result = await apiGet<ListData<ActRecord>>(`${BASE}/act-records/${cycleId}`);
  return result.items;
}

/** 创建迭代处理记录 */
export async function createActRecord(payload: ActRecordFormData): Promise<{ id: number }> {
  return apiPost<{ id: number }>(`${BASE}/act-records`, payload);
}

/** 更新迭代处理记录 */
export async function updateActRecord(id: number, payload: Partial<ActRecordFormData>): Promise<{ id: number }> {
  return apiPut<{ id: number }>(`${BASE}/act-records/${id}`, payload);
}

/** 删除迭代处理记录 */
export async function deleteActRecord(id: number): Promise<void> {
  await apiDelete(`${BASE}/act-records/${id}`);
}