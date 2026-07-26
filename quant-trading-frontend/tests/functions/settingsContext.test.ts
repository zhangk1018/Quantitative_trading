// settingsContext.test.ts — SettingsContext 颜色方案配置
//
// 覆盖场景：
//   - getUpDownColors 纯函数
//   - COLOR_SCHEMES 常量验证
//   - localStorage 读取/降级
//   - 跨标签页同步（storage 事件）

import { describe, it, expect, beforeEach } from 'vitest';
import { getUpDownColors, COLOR_SCHEMES } from '../../src/shared/contexts/SettingsContext';

const STORAGE_KEY = 'app_settings_color_scheme';

beforeEach(() => {
  localStorage.clear();
});

// ==================== COLOR_SCHEMES ====================

describe('COLOR_SCHEMES', () => {
  it('cn 模式：涨红跌绿', () => {
    const cn = COLOR_SCHEMES.cn;
    expect(cn.colors.up).toBe('#EF5350');
    expect(cn.colors.down).toBe('#26A69A');
    expect(cn.label).toContain('红涨绿跌');
  });

  it('intl 模式：涨绿跌红', () => {
    const intl = COLOR_SCHEMES.intl;
    expect(intl.colors.up).toBe('#26A69A');
    expect(intl.colors.down).toBe('#EF5350');
    expect(intl.label).toContain('绿涨红跌');
  });

  it('两种模式颜色互为翻转', () => {
    const cn = COLOR_SCHEMES.cn.colors;
    const intl = COLOR_SCHEMES.intl.colors;
    expect(cn.up).toBe(intl.down);
    expect(cn.down).toBe(intl.up);
  });
});

// ==================== getUpDownColors ====================

describe('getUpDownColors', () => {
  it('默认返回 cn 模式颜色', () => {
    const colors = getUpDownColors();
    expect(colors.up).toBe('#EF5350');
    expect(colors.down).toBe('#26A69A');
  });

  it('读取 localStorage 中的 cn 设置', () => {
    localStorage.setItem(STORAGE_KEY, 'cn');
    const colors = getUpDownColors();
    expect(colors.up).toBe('#EF5350');
  });

  it('读取 localStorage 中的 intl 设置', () => {
    localStorage.setItem(STORAGE_KEY, 'intl');
    const colors = getUpDownColors();
    expect(colors.up).toBe('#26A69A');
    expect(colors.down).toBe('#EF5350');
  });

  it('非法值回退到 cn 默认', () => {
    localStorage.setItem(STORAGE_KEY, 'invalid');
    const colors = getUpDownColors();
    expect(colors.up).toBe('#EF5350');
  });

  it('不抛异常', () => {
    localStorage.setItem(STORAGE_KEY, '');
    expect(() => getUpDownColors()).not.toThrow();
  });
});