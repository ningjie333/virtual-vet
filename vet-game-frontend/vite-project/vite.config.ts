import { defineConfig } from "vite-plus";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

// vite.config.ts is at: <project>/vet-game-frontend/vite-project/
// <project> root (my_project) is 2 levels up
const FLASK_ROOT = resolve(__dirname, "../..");
const FLASK_STATIC = resolve(FLASK_ROOT, "static");

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function resolveApiProxyTarget(): string {
  const explicitTarget = process.env.VITE_API_PROXY_TARGET?.trim();
  if (explicitTarget) return trimTrailingSlash(explicitTarget);

  const apiBaseUrl = process.env.VITE_API_BASE_URL?.trim();
  if (apiBaseUrl) {
    try {
      const url = new URL(apiBaseUrl);
      return `${url.protocol}//${url.host}`;
    } catch {
      return trimTrailingSlash(apiBaseUrl.replace(/\/api\/?$/, ""));
    }
  }

  const host = process.env.VV_HOST?.trim() || "127.0.0.1";
  const port = process.env.VV_PORT?.trim() || "5000";
  return `http://${host}:${port}`;
}

const apiProxyTarget = resolveApiProxyTarget();

export default defineConfig({
  staged: {
    "*": "vp check --fix",
  },
  fmt: {},
  lint: { options: { typeAware: true, typeCheck: true } },
  plugins: [vue()],
  build: {
    outDir: FLASK_STATIC,
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash].[ext]",
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
