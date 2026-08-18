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
});

// ── 请求拦截器：注入认证头 ──
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
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

    // 401 时清除失效 token
    if (status === HTTP_STATUS.UNAUTHORIZED) {
      localStorage.removeItem('auth_token');
    }

    throw new NetworkError(
      status || 0,
      serverMsg || (status === 0 ? '网络连接失败' : `请求失败 (${status || '未知'})`),
    );
  },
);

export default client;