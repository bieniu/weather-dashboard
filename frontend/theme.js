// Light/dark theme toggle; an explicit choice is persisted and wins over the OS.
import { updateChartTheme } from "./charts.js";

export const THEME_STORAGE_KEY = "theme";
// Ligatures the toggle switches between (must be in the Material Symbols subset).
export const THEME_ICONS = { dark: "light_mode", light: "dark_mode" };

function readStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null; // storage disabled (private mode, blocked site data)
  }
}

function storeTheme(theme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* preference simply does not persist */
  }
}

// The CSS already renders the OS preference before this runs (no flash); the
// attribute set here only matters for an explicit choice, which is persisted.
export function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  const html = document.documentElement;
  const systemDark = matchMedia("(prefers-color-scheme: dark)");
  let theme = readStoredTheme() ?? (systemDark.matches ? "dark" : "light");

  const applyTheme = () => {
    html.setAttribute("data-theme", theme);
    btn.querySelector(".material-symbols-rounded").textContent = THEME_ICONS[theme];
    btn.setAttribute("aria-label", theme === "dark" ? "Włącz jasny motyw" : "Włącz ciemny motyw");
  };
  applyTheme();

  systemDark.addEventListener?.("change", (event) => {
    if (readStoredTheme()) return; // an explicit choice wins over the OS
    theme = event.matches ? "dark" : "light";
    applyTheme();
    updateChartTheme();
  });

  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    storeTheme(theme);
    applyTheme();
    updateChartTheme();
  });
}
