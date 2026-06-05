/**
 * useEchartsTheme.ts - 跟随系统主题的 ECharts 主题 Hook
 *
 * 行为：
 * - 默认值：'auto'（跟随系统 prefers-color-scheme）
 * - 监听 matchMedia 变化，实时响应系统切换
 * - 返回实际的 light/dark，供组件使用
 */

import { useEffect, useState } from 'react'
import { getTheme, type KlineTheme, type ThemeMode } from '../config/klineTheme'

export type ThemePreference = ThemeMode | 'auto'

interface UseEchartsThemeReturn {
  /** 当前实际生效的主题（auto 模式会基于系统判断后返回 light/dark） */
  theme: KlineTheme
  /** 当前模式（auto 模式下返回系统实际值） */
  resolvedMode: ThemeMode
}

const MEDIA_QUERY = '(prefers-color-scheme: dark)'

/** 检测系统当前是否偏好深色 */
function getSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia(MEDIA_QUERY).matches
}

export function useEchartsTheme(preference: ThemePreference = 'auto'): UseEchartsThemeReturn {
  const [systemDark, setSystemDark] = useState<boolean>(() => getSystemPrefersDark())

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia(MEDIA_QUERY)
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    // 兼容旧 API（addListener/removeListener）
    if (mq.addEventListener) {
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    } else {
      mq.addListener(handler)
      return () => mq.removeListener(handler)
    }
  }, [])

  const resolvedMode: ThemeMode = preference === 'auto' ? (systemDark ? 'dark' : 'light') : preference
  return { theme: getTheme(resolvedMode), resolvedMode }
}
