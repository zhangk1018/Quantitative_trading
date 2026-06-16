import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from './mocks/server';

// 启动 MSW mock server
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// 每个测试后清理 DOM + 重置 MSW handlers
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

// 所有测试结束后关闭 MSW
afterAll(() => server.close());
