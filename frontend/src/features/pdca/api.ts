/**
 * api.ts — PDCA 模块 API 统一导出入口（barrel file）
 *
 * 所有业务接口已按领域拆分到 services/ 目录下。
 * 本文件仅做 re-export，确保所有现有 import 路径保持兼容。
 *
 * 新代码请直接 import 自对应的 services/* 模块：
 *   import { fetchCycles } from '../services/cycle';
 *   import { fetchRecords } from '../services/record';
 *
 * 变更历史：
 * - 2026-08-18: 重构为 barrel 导出，原业务逻辑迁移至 services/ 目录
 */
export { default as client, NetworkError, BusinessError } from './services/client';
export { createEntityService, createReadonlyService } from './services/factory';
export type { EntityService, PaginationParams, ListParams } from './services/factory';

// ── 交易台账 & 卖出子单 & 日线行情 ──
export {
  fetchRecords,
  fetchExitSlips,
  batchCreateExitSlips,
  updateExitSlip,
  deleteExitSlip,
  fetchDailyOHLC,
  recordApi,
} from './services/record';
export type { DailyOHLC } from './services/record';

// ── PDCA 周期 & 执行跟踪 ──
export {
  fetchCycles,
  createCycle,
  deleteCycle,
  fetchExecutionSummary,
  transitionCycle,
} from './services/cycle';

// ── 交易计划 & ABC 分类 ──
export {
  fetchPlanTemplates,
  planApi,
  fetchSecurities,
  upsertSecurity,
  updateSecurity,
  deleteSecurity,
} from './services/plan';

// ── 交易日记 ──
export {
  fetchDiaries,
  createDiary,
  updateDiary,
  uploadDiaryAttachment,
} from './services/diary';

// ── 资金快照 & 资金曲线 ──
export {
  fetchSnapshots,
  saveSnapshot,
  updateSnapshot,
  deleteSnapshot,
  fetchEquityAutoCurve,
} from './services/snapshot';

// ── 系统配置 ──
export { fetchConfig, updateConfig } from './services/config';

// ── Excel 导入导出 & 备份 ──
export {
  parseImportExcel,
  confirmImport,
  exportRecords,
  backupDatabase,
  downloadExcel,
  downloadBackup,
} from './services/import';

// ── 股票搜索 & 券商适配器 ──
export { searchStocks, fetchBrokerAdapters } from './services/stock';

// ── 复盘报告 ──
export { fetchCheckReport, createCheckReport, updateCheckReport } from './services/check-report';

// ── 迭代处理记录 ──
export { fetchActRecords, createActRecord, updateActRecord, deleteActRecord } from './services/act-record';

// ── 行为日志 ──
export {
  fetchBehaviorLogs,
  createBehaviorLog,
  updateBehaviorLog,
  deleteBehaviorLog,
  fetchBehaviorLogTypes,
} from './services/behavior-log';