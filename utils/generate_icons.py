"""Generate PWA icons and favicon from new_icon.svg with blue gradient background."""

import io
import os
import re

import cairosvg
from PIL import Image

SRC = os.path.join(os.path.dirname(__file__), "new_icon.svg")
OUT_DIR = os.path.join(os.path.dirname(__file__), "frontend", "icons")
FAVICON_OUT = os.path.join(os.path.dirname(__file__), "frontend", "favicon.svg")

BG_START = "#42A5F5"
BG_END = "#1E88E5"


def read_svg(path):
    with open(path) as f:
        return f.read()


def remove_youtube_script(content):
    return re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)


def modify_svg_for_png(content):
    """Add a visible blue gradient background rect (clipPath rect is invisible)."""
    content = remove_youtube_script(content)

    bg_def = (
        '<linearGradient id="icon-bg-grad" x1="0" y1="0" x2="0" y2="128" '
        'gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{BG_START}"/>'
        f'<stop offset="1" stop-color="{BG_END}"/>'
        "</linearGradient>"
    )

    # Add bg rect right after the opening <g> (before all content), then inject def
    content = content.replace(
        '<g id="thunderstorms-day__thunderstorms-day"',
        '<rect width="128" height="128" fill="url(#icon-bg-grad)"/>'
        '\n<g id="thunderstorms-day__thunderstorms-day"',
    )
    content = content.replace("</defs>", f"{bg_def}</defs>")

    return content


def render_svg_to_png(svg_content, output_size):
    """Render SVG to PNG at desired size via cairosvg."""
    png_data = cairosvg.svg2png(
        bytestring=svg_content.encode("utf-8"),
        output_width=output_size,
        output_height=output_size,
    )
    return Image.open(io.BytesIO(png_data))


def modify_svg_for_maskable(content):
    """Add background and scale icon to safe zone (80%) for maskable icons.

    The background rect fills the full viewBox so the gradient is
    continuous. The icon group is scaled+translated to the inner 80%
    safe zone required by Android adaptive icons.
    """
    content = remove_youtube_script(content)

    bg_def = (
        '<linearGradient id="icon-bg-grad" x1="0" y1="0" x2="0" y2="128" '
        'gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{BG_START}"/>'
        f'<stop offset="1" stop-color="{BG_END}"/>'
        "</linearGradient>"
    )

    # Add background rect before the icon group
    content = content.replace(
        '<g id="thunderstorms-day__thunderstorms-day"',
        '<rect width="128" height="128" fill="url(#icon-bg-grad)"/>'
        '\n<g id="thunderstorms-day__thunderstorms-day"',
    )

    # Scale icon into the safe zone (80% of output)
    # 128 * 0.8 = 102.4, margin = (128 - 102.4) / 2 = 12.8
    content = content.replace(
        'clip-path="url(#thunderstorms-day__clip0_1858_9913)"',
        'transform="translate(12.8, 12.8) scale(0.8)"',
    )

    content = content.replace("</defs>", f"{bg_def}</defs>")

    return content


def generate_maskable(svg_content, size=512):
    """Generate maskable icon — single-pass render, no seam."""
    maskable_svg = modify_svg_for_maskable(svg_content)
    return render_svg_to_png(maskable_svg, size)


def extract_visual_elements(svg_content):
    """Extract just the visual elements (sun, cloud, lightning) without clip-path wrapper."""
    content = remove_youtube_script(svg_content)

    # Extract defs
    defs_match = re.search(r"(<defs>.*?</defs>)", content, re.DOTALL)
    defs_content = defs_match.group(1) if defs_match else ""

    # Extract all visual elements inside the clip-path group (skip the clip-path attr)
    # Remove the outer g with clip-path, keep everything inside it
    inner_match = re.search(
        r'<g[^>]*clip-path="[^"]*"[^>]*>(.*?)</g>\s*<defs', content, re.DOTALL
    )
    if not inner_match:
        # Try without defs immediately after
        inner_match = re.search(
            r'<g[^>]*clip-path="[^"]*"[^>]*>(.*?)</g>', content, re.DOTALL
        )

    inner_content = inner_match.group(1) if inner_match else content

    # Extract individual gradient defs we need (sun, cloud, lightning)
    needed_ids = [
        "thunderstorms-day__paint0_linear_1858_9913",
        "thunderstorms-day__paint1_linear_1858_9913",
        "thunderstorms-day__paint2_linear_1858_9913",
    ]

    defs_only = "<defs>"
    for nid in needed_ids:
        grad_match = re.search(
            rf'<linearGradient[^>]*id="{re.escape(nid)}"[^>]*>.*?</linearGradient>',
            defs_content,
            re.DOTALL,
        )
        if grad_match:
            defs_only += grad_match.group(0)

    # Add blue bg gradient
    defs_only += (
        '<linearGradient id="fav-bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop stop-color="{BG_START}"/>'
        f'<stop offset="1" stop-color="{BG_END}"/>'
        "</linearGradient>"
    )
    defs_only += "</defs>"

    return defs_only, inner_content


def create_favicon(svg_content):
    """Create a 24x24 favicon SVG with transform-scale for exact rendering."""
    defs, inner = extract_visual_elements(svg_content)

    favicon = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
        f"{defs}\n"
        f'  <rect width="24" height="24" rx="5" fill="url(#fav-bg)"/>\n'
        f'  <g transform="scale(0.1875)">\n'
        f"{inner}\n"
        f"  </g>\n"
        f"</svg>"
    )
    return favicon


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    raw_svg = read_svg(SRC)
    modified_svg = modify_svg_for_png(raw_svg)

    # Debug: save modified SVG
    tmp_svg = os.path.join(os.path.dirname(__file__), "icon_with_bg.svg")
    with open(tmp_svg, "w") as f:
        f.write(modified_svg)
    print(f"Modified SVG saved to {tmp_svg}")

    icons = [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),
    ]

    for name, size in icons:
        print(f"Generating {name} ({size}x{size})...")
        img = render_svg_to_png(modified_svg, size)
        out_path = os.path.join(OUT_DIR, name)
        if name == "apple-touch-icon.png":
            rgb = Image.new("RGB", img.size, (BG_START))
            rgb.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            rgb.save(out_path, "PNG")
        else:
            img.save(out_path, "PNG")
        print(f"  -> {out_path}")

    print("Generating icon-512-maskable.png (512x512)...")
    maskable = generate_maskable(modified_svg, 512)
    maskable_path = os.path.join(OUT_DIR, "icon-512-maskable.png")
    maskable.save(maskable_path, "PNG")
    print(f"  -> {maskable_path}")

    print("Generating favicon.svg...")
    favicon_svg = create_favicon(raw_svg)
    with open(FAVICON_OUT, "w") as f:
        f.write(favicon_svg)
    print(f"  -> {FAVICON_OUT}")

    print("\nDone!")


if __name__ == "__main__":
    main()
