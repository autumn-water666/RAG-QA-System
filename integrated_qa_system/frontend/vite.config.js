import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base 用相对路径：产物要交给 FastAPI 在任意子路径托管，不能硬编码绝对根路径。
// build.outDir 直接输出到 FastAPI 托管的 static/，构建后无需再拷贝。
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // 开发模式：把 API 请求代理到本地 FastAPI，前后端分离联调
    proxy: {
      '/api': 'http://localhost:8000',
      '/api/stream': { target: 'ws://localhost:8000', ws: true },
    },
  },
})