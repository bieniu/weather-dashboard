import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    setupFiles: ["./tests/frontend/setup.js"],
    include: ["tests/frontend/**/*.test.js"],
    coverage: {
      provider: "v8",
      include: ["frontend/app.js"],
      reporter: ["text", "lcovonly"],
    },
  },
});
