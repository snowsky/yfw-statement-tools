import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_STATEMENT_TOOLS_PREFIX": JSON.stringify(
      "/api/v1/external/statement-tools"
    ),
    "import.meta.env.VITE_USE_SETUP": JSON.stringify("true"),
  },
  resolve: {
    alias: {
      "@shared": path.resolve(__dirname, "../../shared/ui"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
