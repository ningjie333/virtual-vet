import { defineConfig } from "vite-plus";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

// vite.config.ts is at: <project>/vet-game-frontend/vite-project/
// <project> root (my_project) is 2 levels up
const FLASK_ROOT = resolve(__dirname, "../..");
const FLASK_STATIC = resolve(FLASK_ROOT, "static");

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
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
