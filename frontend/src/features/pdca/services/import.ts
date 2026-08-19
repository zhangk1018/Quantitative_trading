/**
 * import.ts — Excel 导入导出 & 备份 API
 */
import { apiGet, apiPost } from './client';
import { downloadBlob } from '@/utils/download';
import { API_PREFIX } from '@/config/constants';
import type { ImportParseResult, TradingRecordFormData } from '../types';

const BASE = API_PREFIX;

/** 解析券商 Excel */
export async function parseImportExcel(file: File, brokerName: string): Promise<ImportParseResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('broker_name', brokerName);
  // 使用 Axios 实例（已在 client.ts 中配置认证/超时/错误拦截）
  return apiPost<ImportParseResult>(`${BASE}/import/parse`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

/** 确认导入解析后的数据 */
export async function confirmImport(records: TradingRecordFormData[]): Promise<{ imported: number }> {
  return apiPost<{ imported: number }>(`${BASE}/import/confirm`, { records });
}

/** 导出台账为 Excel */
export async function exportRecords(params?: { date_from?: string; date_to?: string }): Promise<Blob> {
  return apiGet<Blob>(`${BASE}/export`, { params, responseType: 'blob' });
}

/** 全量备份 */
export async function backupDatabase(): Promise<Blob> {
  return apiGet<Blob>(`${BASE}/backup`, { responseType: 'blob' });
}

/** 下载 Excel 文件 */
export async function downloadExcel(blobPromise: Promise<Blob>, prefix: string): Promise<void> {
  const blob = await blobPromise;
  downloadBlob(blob, `${prefix}_${new Date().toISOString().slice(0, 10)}.xlsx`);
}

/** 下载备份 SQL 文件 */
export async function downloadBackup(blobPromise: Promise<Blob>): Promise<void> {
  const blob = await blobPromise;
  downloadBlob(blob, `pdca_backup_${new Date().toISOString().slice(0, 10)}.sql`);
}