/**
 * config.ts - 前端配置
 * 
 * 包含开发/生产环境的配置项
 */

/**
 * 是否使用 Mock 数据
 * 
 * 开发环境：true（无需后端即可测试前端）
 * 生产环境：false（调用真实 API）
 */
export const USE_MOCK = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true'

/**
 * API 基础路径
 */
export const API_BASE = import.meta.env.VITE_API_BASE || '/api'

/**
 * 分页默认配置
 */
export const DEFAULT_PAGE_SIZE = 100
export const MAX_PAGE_SIZE = 200

/**
 * 缓存配置
 */
export const CACHE_CONFIG = {
  KLINE_TTL: 10 * 60 * 1000,  // K线缓存 10分钟
  SIGNAL_TTL: 5 * 60 * 1000,  // 信号缓存 5分钟
}
