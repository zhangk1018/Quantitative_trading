/**
 * diary.ts — 交易日记 API
 */
import { apiGet, apiPost, apiPut, apiDelete } from './client';
import { API_PREFIX } from '@/config/constants';
import type { TradingDiary, TradingDiaryFormData } from '../types';

const BASE = API_PREFIX;

/** 获取交易日记列表 */
export async function fetchDiaries(params: {
  record_id?: number;
  cycle_id?: number;
  page?: number;
  page_size?: number;
}): Promise<{ items: TradingDiary[]; total: number; page: number; page_size: number }> {
  return apiGet<{ items: TradingDiary[]; total: number; page: number; page_size: number }>(`${BASE}/diaries`, { params });
}

/** 新增交易日记 */
export async function createDiary(diary: TradingDiaryFormData): Promise<TradingDiary> {
  return apiPost<TradingDiary>(`${BASE}/diaries`, diary);
}

/** 更新交易日记 */
export async function updateDiary(id: number, diary: Partial<TradingDiaryFormData>): Promise<TradingDiary> {
  return apiPut<TradingDiary>(`${BASE}/diaries/${id}`, diary);
}

/** 删除交易日记（软删除，协作单 [27.0]） */
export async function deleteDiary(id: number): Promise<void> {
  return apiDelete<void>(`${BASE}/diaries/${id}`);
}

/** 上传日记附件 */
export async function uploadDiaryAttachment(id: number, file: File): Promise<{ file_path: string }> {
  const formData = new FormData();
  formData.append('file', file);
  return apiPost<{ file_path: string }>(`${BASE}/diaries/${id}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}