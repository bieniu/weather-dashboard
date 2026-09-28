import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { load as loadYaml } from "js-yaml";
import { THEME_ICONS } from "../../frontend/app.js";

// vitest (and `npm test`) run from the repository root.
const ROOT = process.cwd();
const read = (path) => readFileSync(join(ROOT, path), "utf8");

/** Ligature names the UI can render (index.html, app.js, config.yaml icons). */
function usedIconNames() {
  const names = new Set();
  for (const source of [read("frontend/index.html"), read("frontend/app.js")]) {
    for (const m of source.matchAll(/material-symbols-rounded[^>]*>\s*([a-z0-9_]+)\s*</g)) {
      names.add(m[1]);
    }
  }
  for (const name of Object.values(THEME_ICONS)) names.add(name); // set via textContent
  const config = loadYaml(read("config.yaml"));
  for (const sensor of Object.values(config.sensors)) {
    if (sensor.icon) names.add(sensor.icon.replace(/^mdi:/, ""));
  }
  return names;
}

function requestedIconNames() {
  const html = read("frontend/index.html");
  const match = html.match(/icon_names=([a-z0-9_,]+)/);
  return match ? match[1].split(",") : [];
}

describe("Material Symbols subset", () => {
  it("requests every icon the UI can show", () => {
    const requested = new Set(requestedIconNames());
    const missing = [...usedIconNames()].filter((name) => !requested.has(name));
    expect(missing).toEqual([]);
  });

  it("lists icon names alphabetically (Google Fonts rejects other orders)", () => {
    const requested = requestedIconNames();
    expect(requested.length).toBeGreaterThan(0);
    expect(requested).toEqual([...requested].sort());
  });
});

describe("dark theme tokens", () => {
  it("keeps the explicit [data-theme=dark] block and the OS-preference block identical", () => {
    const css = read("frontend/style.css");
    const block = (selector) => {
      const start = css.indexOf(selector);
      expect(start, `${selector} not found`).toBeGreaterThan(-1);
      const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
      return body
        .split(";")
        .map((line) => line.trim())
        .filter(Boolean)
        .sort();
    };
    expect(block(':root:not([data-theme="light"])')).toEqual(block('[data-theme="dark"]'));
  });
});
