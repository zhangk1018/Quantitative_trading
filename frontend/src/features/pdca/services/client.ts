/**
 * client.ts — PDCA 模块统一 API 客户端
 *
 * 职责：
 * - 提供预配置的 Axios 实例（baseURL / timeout / 认证注入）
 * - 响应拦截器自动解包（code=200 时直接返回 data，失败时抛出 ApiError）
 * - 统一的错误分类与格式化
 *
 * 变更历史：
 * - 2026-08-18: 新增 ApiError 类 + 响应解包逻辑（原逻辑在 api.ts 中与业务函数混用）
 */
import axios from 'axios';
import { API_TIMEOUT, HTTP_STATUS } from '@/config/constants';

// ============================================================
// 自定义 ApiError 异常类
// ============================================================

/** HTTP 网络错误（如 500、网络断开） */
export class NetworkError extends Error {
  statusCode: number;
  constructor(statusCode: number, message: string) {
    super(message);
    this.name = 'NetworkError';
    this.statusCode = statusCode;
  }
}

/** 业务逻辑错误（后端返回 code ≠ 200） */
export class BusinessError extends Error {
  businessCode: number;
  serverMessage: string;
  constructor(code: number, message: string) {
    super(message);
    this.name = 'BusinessError';
    this.businessCode = code;
    this.serverMessage = message;
  }
}

// ============================================================
// Axios 实例
// ============================================================

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: API_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,  // 认证载体为 HttpOnly Cookie，浏览器自动携带
});

// ── 响应拦截器：自动解包 + 统一错误处理 ──
client.interceptors.response.use(
  // 成功响应：自动解包 ApiResponse
  (response) => {
    const body = response.data;

    // 跳过非 JSON 响应（如 Blob 下载）
    if (body instanceof Blob || typeof body !== 'object') {
      return body;
    }

    // 跳过不含 code/data 结构的响应（如后端非标准接口）
    if (body.code === undefined) {
      return body;
    }

    // code=200 直接返回内部 data，调用方无需再拆
    if (body.code === HTTP_STATUS.SUCCESS) {
      return body.data;
    }

    // 业务错误：code ≠ 200
    throw new BusinessError(
      body.code,
      body.message || `业务请求失败 (code=${body.code})`,
    );
  },

  // HTTP 错误（网络错误、4xx、5xx）
  async (error) => {
    if (!axios.isAxiosError(error)) {
      throw new Error('请求异常');
    }

    const status = error.response?.status;
    let responseData = error.response?.data;

    // 处理 Blob 响应中的 JSON 错误（如导出/备份接口返回 400/500）
    let serverMsg: string | undefined;
    if (responseData instanceof Blob) {
      if (responseData.type === 'application/json') {
        try {
          const text = await responseData.text();
          const json = JSON.parse(text);
          serverMsg = json.message || (typeof json.detail === 'string' ? json.detail : undefined);
        } catch {
          // 解析失败时，保留原始错误信息
          serverMsg = `服务器返回了非预期的响应格式(HTTP ${status})`;
        }
      } else {
        serverMsg = `服务器返回了非预期的响应格式(HTTP ${status})`;
      }
    } else if (responseData) {
      serverMsg = responseData.message || (typeof responseData.detail === 'string' ? responseData.detail : undefined);
    }

    // 401 时跳转登录页（HttpOnly Cookie 过期或未认证）
    // 防护：已在登录页时不再跳转，防止无限循环
    if (status === HTTP_STATUS.UNAUTHORIZED && window.location.pathname !== '/login') {
      // 支持按请求配置跳过自动跳转（如登录页面的公共接口调用）
      const config = error.config as (typeof error.config & { skipAuthRedirect?: boolean }) | undefined;
      if (!config?.skipAuthRedirect) {
        window.location.href = '/login';
      }
    }

    throw new NetworkError(
      status || 0,
      serverMsg || (status === 0 ? '网络连接失败' : `请求失败 (${status || '未知'})`),
    );
  },
);

export default client;

// ============================================================
// 类型安全的 API 调用包装
// 拦截器已自动解包 body.data，此处标注正确返回类型
// ============================================================

/** 类型安全的 GET 请求，返回已解包的数据 */
export async function apiGet<T>(url: string, config?: any): Promise<T> {
  return client.get(url, config) as unknown as T;
}

/** 类型安全的 POST 请求，返回已解包的数据 */
export async function apiPost<T>(url: string, data?: any, config?: any): Promise<T> {
  return client.post(url, data, config) as unknown as T;
}

/** 类型安全的 PUT 请求，返回已解包的数据 */
export async function apiPut<T>(url: string, data?: any, config?: any): Promise<T> {
  return client.put(url, data, config) as unknown as T;
}

/** 类型安全的 DELETE 请求，返回已解包的数据 */
export async function apiDelete<T>(url: string, config?: any): Promise<T> {
  return client.delete(url, config) as unknown as T;
}

// ============================================================
// 错误提取工具函数
// 优先级：BusinessError.serverMessage → NetworkError.message → Error.message → 默认文案
// ============================================================

/** 从 catch 块中提取可读的错误消息 */
export function extractErrorMessage(err: unknown, fallback = '操作失败'): string {
  if (err instanceof BusinessError) {
    return err.serverMessage;
  }
  if (err instanceof NetworkError) {
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}