import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// ONNX Runtime Web / Transformers.js 在 WASM / WebGPU 模式下需要用特定文件
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // 代理到 seekdb 后端
    proxy: {
      '/api': {
        target: 'http://localhost:5174',
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    exclude: ['@huggingface/transformers'],
  },
  build: {
    target: 'esnext',
    sourcemap: true,
  },
});
