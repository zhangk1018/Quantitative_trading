import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { server } from './mocks/server';

// 启动 MSW mock server
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Antd 5 在 jsdom 下需要 matchMedia polyfill（Grid/ResponsiveObserver）
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // deprecated
      removeListener: vi.fn(), // deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// ResizeObserver polyfill（Antd Select/Drawer 需要）
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  (window as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// URL.createObjectURL / revokeObjectURL polyfill（jsdom 不实现，
// StockPickerView 的 CSV 导出测试需要用到）
if (typeof URL.createObjectURL !== 'function') {
  (URL as any).createObjectURL = vi.fn(() => 'blob:mock-url');
  (URL as any).revokeObjectURL = vi.fn();
}

// 每个测试后清理 DOM + 重置 MSW handlers
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

// 所有测试结束后关闭 MSW
afterAll(() => server.close());
