import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/*
 * Served under /audits/ behind the shared tunnel, next to the renewal console.
 * The base is set here rather than on the CLI so `npm run dev` and `npm run build`
 * agree about it — the API base is derived from import.meta.env.BASE_URL, and the
 * sibling app broke exactly because those two disagreed.
 */
export default defineConfig({
  base: "/audits/",
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5174,
    proxy: {
      "/audits/api": {
        target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8085",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/audits/, ""),
      },
    },
  },
});
