import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // "Try the AI" demo — same-origin /demo in dev, forwarded to the API.
      "/demo": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom"],
  },
  // react-router's prebundled chunk inlines its own React copy (duplicate-
  // dispatcher crash at runtime); serve its raw ESM build instead.
  optimizeDeps: {
    exclude: ["react-router"],
    include: ["cookie", "set-cookie-parser"],
  },
});
