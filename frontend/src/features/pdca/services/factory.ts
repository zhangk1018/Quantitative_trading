/**
 * factory.ts — 通用 CRUD 服务工厂
 *
 * 自动生成标准 REST 资源操作，减少重复代码。
 * 每个实体模块只需调用 createEntityService() 即可获得基础 CRUD。
 *
 * 使用方式：
 *   const recordApi = createEntityService<TradingRecord, TradingRecordFormData>('/records');
 *   const list = await recordApi.list({ page: 1, page_size: 20 });  // T[]
 *   const id = await recordApi.create(formData);                     // number
 *   await recordApi.update(id, { ... });                            // void
 *   await recordApi.delete(id);                                     // void
 *
 * 变更历史：
 * - 2026-08-18: 新增，替代 api.ts 中大量重复的 CRUD 函数
 */
import client from './client';
import { API_PREFIX } from '@/config/constants';

const BASE = API_PREFIX;

// ============================================================
// 工具类型
// ============================================================

/** 通用的分页查询参数 */
export interface PaginationParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_asc?: boolean;
}

/** 非分页列表查询参数 */
export interface ListParams {
  [key: string]: unknown;
}

// ============================================================
// CRUD 服务接口
// ============================================================

export interface EntityService<T, TForm = T> {
  /** 获取分页列表 */
  list(params?: PaginationParams & Record<string, unknown>): Promise<T[]>;
  /** 获取无分页列表 */
  listAll(params?: ListParams): Promise<T[]>;
  /** 获取单个 */
  get(id: number): Promise<T>;
  /** 创建 */
  create(payload: TForm): Promise<number>;
  /** 更新 */
  update(id: number, payload: Partial<TForm>): Promise<void>;
  /** 删除 */
  delete(id: number): Promise<void>;
}

// ============================================================
// 工厂函数
// ============================================================

/**
 * 创建标准 CRUD 服务
 *
 * @param endpoint    - REST 资源路径（如 '/records'）
 * @param idField     - 后端返回的 ID 字段名，默认 'id'
 * @returns EntityService 实例
 */
export function createEntityService<T, TForm = T>(
  endpoint: string,
  idField: string = 'id',
): EntityService<T, TForm> {
  return {
    async list(params) {
      const { data } = await client.get(`${BASE}${endpoint}`, { params });
      return (data as { items: T[] }).items;
    },

    async listAll(params) {
      const { data } = await client.get(`${BASE}${endpoint}`, { params });
      return (data as { items: T[] }).items;
    },

    async get(id) {
      return client.get(`${BASE}${endpoint}/${id}`);
    },

    async create(payload) {
      const result = await client.post(`${BASE}${endpoint}`, payload);
      return (result as unknown as Record<string, number>)[idField];
    },

    async update(id, payload) {
      await client.put(`${BASE}${endpoint}/${id}`, payload);
    },

    async delete(id) {
      await client.delete(`${BASE}${endpoint}/${id}`);
    },
  };
}

/**
 * 创建仅读取的列表服务（适用于枚举、配置等只读资源）
 */
export function createReadonlyService<T>(endpoint: string) {
  return {
    async list(params?: ListParams) {
      const { data } = await client.get(`${BASE}${endpoint}`, { params });
      return (data as { items: T[] }).items;
    },
  };
}