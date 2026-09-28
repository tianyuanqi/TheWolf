import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.WOLF_DEV_PORT ?? "5173"),
    strictPort: true,
    proxy: {
      "/api": { target: `http://127.0.0.1:${process.env.WOLF_SERVICE_PORT ?? "8000"}`,
        changeOrigin: true },
    },
  },
});
