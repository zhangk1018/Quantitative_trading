import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      include: [
        'src/features/stock-picker/**/*.{ts,tsx}',
      ],
      exclude: [
        'src/features/stock-picker/**/*.{d.ts,test.ts,test.tsx}',
        'src/features/stock-picker/api.ts',
        'src/features/stock-picker/store.ts',
        'src/features/stock-picker/index.tsx',
        'src/features/stock-picker/StockPickerView.tsx',
      ],
    },
  },
});
