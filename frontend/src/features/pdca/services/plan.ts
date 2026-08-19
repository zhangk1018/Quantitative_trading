/**
 * plan.ts — 交易计划 & 标的 ABC 分类 API
 */
import { apiGet, apiPost, apiPut, apiDelete } from './client';
import { createEntityService } from './factory';
import { API_PREFIX } from '@/config/constants';
import type { TradingPlan, TradingPlanFormData, PlanTemplate, SecurityTag, ListData } from '../types';

const BASE = API_PREFIX;

// ── 交易计划 ──
export const planApi = createEntityService<TradingPlan, TradingPlanFormData>('/plans');

/** 获取交易计划列表（支持分页/筛选） */
export async function fetchPlans(params?: {
  cycle_id?: number;
  code?: string;
  page?: number;
  page_size?: number;
}): Promise<{ items: TradingPlan[]; total: number; page: number; page_size: number }> {
  return apiGet(`${BASE}/plans`, { params });
}

/** 创建交易计划 */
export async function createPlan(payload: TradingPlanFormData): Promise<{ id: number }> {
  return apiPost(`${BASE}/plans`, payload);
}

/** 更新交易计划 */
export async function updatePlan(id: number, payload: Partial<TradingPlanFormData>): Promise<void> {
  await apiPut(`${BASE}/plans/${id}`, payload);
}

/** 删除交易计划 */
export async function deletePlan(id: number): Promise<void> {
  await apiDelete(`${BASE}/plans/${id}`);
}

/** 获取交易计划模板列表 */
export async function fetchPlanTemplates(): Promise<PlanTemplate[]> {
  const result = await apiGet<ListData<PlanTemplate>>(`${BASE}/plans/templates`);
  return result.items;
}

// ── 标的 ABC 分类 ──

/** 获取 ABC 分类列表 */
export async function fetchSecurities(params?: { tag?: string }): Promise<SecurityTag[]> {
  const result = await apiGet<ListData<SecurityTag>>(`${BASE}/securities`, { params });
  return result.items;
}

/** 新增或覆盖 ABC 分类 */
export async function upsertSecurity(payload: {
  code: string;
  security_name?: string | null;
  tag: string;
  note?: string | null;
}): Promise<number> {
  const result = await apiPost<{ id: number }>(`${BASE}/securities`, payload);
  return result.id;
}

/** 更新 ABC 分类 */
export async function updateSecurity(
  id: number,
  payload: { security_name?: string | null; tag: string; note?: string | null },
): Promise<void> {
  await apiPut(`${BASE}/securities/${id}`, payload);
}

/** 删除 ABC 分类 */
export async function deleteSecurity(id: number): Promise<void> {
  await apiDelete(`${BASE}/securities/${id}`);
}