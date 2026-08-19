/**
 * config.ts — 系统配置 API
 */
import { apiGet, apiPut } from './client';
import { API_PREFIX } from '@/config/constants';
import type { SystemConfigItem, ListData } from '../types';

const BASE = API_PREFIX;

/** 获取系统配置 */
export async function fetchConfig(): Promise<SystemConfigItem[]> {
  const result = await apiGet<ListData<SystemConfigItem>>(`${BASE}/config`);
  return result.items;
}

/** 更新系统配置 */
export async function updateConfig(
  configKey: string,
  updates: { config_value?: string; numeric_value?: number; bool_value?: boolean; modify_reason: string },
): Promise<SystemConfigItem> {
  return apiPut<SystemConfigItem>(`${BASE}/config`, { config_key: configKey, ...updates });
}