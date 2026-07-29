import { setupServer } from 'msw/node';
import { stocksHandlers } from './handlers';

// 启动 mock 服务器（Node 环境，用于 Vitest）
export const server = setupServer(...stocksHandlers);
