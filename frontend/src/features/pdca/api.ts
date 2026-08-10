/** PDCA 交易自律系统 — API 调用封装 */

import axios from 'axios';
import type {
  ApiResponse,
  PaginatedData,
  TradingRecord,
  TradingRecordFormData,
  TradingDiary,
  TradingDiaryFormData,
  AccountSnapshot,
  AccountSnapshotFormData,
  CapitalCurvePoint,
  SystemConfigItem,
  StockSearchResult,
  PDCACycle,
  BrokerAdapter,
  ImportParseResult,
} from './types';

const BASE = '/api/pdca';

// ============================================================
// 交易台账 CRUD
// ============================================================

/** 获取交易记录列表 */
export async function fetchRecords(params: {
  page?: number;
  page_size?: number;
  code?: string;
  entry_date_from?: string;
  entry_date_to?: string;
  cycle_id?: number;
  sort_by?: string;
  sort_asc?: boolean;
}): Promise<ApiResponse<PaginatedData<TradingRecord>>> {
  const { data } = await axios.get(`${BASE}/records`, { params });
  return data;
}

/** 新增交易记录 */
export async function createRecord(
  record: TradingRecordFormData,
): Promise<ApiResponse<TradingRecord>> {
  const { data } = await axios.post(`${BASE}/records`, record);
  return data;
}

/** 更新交易记录 */
export async function updateRecord(
  id: number,
  record: Partial<TradingRecordFormData>,
): Promise<ApiResponse<TradingRecord>> {
  const { data } = await axios.put(`${BASE}/records/${id}`, record);
  return data;
}

/** 软删除交易记录 */
export async function deleteRecord(id: number): Promise<ApiResponse<null>> {
  const { data } = await axios.delete(`${BASE}/records/${id}`);
  return data;
}

// ============================================================
// 资金快照 & 资金曲线
// ============================================================

/** 获取资金快照列表 */
export async function fetchSnapshots(params: {
  date_from?: string;
  date_to?: string;
}): Promise<ApiResponse<AccountSnapshot[]>> {
  const { data } = await axios.get(`${BASE}/snapshots`, { params });
  return data;
}

/** 新增/更新资金快照 */
export async function saveSnapshot(
  snapshot: AccountSnapshotFormData,
): Promise<ApiResponse<AccountSnapshot>> {
  const { data } = await axios.post(`${BASE}/snapshots`, snapshot);
  return data;
}

/** 获取资金曲线数据 */
export async function fetchCapitalCurve(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ApiResponse<CapitalCurvePoint[]>> {
  const { data } = await axios.get(`${BASE}/snapshots/curve`, { params });
  return data;
}

// ============================================================
// 交易日记
// ============================================================

/** 获取交易日记列表 */
export async function fetchDiaries(params: {
  record_id?: number;
  cycle_id?: number;
}): Promise<ApiResponse<TradingDiary[]>> {
  const { data } = await axios.get(`${BASE}/diaries/`, { params });
  return data;
}

/** 新增交易日记 */
export async function createDiary(
  diary: TradingDiaryFormData,
): Promise<ApiResponse<TradingDiary>> {
  const { data } = await axios.post(`${BASE}/diaries/`, diary);
  return data;
}

/** 更新交易日记 */
export async function updateDiary(
  id: number,
  diary: Partial<TradingDiaryFormData>,
): Promise<ApiResponse<TradingDiary>> {
  const { data } = await axios.put(`${BASE}/diaries/${id}`, diary);
  return data;
}

/** 上传日记附件 */
export async function uploadDiaryAttachment(
  id: number,
  file: File,
): Promise<ApiResponse<{ file_path: string }>> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await axios.post(`${BASE}/diaries/${id}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

// ============================================================
// 系统配置
// ============================================================

/** 获取系统配置 */
export async function fetchConfig(): Promise<ApiResponse<SystemConfigItem[]>> {
  const { data } = await axios.get(`${BASE}/config`);
  return data;
}

/** 更新系统配置 */
export async function updateConfig(
  configKey: string,
  updates: { config_value?: string; numeric_value?: number; bool_value?: boolean; modify_reason: string },
): Promise<ApiResponse<SystemConfigItem>> {
  const { data } = await axios.put(`${BASE}/config`, {
    config_key: configKey,
    ...updates,
  });
  return data;
}

// ============================================================
// Excel 导入导出
// ============================================================

/** 解析券商 Excel */
export async function parseImportExcel(
  file: File,
  brokerName: string,
): Promise<ApiResponse<ImportParseResult>> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('broker_name', brokerName);
  const { data } = await axios.post(`${BASE}/import/parse`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

/** 确认导入解析后的数据 */
export async function confirmImport(
  records: TradingRecordFormData[],
): Promise<ApiResponse<{ imported: number }>> {
  const { data } = await axios.post(`${BASE}/import/confirm`, { records });
  return data;
}

/** 导出台账为 Excel */
export async function exportRecords(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<Blob> {
  const { data } = await axios.get(`${BASE}/export`, {
    params,
    responseType: 'blob',
  });
  return data;
}

/** 全量备份 */
export async function backupDatabase(): Promise<Blob> {
  const { data } = await axios.get(`${BASE}/backup`, {
    responseType: 'blob',
  });
  return data;
}

// ============================================================
// 股票搜索
// ============================================================

/** 搜索股票代码 */
export async function searchStocks(q: string): Promise<ApiResponse<StockSearchResult[]>> {
  const { data } = await axios.get(`${BASE}/stocks/search`, { params: { q } });
  return data;
}

// ============================================================
// 券商适配器
// ============================================================

/** 获取可用券商适配器列表 */
export async function fetchBrokerAdapters(): Promise<ApiResponse<BrokerAdapter[]>> {
  const { data } = await axios.get(`${BASE}/import/brokers`);
  return data;
}

// ============================================================
// PDCA 周期
// ============================================================

/** 获取 PDCA 周期列表 */
export async function fetchCycles(params?: {
  status?: string;
}): Promise<ApiResponse<PDCACycle[]>> {
  const { data } = await axios.get(`${BASE}/cycles`, { params });
  return data;
}