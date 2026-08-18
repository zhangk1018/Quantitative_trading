/**
 * check-report.ts — 复盘报告 API
 */
import client from './client';
import { API_PREFIX } from '@/config/constants';
import type { CheckReport, CheckReportFormData } from '../types';

const BASE = API_PREFIX;

/** 获取指定周期的复盘报告 */
export async function fetchCheckReport(cycleId: number): Promise<CheckReport | null> {
  return client.get(`${BASE}/check-reports/${cycleId}`);
}

/** 创建/更新复盘报告 */
export async function createCheckReport(payload: CheckReportFormData): Promise<{ id: number }> {
  return client.post(`${BASE}/check-reports`, payload);
}

/** 更新复盘报告 */
export async function updateCheckReport(id: number, payload: Partial<CheckReportFormData>): Promise<{ id: number }> {
  return client.put(`${BASE}/check-reports/${id}`, payload);
}