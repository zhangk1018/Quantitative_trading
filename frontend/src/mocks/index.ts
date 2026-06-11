/**
 * mocks/index.ts - Mock 数据统一导出
 * 
 * 用于前端开发阶段的模拟数据。
 * 
 * 生产环境不加载 Mock 数据（通过 VITE_ENABLE_MOCK 环境变量控制）。
 * 在 .env.production 中设置 VITE_ENABLE_MOCK=false 即可禁用。
 */

const isMockEnabled = () => {
    try {
        return import.meta.env.VITE_ENABLE_MOCK === 'true'
    } catch {
        // 环境变量不可用时（如无 Vite 上下文），默认禁用
        return false
    }
}

if (!isMockEnabled()) {
    console.warn('[Mock] 模拟数据已禁用（设置 VITE_ENABLE_MOCK=true 以启用）')
}

export { mockMetaResponse } from './meta'
export { generateMockStocks, mockStocksResponse } from './stocks'
