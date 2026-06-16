import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';

/**
 * 涨跌颜色方案
 * - cn:  中国惯例（红涨绿跌）→ 涨=#EF5350(红)  跌=#26A69A(绿)
 * - intl: 国际惯例（绿涨红跌）→ 涨=#26A69A(绿)  跌=#EF5350(红)
 */
export type ColorScheme = 'cn' | 'intl';

const STORAGE_KEY = 'app_settings_color_scheme';

export interface UpDownColors {
  up: string;
  down: string;
}

export const COLOR_SCHEMES: Record<ColorScheme, { label: string; description: string; colors: UpDownColors }> = {
  cn: {
    label: '中国惯例（红涨绿跌）',
    description: '上涨红色 / 下跌绿色',
    colors: { up: '#EF5350', down: '#26A69A' },
  },
  intl: {
    label: '国际惯例（绿涨红跌）',
    description: '上涨绿色 / 下跌红色',
    colors: { up: '#26A69A', down: '#EF5350' },
  },
};

function loadColorScheme(): ColorScheme {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'cn' || v === 'intl') return v;
  } catch {
    // localStorage 不可用时回退到默认
  }
  return 'cn';
}

interface SettingsContextType {
  colorScheme: ColorScheme;
  setColorScheme: (scheme: ColorScheme) => void;
  colors: UpDownColors;
}

const SettingsContext = createContext<SettingsContextType | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>(loadColorScheme);

  const setColorScheme = (scheme: ColorScheme) => {
    setColorSchemeState(scheme);
    try {
      localStorage.setItem(STORAGE_KEY, scheme);
    } catch {
      // 静默失败
    }
  };

  // 跨标签页同步设置
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && (e.newValue === 'cn' || e.newValue === 'intl')) {
        setColorSchemeState(e.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return (
    <SettingsContext.Provider
      value={{ colorScheme, setColorScheme, colors: COLOR_SCHEMES[colorScheme].colors }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextType {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return ctx;
}
