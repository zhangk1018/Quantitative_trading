var _a;
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import monacoEditorPluginModule from 'vite-plugin-monaco-editor';
var monacoEditorPlugin = (_a = monacoEditorPluginModule.default) !== null && _a !== void 0 ? _a : monacoEditorPluginModule;
export default defineConfig({
    plugins: [
        react(),
        monacoEditorPlugin({
            languageWorkers: ['editorWorkerService'],
        }),
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: {
        port: 5173,
        strictPort: true,
        host: true,
        open: true,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
});
