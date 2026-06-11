import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * Vite 配置
 *
 * Phase 5.1.a (2026-06-10): 部署支持
 * - 开发模式：dev server 5173 + proxy /api → localhost:8000
 * - 生产模式：build 产物由 nginx 服务，nginx 反代 /api → backend:8000
 * - 两种模式均使用相对路径（/api/...），前端代码无需修改
 *
 * VITE_API_BASE 可在构建时注入（Dockerfile.frontend ARG），用于跨域部署
 *  - 同域（默认）：VITE_API_BASE=/api
 *  - 跨域：VITE_API_BASE=https://api.example.com/api
 */
const VITE_API_BASE = process.env.VITE_API_BASE || '/api'

export default defineConfig({
  plugins: [react()],
  // 注入到 import.meta.env.VITE_API_BASE（前端代码可读）
  define: {
    'import.meta.env.VITE_API_BASE': JSON.stringify(VITE_API_BASE),
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 输出 dist/，由 Dockerfile.frontend 复制到 nginx
    outDir: 'dist',
    sourcemap: false,  // 生产关闭 sourcemap（减体积）
    chunkSizeWarningLimit: 800,  // klinecharts 体积较大（~700KB）
    rollupOptions: {
      output: {
        // 拆包：把 klinecharts 单独 chunk（首屏不需加载）
        manualChunks: {
          klinecharts: ['klinecharts'],
          react: ['react', 'react-dom'],
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})