"""Generate teaching slide images for explainer videos."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

DEFAULT_BG = "#0f0f1a"
DEFAULT_ACCENT = "#3B82F6"
TITLE_COLOR = "#FFFFFF"
BULLET_COLOR = "#A0A0B0"
WATERMARK_COLOR = "#3a3a4a"
BAR_WIDTH = 8


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_title(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        test = " ".join(current + [word])
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines[:3]


def render_slide(
    scene: dict[str, Any],
    dest: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
) -> Path:
    """Render one concept slide PNG from a scene spec."""
    img = Image.new("RGB", (width, height), _hex_to_rgb(bg_color))
    draw = ImageDraw.Draw(img)

    accent = scene.get("accent_color", DEFAULT_ACCENT)
    accent_rgb = _hex_to_rgb(accent)
    draw.rectangle([(0, 0), (BAR_WIDTH, height)], fill=accent_rgb)

    title_font = _load_font(72, bold=True)
    bullet_font = _load_font(36)
    watermark_font = _load_font(24)

    title = str(scene.get("visual_title", "Concept")).strip()
    bullets = [str(b).strip() for b in scene.get("visual_bullets", []) if str(b).strip()][:3]

    x_start = 80
    y = 120
    max_text_width = width - 160

    for line in _wrap_title(title, title_font, max_text_width):
        draw.text((x_start, y), line, fill=_hex_to_rgb(TITLE_COLOR), font=title_font)
        y += 90

    y += 40
    for bullet in bullets:
        wrapped = textwrap.wrap(bullet, width=50)
        for i, line in enumerate(wrapped):
            prefix = "• " if i == 0 else "  "
            draw.text((x_start, y), prefix + line, fill=_hex_to_rgb(BULLET_COLOR), font=bullet_font)
            y += 50
        y += 10

    wm = channel_name
    wm_bbox = watermark_font.getbbox(wm)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text((width - wm_w - 40, height - 50), wm, fill=_hex_to_rgb(WATERMARK_COLOR), font=watermark_font)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest


def render_all_slides(
    scenes: list[dict[str, Any]],
    work_dir: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
) -> list[Path]:
    paths: list[Path] = []
    for scene in scenes:
        sid = int(scene.get("scene_id", len(paths) + 1))
        dest = work_dir / f"slide_{sid:02d}.png"
        render_slide(scene, dest, width=width, height=height, bg_color=bg_color, channel_name=channel_name)
        paths.append(dest)
    return paths
