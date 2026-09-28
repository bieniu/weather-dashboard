import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: ["**/weather_icons/**", "**/icons/**", "frontend/vendor/**"],
  },
  js.configs.recommended,
  {
    languageOptions: { ecmaVersion: 2022, sourceType: "module" },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-console": "off",
    },
  },
  {
    files: ["frontend/**/*.js"],
    ignores: ["frontend/service-worker.js"],
    languageOptions: { globals: { ...globals.browser, Chart: "readonly" } },
  },
  {
    files: ["frontend/service-worker.js"],
    languageOptions: { sourceType: "script", globals: globals.serviceworker },
  },
  {
    // Frontend tests run in happy-dom, so they also see the browser globals.
    files: ["tests/**/*.js"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.vitest, Chart: "readonly" },
    },
  },
  {
    files: ["scripts/**/*.{js,mjs}", "*.config.js"],
    languageOptions: { globals: globals.node },
  },
];
