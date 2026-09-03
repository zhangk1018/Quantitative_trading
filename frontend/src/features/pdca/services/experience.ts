/**
 * experience.ts — 经验知识库 API
 *
 * 对应后端：GET /api/pdca/experiences
 * （协作单 [21.0]，量量实现中；本 service 按契约先行，联调后即可展示）
 */
import { apiGet } from './client';
import { API_PREFIX } from '@/config/constants';
import type { TradeExperience, ExperienceQueryParams, PaginatedData } from '../types';

const BASE = API_PREFIX;

/** 查询经验知识库（支持标签筛选 / 关键词搜索 / 分页） */
export async function fetchExperiences(params?: ExperienceQueryParams): Promise<PaginatedData<TradeExperience>> {
  return apiGet<PaginatedData<TradeExperience>>(`${BASE}/experiences`, { params });
}
