/**
 * hooks/useUrlCode.ts - URL ?code= 双向同步 hook
 *
 * 用途：股票详情 Modal 的开关状态与 URL 双向绑定
 * - 用户打开 Modal → URL 变为 ?code=000001
 * - 用户点击浏览器后退 → Modal 自动关闭
 * - 用户分享 URL → 接收方打开页面时 Modal 自动展示
 *
 * 遵循项目硬约束："写入数据库的 code 字段必须使用 normalize_code 转换为纯数字"
 * 此处只关心前端 URL 展示，统一使用纯数字格式
 */

import { useEffect, useState, useCallback } from 'react';

/** 校验是否为 6 位纯数字股票代码 */
const isValidCode = (v: string | null): v is string =>
  !!v && /^\d{6}$/.test(v);

export function useUrlCode(): {
  code: string | null;
  setCode: (code: string | null) => void;
} {
  const [code, setCodeState] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    const params = new URLSearchParams(window.location.search);
    const c = params.get('code');
    return isValidCode(c) ? c : null;
  });

  // 同步到 URL
  const setCode = useCallback((newCode: string | null) => {
    setCodeState(newCode);
    if (typeof window === 'undefined') return;

    const url = new URL(window.location.href);
    if (newCode) {
      url.searchParams.set('code', newCode);
    } else {
      url.searchParams.delete('code');
    }
    // 使用 replace 避免污染历史栈（详情是临时视图）
    window.history.replaceState({}, '', url.toString());
  }, []);

  // 监听浏览器前进/后退
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handler = () => {
      const params = new URLSearchParams(window.location.search);
      const c = params.get('code');
      setCodeState(isValidCode(c) ? c : null);
    };

    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, []);

  return { code, setCode };
}
