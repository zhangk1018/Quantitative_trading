/**
 * cycle.ts — PDCA 周期 & 执行跟踪 API
 */
import { apiGet, apiPost, apiPut, apiDelete } from './client';
import { API_PREFIX } from '@/config/constants';
import type { PDCACycle, ExecutionSummary, ListData } from '../types';

const BASE = API_PREFIX;

/** 获取 PDCA 周期列表 */
export async function fetchCycles(params?: {
  status?: string;
  sort_by?: string;
  sort_asc?: boolean;
}): Promise<PDCACycle[]> {
  const result = await apiGet<ListData<PDCACycle>>(`${BASE}/cycles`, { params });
  return result.items;
}

/** 新建 PDCA 周期 */
export async function createCycle(payload: {
  cycle_name: string;
  cycle_type: string;
  start_date: string;
  end_date: string;
  goal_text?: string | null;
}): Promise<PDCACycle> {
  return apiPost<PDCACycle>(`${BASE}/cycles`, payload);
}

/** 删除 PDCA 周期（仅 PLAN 状态） */
export async function deleteCycle(id: number): Promise<void> {
  await apiDelete(`${BASE}/cycles/${id}`);
}

/** 获取周期执行跟踪摘要 */
export async function fetchExecutionSummary(cycleId: number): Promise<ExecutionSummary> {
  return apiGet<ExecutionSummary>(`${BASE}/cycles/${cycleId}/execution-summary`);
}

/** 状态流转 */
export async function transitionCycle(id: number, targetStatus: string): Promise<PDCACycle> {
  return apiPut<PDCACycle>(`${BASE}/cycles/${id}/transition`, { target_status: targetStatus });
}