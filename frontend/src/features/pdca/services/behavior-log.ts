/**
 * behavior-log.ts — 行为 & 违规日志 API
 */
import client from './client';
import { API_PREFIX } from '@/config/constants';
import type { BehaviorLog, BehaviorLogFormData, ListData } from '../types';

const BASE = API_PREFIX;

/** 获取指定周期的行为日志列表 */
export async function fetchBehaviorLogs(
  cycleId: number,
  params?: { log_type?: string; violation_type?: string; date_from?: string; date_to?: string },
): Promise<BehaviorLog[]> {
  const { data } = await client.get<ListData<BehaviorLog>>(`${BASE}/behavior-logs/${cycleId}`, { params });
  return data.items;
}

/** 创建行为日志 */
export async function createBehaviorLog(payload: BehaviorLogFormData): Promise<{ id: number }> {
  return client.post(`${BASE}/behavior-logs`, payload);
}

/** 更新行为日志 */
export async function updateBehaviorLog(
  id: number,
  payload: Partial<Pick<BehaviorLogFormData, 'log_content' | 'violation_type' | 'severity'>>,
): Promise<{ id: number }> {
  return client.put(`${BASE}/behavior-logs/${id}`, payload);
}

/** 删除行为日志 */
export async function deleteBehaviorLog(id: number): Promise<void> {
  await client.delete(`${BASE}/behavior-logs/${id}`);
}

/** 获取行为日志支持的枚举类型值 */
export async function fetchBehaviorLogTypes(): Promise<{
  log_types: string[];
  violation_types: string[];
  severities: string[];
}> {
  return client.get(`${BASE}/behavior-logs/types`);
}