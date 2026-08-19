/**
 * check-report.ts — 复盘报告 API
 */
import { apiGet, apiPost, apiPut } from './client';
import { API_PREFIX } from '@/config/constants';
import type { CheckReport, CheckReportFormData } from '../types';

const BASE = API_PREFIX;

/** 获取指定周期的复盘报告 */
export async function fetchCheckReport(cycleId: number): Promise<CheckReport | null> {
  return apiGet<CheckReport | null>(`${BASE}/check-reports/${cycleId}`);
}

/** 创建/更新复盘报告 */
export async function createCheckReport(payload: CheckReportFormData): Promise<{ id: number }> {
  return apiPost<{ id: number }>(`${BASE}/check-reports`, payload);
}

/** 更新复盘报告 */
export async function updateCheckReport(id: number, payload: Partial<CheckReportFormData>): Promise<{ id: number }> {
  return apiPut<{ id: number }>(`${BASE}/check-reports/${id}`, payload);
}