/**
 * snapshot.ts — 资金快照 & 资金曲线 API
 */
import client from './client';
import { API_PREFIX } from '@/config/constants';
import type { AccountSnapshot, AccountSnapshotFormData, EquityCurveAutoPoint, ListData } from '../types';

const BASE = API_PREFIX;

/** 获取资金记录列表 */
export async function fetchSnapshots(params?: { date_from?: string; date_to?: string }): Promise<AccountSnapshot[]> {
  const { data } = await client.get<ListData<AccountSnapshot>>(`${BASE}/snapshots`, { params });
  return data.items;
}

/** 新增资金记录 */
export async function saveSnapshot(snapshot: AccountSnapshotFormData): Promise<AccountSnapshot> {
  return client.post(`${BASE}/snapshots`, snapshot);
}

/** 更新资金记录 */
export async function updateSnapshot(id: number, snapshot: AccountSnapshotFormData): Promise<void> {
  await client.put(`${BASE}/snapshots/${id}`, snapshot);
}

/** 删除资金记录 */
export async function deleteSnapshot(id: number): Promise<void> {
  await client.delete(`${BASE}/snapshots/${id}`);
}

/** 获取自动计算净值曲线 */
export async function fetchEquityAutoCurve(): Promise<EquityCurveAutoPoint[]> {
  const { data } = await client.get<ListData<EquityCurveAutoPoint>>(`${BASE}/snapshots/curve-auto`);
  return data.items;
}