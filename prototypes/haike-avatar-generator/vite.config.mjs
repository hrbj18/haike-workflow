import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.HAIKE_EMBED_BASE || "/",
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target: "http://127.0.0.1:14754" },
    },
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [react(), {
    name: "local-workspace-links",
    configureServer(server) {
      // Redirect to each app's own origin so its assets, login and API routes work.
      for (const [prefix, port] of [["/workspace", 14754], ["/account", 17894]]) {
        server.middlewares.use(prefix, (req, res) => {
          const url = new URL(req.url || "/", `http://127.0.0.1:${port}`);
          if (url.origin !== `http://127.0.0.1:${port}`) { res.writeHead(400); res.end(); return; }
          res.writeHead(302, { Location: url.href });
          res.end();
        });
      }
    },
  }],
});
