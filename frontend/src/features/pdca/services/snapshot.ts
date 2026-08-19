/**
 * snapshot.ts — 资金快照 & 资金曲线 API
 */
import { apiGet, apiPost, apiPut, apiDelete } from './client';
import { API_PREFIX } from '@/config/constants';
import type { AccountSnapshot, AccountSnapshotFormData, EquityCurveAutoPoint, ListData } from '../types';

const BASE = API_PREFIX;

/** 获取资金记录列表 */
export async function fetchSnapshots(params?: { date_from?: string; date_to?: string }): Promise<AccountSnapshot[]> {
  const result = await apiGet<ListData<AccountSnapshot>>(`${BASE}/snapshots`, { params });
  return result.items;
}

/** 新增资金记录 */
export async function saveSnapshot(snapshot: AccountSnapshotFormData): Promise<AccountSnapshot> {
  return apiPost<AccountSnapshot>(`${BASE}/snapshots`, snapshot);
}

/** 更新资金记录 */
export async function updateSnapshot(id: number, snapshot: AccountSnapshotFormData): Promise<void> {
  await apiPut(`${BASE}/snapshots/${id}`, snapshot);
}

/** 删除资金记录 */
export async function deleteSnapshot(id: number): Promise<void> {
  await apiDelete(`${BASE}/snapshots/${id}`);
}

/** 获取自动计算净值曲线 */
export async function fetchEquityAutoCurve(): Promise<EquityCurveAutoPoint[]> {
  const result = await apiGet<ListData<EquityCurveAutoPoint>>(`${BASE}/snapshots/curve-auto`);
  return result.items;
}