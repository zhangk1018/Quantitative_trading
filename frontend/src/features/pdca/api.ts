/**
 * PDCA 交易自律系统 — API 调用封装
 *
 * 统一 Axios 实例：
 * - 基础路径从环境变量获取
 * - 全局请求拦截器注入 Authorization 头
 * - 全局响应拦截器统一处理错误
 * - 标准错误对象抛出
 */

import axios from 'axios';
import { downloadBlob } from '@/utils/download';
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

// Axios 实例（统一配置）
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ── 请求拦截器：注入认证头 ──
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── 响应拦截器：统一错误处理 ──
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status;
      const serverMsg = error.response?.data?.message;

      if (status === 401) {
        // 未授权：清除本地 token，可考虑跳转登录页
        localStorage.removeItem('auth_token');
      }

      // 抛出标准化错误，各组件可统一 catch 处理
      const message = serverMsg || (status === 0 ? '网络连接失败' : `请求失败 (${status || '未知'})`);
      return Promise.reject(new Error(message));
    }
    return Promise.reject(new Error('请求异常'));
  },
);

const BASE = '/pdca';

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
  const { data } = await client.get(`${BASE}/records`, { params });
  return data;
}

/** 新增交易记录 */
export async function createRecord(
  record: TradingRecordFormData,
): Promise<ApiResponse<TradingRecord>> {
  const { data } = await client.post(`${BASE}/records`, record);
  return data;
}

/** 更新交易记录 */
export async function updateRecord(
  id: number,
  record: Partial<TradingRecordFormData>,
): Promise<ApiResponse<TradingRecord>> {
  const { data } = await client.put(`${BASE}/records/${id}`, record);
  return data;
}

/** 软删除交易记录 */
export async function deleteRecord(id: number): Promise<ApiResponse<null>> {
  const { data } = await client.delete(`${BASE}/records/${id}`);
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
  const { data } = await client.get(`${BASE}/snapshots`, { params });
  return data;
}

/** 新增/更新资金快照 */
export async function saveSnapshot(
  snapshot: AccountSnapshotFormData,
): Promise<ApiResponse<AccountSnapshot>> {
  const { data } = await client.post(`${BASE}/snapshots`, snapshot);
  return data;
}

/** 获取资金曲线数据 */
export async function fetchCapitalCurve(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ApiResponse<CapitalCurvePoint[]>> {
  const { data } = await client.get(`${BASE}/snapshots/curve`, { params });
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
  const { data } = await client.get(`${BASE}/diaries`, { params });
  return data;
}

/** 新增交易日记 */
export async function createDiary(
  diary: TradingDiaryFormData,
): Promise<ApiResponse<TradingDiary>> {
  const { data } = await client.post(`${BASE}/diaries`, diary);
  return data;
}

/** 更新交易日记 */
export async function updateDiary(
  id: number,
  diary: Partial<TradingDiaryFormData>,
): Promise<ApiResponse<TradingDiary>> {
  const { data } = await client.put(`${BASE}/diaries/${id}`, diary);
  return data;
}

/** 上传日记附件 */
export async function uploadDiaryAttachment(
  id: number,
  file: File,
): Promise<ApiResponse<{ file_path: string }>> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post(`${BASE}/diaries/${id}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

// ============================================================
// 系统配置
// ============================================================

/** 获取系统配置 */
export async function fetchConfig(): Promise<ApiResponse<SystemConfigItem[]>> {
  const { data } = await client.get(`${BASE}/config`);
  return data;
}

/** 更新系统配置 */
export async function updateConfig(
  configKey: string,
  updates: {
    config_value?: string;
    numeric_value?: number;
    bool_value?: boolean;
    modify_reason: string;
  },
): Promise<ApiResponse<SystemConfigItem>> {
  const { data } = await client.put(`${BASE}/config`, {
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
  const { data } = await client.post(`${BASE}/import/parse`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

/** 确认导入解析后的数据 */
export async function confirmImport(
  records: TradingRecordFormData[],
): Promise<ApiResponse<{ imported: number }>> {
  const { data } = await client.post(`${BASE}/import/confirm`, { records });
  return data;
}

/** 导出台账为 Excel */
export async function exportRecords(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<Blob> {
  const { data } = await client.get(`${BASE}/export`, {
    params,
    responseType: 'blob',
  });
  return data;
}

/** 全量备份 */
export async function backupDatabase(): Promise<Blob> {
  const { data } = await client.get(`${BASE}/backup`, {
    responseType: 'blob',
  });
  return data;
}

// ============================================================
// 股票搜索
// ============================================================

/** 搜索股票代码 */
export async function searchStocks(
  q: string,
): Promise<ApiResponse<StockSearchResult[]>> {
  const { data } = await client.get(`${BASE}/stocks/search`, { params: { q } });
  return data;
}

// ============================================================
// 券商适配器
// ============================================================

/** 获取可用券商适配器列表 */
export async function fetchBrokerAdapters(): Promise<
  ApiResponse<BrokerAdapter[]>
> {
  const { data } = await client.get(`${BASE}/import/brokers`);
  return data;
}

// ============================================================
// PDCA 周期
// ============================================================

/** 获取 PDCA 周期列表 */
export async function fetchCycles(params?: {
  status?: string;
}): Promise<ApiResponse<PDCACycle[]>> {
  const { data } = await client.get(`${BASE}/cycles`, { params });
  return data;
}

// ============================================================
// 通用下载辅助函数
// ============================================================

/** 下载 Excel 文件 */
export async function downloadExcel(
  blobPromise: Promise<Blob>,
  prefix: string,
): Promise<void> {
  const blob = await blobPromise;
  downloadBlob(blob, `${prefix}_${new Date().toISOString().slice(0, 10)}.xlsx`);
}

/** 下载备份 SQL 文件 */
export async function downloadBackup(blobPromise: Promise<Blob>): Promise<void> {
  const blob = await blobPromise;
  downloadBlob(blob, `pdca_backup_${new Date().toISOString().slice(0, 10)}.sql`);
}