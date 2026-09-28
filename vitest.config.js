import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // setup.js pins process.env.TZ = "UTC" before the modules build their Intl
    // formatters; that only takes effect in a fresh process, i.e. the forks pool.
    pool: "forks",
    environment: "happy-dom",
    environmentOptions: {
      // initAnalytics appends a <script>; never fetch it, and report it as loaded.
      happyDOM: {
        settings: { disableJavaScriptFileLoading: true, handleDisabledFileLoadingAsSuccess: true },
      },
    },
    setupFiles: ["./tests/frontend/setup.js"],
    include: ["tests/frontend/**/*.test.js"],
    coverage: {
      provider: "v8",
      // service-worker.js runs in a vm context (tests/frontend/service-worker.test.js), which v8 coverage cannot see.
      include: ["frontend/*.js"],
      exclude: ["frontend/service-worker.js"],
      reporter: ["text", "lcovonly"],
    },
  },
});
