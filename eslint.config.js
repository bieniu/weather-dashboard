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
        setInterval: "readonly",
        clearInterval: "readonly",
        Notification: "readonly",
        matchMedia: "readonly",
        Chart: "readonly",
        caches: "readonly",
        self: "readonly",
        process: "readonly",
        Event: "readonly",
        Element: "readonly",
        HTMLCanvasElement: "readonly",
        vi: "readonly",
        describe: "readonly",
        it: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
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
