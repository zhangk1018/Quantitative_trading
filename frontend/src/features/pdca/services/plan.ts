/**
 * plan.ts — 交易计划 & 标的 ABC 分类 API
 */
import client from './client';
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
  return client.get(`${BASE}/plans`, { params });
}

/** 创建交易计划 */
export async function createPlan(payload: TradingPlanFormData): Promise<{ id: number }> {
  return client.post(`${BASE}/plans`, payload);
}

/** 更新交易计划 */
export async function updatePlan(id: number, payload: Partial<TradingPlanFormData>): Promise<void> {
  await client.put(`${BASE}/plans/${id}`, payload);
}

/** 删除交易计划 */
export async function deletePlan(id: number): Promise<void> {
  await client.delete(`${BASE}/plans/${id}`);
}

/** 获取交易计划模板列表 */
export async function fetchPlanTemplates(): Promise<PlanTemplate[]> {
  const { data } = await client.get<ListData<PlanTemplate>>(`${BASE}/plans/templates`);
  return data.items;
}

// ── 标的 ABC 分类 ──

/** 获取 ABC 分类列表 */
export async function fetchSecurities(params?: { tag?: string }): Promise<SecurityTag[]> {
  const { data } = await client.get<ListData<SecurityTag>>(`${BASE}/securities`, { params });
  return data.items;
}

/** 新增或覆盖 ABC 分类 */
export async function upsertSecurity(payload: {
  code: string;
  security_name?: string | null;
  tag: string;
  note?: string | null;
}): Promise<number> {
  const result = await client.post(`${BASE}/securities`, payload);
  return (result as unknown as { id: number }).id;
}

/** 更新 ABC 分类 */
export async function updateSecurity(
  id: number,
  payload: { security_name?: string | null; tag: string; note?: string | null },
): Promise<void> {
  await client.put(`${BASE}/securities/${id}`, payload);
}

/** 删除 ABC 分类 */
export async function deleteSecurity(id: number): Promise<void> {
  await client.delete(`${BASE}/securities/${id}`);
}