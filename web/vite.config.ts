import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发态：vite dev server 在 5173，把 /api 代理到 uvicorn 的 8000，
// 这样前端代码里只写相对路径，生产态（FastAPI 直接托管 dist）不用改任何 URL。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/metrics": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
