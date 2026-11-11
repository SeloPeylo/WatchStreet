import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build lands inside the Python package; FastAPI serves it under /static/app.
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  worker: { format: "es" },
  build: { outDir: "../src/watchstreet/web/static/app", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/static/vendor": "http://127.0.0.1:8000" } },
});
