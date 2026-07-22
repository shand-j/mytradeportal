import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

function demoLocalhostRedirect(): Plugin {
  return {
    name: 'demo-localhost-redirect',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const host = req.headers.host || '';
        if (host === 'localhost:3000' || host === 'localhost') {
          res.writeHead(302, { Location: `http://demo.localhost:3000${req.url || '/'}` });
          res.end();
          return;
        }
        next();
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [demoLocalhostRedirect(), react()],
  server: {
    port: 3000,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
