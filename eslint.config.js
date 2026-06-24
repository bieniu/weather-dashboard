import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        document: "readonly",
        window: "readonly",
        navigator: "readonly",
        location: "readonly",
        fetch: "readonly",
        getComputedStyle: "readonly",
        WebSocket: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        matchMedia: "readonly",
        Chart: "readonly",
        caches: "readonly",
        self: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-console": "off",
    },
  },
  {
    ignores: ["**/weather_icons/**", "**/icons/**"],
  },
];
