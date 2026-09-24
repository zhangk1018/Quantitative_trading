/**
 * watchlist api - 自选股 REST 客户端
 *
 * 对接后端 /api/watchlist（统一响应信封 {code, message, data}）
 *
 * 复用约束：
 * - 与 stock-detail/api.ts 共用 axios 实例（baseURL = '/api'）
 * - 数据解包走与 fetchStocks 相同的 unwrap 模式
 * - 不直接构造 fetch；错误由 message.error 统一处理（业务层不抛）
 */
import axios from 'axios';
import { attachSessionWatcher } from '@/features/auth/session';

interface ApiResponse<T> {
  code?: number;
  message?: string;
  data: T;
}

const api = axios.create({ baseURL: '/api', withCredentials: true });

// 会话失效（401 unauthenticated）统一捕获 → 踢下线跳登录
attachSessionWatcher(api);

const unwrap = <T>(response: ApiResponse<T>): T => {
  if (response.data !== undefined) return response.data;
  throw new Error(response.message || 'API Request Failed');
};

/** 自选股项（与后端 WatchlistItem 保持一致） */
export interface WatchlistItem {
  id: number;
  code: string;
  group_name: string;
  sort_order: number;
  created_at?: string;
}

/** 添加自选股请求体 */
export interface AddWatchlistRequest {
  code: string;
  group_name?: string;
}

/**
 * 获取自选股列表
 * GET /api/watchlist/
 *
 * 账号隔离：后端按会话身份（get_current_user）取 user_id，前端不再传 user_id
 */
export const fetchWatchlist = async (): Promise<WatchlistItem[]> => {
  const { data } = await api.get<ApiResponse<WatchlistItem[]>>('/watchlist/');
  const list = unwrap(data);
  return Array.isArray(list) ? list : [];
};

/**
 * 添加自选股（单只）
 * POST /api/watchlist/
 *
 * 业务约束：
 * - 重复添加返回 409 → 由调用方决定是"提示"还是"静默跳过"
 * - 返回的 data 是新创建的 item（包含后端分配的 id/sort_order）
 */
export const addWatchlist = async (payload: AddWatchlistRequest): Promise<WatchlistItem> => {
  const { data } = await api.post<ApiResponse<WatchlistItem>>('/watchlist/', payload);
  return unwrap(data);
};

/**
 * 移除自选股
 * DELETE /api/watchlist/{code}
 */
export const removeWatchlist = async (code: string): Promise<void> => {
  const { data } = await api.delete<ApiResponse<null>>(`/watchlist/${code}`);
  unwrap(data);
};
