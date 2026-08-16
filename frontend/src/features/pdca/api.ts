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
import { API_PREFIX, API_TIMEOUT, HTTP_STATUS } from '@/config/constants';
import type {
  ApiResponse,
  ListData,
  PaginatedData,
  TradingRecord,
  TradingRecordFormData,
  TradingDiary,
  TradingDiaryFormData,
  AccountSnapshot,
  AccountSnapshotFormData,
  EquityCurveAutoPoint,
  SystemConfigItem,
  StockSearchResult,
  PDCACycle,
  BrokerAdapter,
  TradingPlan,
  TradingPlanFormData,
  PlanTemplate,
  SecurityTag,
  ImportParseResult,
  ExitSlip,
  ExitSlipFormData,
} from './types';

// Axios 实例（统一配置）
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: API_TIMEOUT,
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
      // FastAPI 错误信息在 detail 字段（HTTPException 为字符串），message 为兼容旧接口
      const rawMsg = error.response?.data?.message;
      const rawDetail = error.response?.data?.detail;
      const serverMsg = rawMsg || (typeof rawDetail === 'string' ? rawDetail : undefined);

      if (status === HTTP_STATUS.UNAUTHORIZED) {
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

const BASE = API_PREFIX;

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
// 资金记录 & 资金曲线
// ============================================================

/** 新增资金记录 */
export async function saveSnapshot(
  snapshot: AccountSnapshotFormData,
): Promise<ApiResponse<AccountSnapshot>> {
  const { data } = await client.post(`${BASE}/snapshots`, snapshot);
  return data;
}

/** 获取资金记录列表 */
export async function fetchSnapshots(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<ApiResponse<ListData<AccountSnapshot>>> {
  const { data } = await client.get(`${BASE}/snapshots`, { params });
  return data;
}

/** 修改资金记录 */
export async function updateSnapshot(
  id: number,
  snapshot: AccountSnapshotFormData,
): Promise<ApiResponse<unknown>> {
  const { data } = await client.put(`${BASE}/snapshots/${id}`, snapshot);
  return data;
}

/** 删除资金记录 */
export async function deleteSnapshot(id: number): Promise<ApiResponse<unknown>> {
  const { data } = await client.delete(`${BASE}/snapshots/${id}`);
  return data;
}

/** 获取自动计算净值曲线（基于股票买卖 + 未平仓浮盈） */
export async function fetchEquityAutoCurve(): Promise<ApiResponse<ListData<EquityCurveAutoPoint>>> {
  const { data } = await client.get(`${BASE}/snapshots/curve-auto`);
  return data;
}

// ============================================================
// 交易日记
// ============================================================

/** 获取交易日记列表 */
export async function fetchDiaries(params: {
  record_id?: number;
  cycle_id?: number;
  page?: number;
  page_size?: number;
}): Promise<ApiResponse<PaginatedData<TradingDiary>>> {
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
export async function fetchConfig(): Promise<ApiResponse<ListData<SystemConfigItem>>> {
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
  // 使用 fetch 而非 client.post：axios + FormData 在 MSW 测试环境下存在兼容性问题
  const res = await fetch(`${client.defaults.baseURL}${BASE}/import/parse`, {
    method: 'POST',
    body: formData,
  });
  return res.json();
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
  ApiResponse<ListData<BrokerAdapter>>
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
}): Promise<ApiResponse<ListData<PDCACycle>>> {
  const { data } = await client.get(`${BASE}/cycles`, { params });
  return data;
}

/** 新建 PDCA 周期 */
export async function createCycle(payload: {
  cycle_name: string;
  cycle_type: string;
  start_date: string;
  end_date: string;
  goal_text?: string | null;
}): Promise<ApiResponse<PDCACycle>> {
  const { data } = await client.post(`${BASE}/cycles`, payload);
  return data;
}

/** 删除 PDCA 周期（仅 PLAN 状态） */
export async function deleteCycle(id: number): Promise<ApiResponse<null>> {
  const { data } = await client.delete(`${BASE}/cycles/${id}`);
  return data;
}

/** 状态流转 */
export async function transitionCycle(
  id: number,
  targetStatus: string,
): Promise<ApiResponse<PDCACycle>> {
  const { data } = await client.put(`${BASE}/cycles/${id}/transition`, {
    target_status: targetStatus,
  });
  return data;
}

// ============================================================
// 交易计划（阶段A：Plan 模块）
// ============================================================

/** 获取交易计划模板列表（FR-P07） */
export async function fetchPlanTemplates(): Promise<
  ApiResponse<ListData<PlanTemplate>>
> {
  const { data } = await client.get(`${BASE}/plans/templates`);
  return data;
}

/** 获取交易计划列表（可按周期/标的筛选） */
export async function fetchPlans(params?: {
  cycle_id?: number;
  code?: string;
}): Promise<ApiResponse<ListData<TradingPlan>>> {
  const { data } = await client.get(`${BASE}/plans`, { params });
  return data;
}

/** 新建交易计划 */
export async function createPlan(
  payload: TradingPlanFormData,
): Promise<ApiResponse<{ id: number }>> {
  const { data } = await client.post(`${BASE}/plans`, payload);
  return data;
}

/** 更新交易计划（仅 PLAN 状态周期） */
export async function updatePlan(
  id: number,
  payload: Partial<TradingPlanFormData>,
): Promise<ApiResponse<{ id: number }>> {
  const { data } = await client.put(`${BASE}/plans/${id}`, payload);
  return data;
}

/** 删除交易计划（软删除，仅 PLAN 状态周期） */
export async function deletePlan(id: number): Promise<ApiResponse<{ id: number }>> {
  const { data } = await client.delete(`${BASE}/plans/${id}`);
  return data;
}

// ============================================================
// 标的 ABC 分类（阶段A：PL-003 前置）
// ============================================================

/** 获取 ABC 分类列表 */
export async function fetchSecurities(params?: {
  tag?: string;
}): Promise<ApiResponse<ListData<SecurityTag>>> {
  const { data } = await client.get(`${BASE}/securities`, { params });
  return data;
}

/** 新增或覆盖 ABC 分类 */
export async function upsertSecurity(payload: {
  code: string;
  security_name?: string | null;
  tag: string;
  note?: string | null;
}): Promise<ApiResponse<{ id: number }>> {
  const { data } = await client.post(`${BASE}/securities`, payload);
  return data;
}

/** 更新 ABC 分类 */
export async function updateSecurity(
  id: number,
  payload: {
    security_name?: string | null;
    tag: string;
    note?: string | null;
  },
): Promise<ApiResponse<{ id: number }>> {
  const { data } = await client.put(`${BASE}/securities/${id}`, payload);
  return data;
}

/** 删除 ABC 分类 */
export async function deleteSecurity(id: number): Promise<ApiResponse<{ id: number }>> {
  const { data } = await client.delete(`${BASE}/securities/${id}`);
  return data;
}

// ============================================================
// 卖出子单（一买多卖）
// ============================================================

/** 获取买入单的所有卖出子单 */
export async function fetchExitSlips(
  recordId: number,
): Promise<ApiResponse<ListData<ExitSlip>>> {
  const { data } = await client.get(`${BASE}/records/${recordId}/exit-slips`);
  return data;
}

/** 批量新增卖出子单 */
export async function batchCreateExitSlips(
  recordId: number,
  slips: ExitSlipFormData[],
): Promise<ApiResponse<{ record_id: number; remain_qty: number; gross_profit: number }>> {
  const { data } = await client.post(`${BASE}/records/${recordId}/exit-slips/batch`, { slips });
  return data;
}

/** 修改卖出子单 */
export async function updateExitSlip(
  slipId: number,
  payload: Partial<ExitSlipFormData>,
): Promise<ApiResponse<ExitSlip>> {
  const { data } = await client.put(`${BASE}/exit-slips/${slipId}`, payload);
  return data;
}

/** 删除卖出子单 */
export async function deleteExitSlip(slipId: number): Promise<ApiResponse<null>> {
  const { data } = await client.delete(`${BASE}/exit-slips/${slipId}`);
  return data;
}

// ============================================================
// 日线行情查询（用于自动计算得分）
// ============================================================

/** 单日 OHLC 数据 */
export interface DailyOHLC {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

/**
 * 查询股票在指定交易日的 OHLC 数据
 * 依赖后端 /api/kline/{code} 接口
 */
export async function fetchDailyOHLC(
  code: string,
  date: string,
): Promise<DailyOHLC | null> {
  try {
    const { data } = await client.get(`${BASE}/kline/${code}`, {
      params: {
        period: 'daily',
        start_date: date,
        end_date: date,
        limit: 1,
        adj: 'none',
      },
    });
    if (data?.data?.length > 0) {
      const item = data.data[0];
      return {
        trade_date: item.trade_date,
        open: Number(item.open),
        high: Number(item.high),
        low: Number(item.low),
        close: Number(item.close),
      };
    }
    return null;
  } catch {
    return null;
  }
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