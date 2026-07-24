# utils/

## Responsibility

Icon generation tooling for the weather dashboard's PWA. Produces the app icons (PNG at various sizes), maskable icons for Android adaptive icons, and an SVG favicon — all derived from a single source icon.

## Design

- **Source**: `new_icon.svg` — a thunderstorms-day icon exported from a design tool (128×128 viewBox). Contains a `<script>` tag injected by YouTube that must be stripped before use.
- **Generation script**: `generate_icons.py` uses `cairosvg` to rasterise SVG to PNG and `Pillow` for final image encoding.
- **Templates**:
  - `icon.svg` — raw source icon (no background, with YouTube script).
  - `icon_with_bg.svg` — debug/intermediate output written by the script (source icon + blue gradient background rect).
- **Gradient**: Blue linear gradient (`#42A5F5` → `#1E88E5`) applied as a background rect behind the icon artwork.
- **Maskable variant**: The icon group is scaled to 80% (safe zone) and translated to the center, as required by Android adaptive icon masks.
- **Favicon**: A standalone 24×24 SVG with rounded corners (`rx="5"`) and the blue background. Visual elements are extracted from the source and scaled down via `transform="scale(0.1875)"` (24 / 128) to preserve pixel-perfect rendering.

## Flow

1. **Read**: `generate_icons.py` reads `new_icon.svg` (raw source).
2. **Sanitise**: The YouTube `<script>` tag is removed via regex.
3. **Render pipeline**:
   - `modify_svg_for_png()` injects a `<rect>` with the blue gradient background and defines the gradient in `<defs>`. The result is saved as `icon_with_bg.svg` (debug copy).
   - `render_svg_to_png()` converts the modified SVG to PNG at the requested size via `cairosvg.svg2png`.
   - Standard icons: 192×192 (`icon-192.png`), 512×512 (`icon-512.png`), 180×180 (`apple-touch-icon.png` — flattened to RGB with a solid background).
4. **Maskable icon**: `generate_maskable()` calls `modify_svg_for_maskable()` which adds the background and wraps the icon group in `transform="translate(12.8, 12.8) scale(0.8)"`. Rendered at 512×512 → `icon-512-maskable.png`.
5. **Favicon**: `create_favicon()` extracts only the needed gradient defs (sun, cloud, lightning, plus the blue background) and the inner visual elements (dropping the clip-path wrapper), then assembles a 24×24 SVG → `favicon.svg`.
6. **Output**: All files are written under `frontend/icons/` (relative to the script directory).

## Integration

- Output icons are consumed by the frontend PWA manifest and `<link>` tags (standard sizes for `manifest.json`, `apple-touch-icon`, favicon).
- The source `new_icon.svg` is expected at `utils/new_icon.svg`; intermediate `icon_with_bg.svg` is written to the same directory as a side-effect of generation.
- Run manually via `python utils/generate_icons.py` — there is no CI/CD or build-step integration.
