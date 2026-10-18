import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// This Vite app is the only Yashi UI. It talks to the FastAPI backend
// (API-only, :8000) through same-origin paths, forwarded here.
const BACKEND = process.env.YASHI_BACKEND || "http://127.0.0.1:8000";

const proxy = {};
for (const path of ["/api", "/audio", "/health"]) {
  proxy[path] = { target: BACKEND, changeOrigin: true };
}
proxy["/ws"] = { target: BACKEND.replace(/^http/, "ws"), ws: true };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy,
  },
  preview: {
    port: 4173,
    proxy,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // The lazily-loaded 3D avatar chunk is three.js (~190 kB gzipped); the
    // UI itself loads separately and first.
    chunkSizeWarningLimit: 800,
  }
});
