"""Generate teaching slide images for explainer videos — text + animated diagrams."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from diagram_renderer import draw_diagram, infer_diagram_type

DEFAULT_BG = "#0f0f1a"
DEFAULT_ACCENT = "#3B82F6"
TITLE_COLOR = "#FFFFFF"
BULLET_COLOR = "#A0A0B0"
WATERMARK_COLOR = "#3a3a4a"
BAR_WIDTH = 8
DIAGRAM_HEIGHT = 520
ANIM_REVEAL_RATIO = 0.55  # reveal completes in first 55% of animation frames

# Diagram types that render bullets inside the diagram — skip duplicate list below
_SELF_CONTAINED_DIAGRAMS = frozenset({
    "list_items",
    "warning_icons",
    "status_code",
})


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    import platform

    candidates: list[str] = []
    if platform.system() == "Windows":
        candidates.extend([
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        ])
    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ])
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        except OSError:
            continue
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
    return lines[:2]


def _should_show_bullets(scene: dict[str, Any], bullets: list[str]) -> bool:
    if not bullets:
        return False
    diagram_type = infer_diagram_type(scene)
    if diagram_type in _SELF_CONTAINED_DIAGRAMS:
        return False
    return True


def render_slide_frame(
    scene: dict[str, Any],
    dest: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
    progress: float = 1.0,
    frame_t: float = 0.0,
) -> Path:
    """Render one slide frame; progress 0..1 drives diagram reveal animation."""
    img = Image.new("RGB", (width, height), _hex_to_rgb(bg_color))
    draw = ImageDraw.Draw(img)

    accent = scene.get("accent_color", DEFAULT_ACCENT)
    accent_rgb = _hex_to_rgb(accent)
    draw.rectangle([(0, 0), (BAR_WIDTH, height)], fill=accent_rgb)

    title_font = _load_font(64, bold=True)
    bullet_font = _load_font(32)
    diagram_label_font = _load_font(40, bold=True)
    diagram_small_font = _load_font(22)
    watermark_font = _load_font(24)

    title = str(scene.get("visual_title", "Concept")).strip()
    bullets = [str(b).strip() for b in scene.get("visual_bullets", []) if str(b).strip()][:3]
    show_bullets = _should_show_bullets(scene, bullets)

    x_start = 80
    y = 72
    max_text_width = width - 160

    for line in _wrap_title(title, title_font, max_text_width):
        draw.text((x_start, y), line, fill=_hex_to_rgb(TITLE_COLOR), font=title_font)
        y += 78

    diagram_top = 188
    diagram_height = DIAGRAM_HEIGHT
    diagram_bbox = (48, diagram_top, width - 48, diagram_top + diagram_height)

    # Subtle panel glow
    glow_alpha = int(12 + 8 * min(1.0, progress))
    panel_fill = (14 + glow_alpha // 4, 14 + glow_alpha // 4, 22 + glow_alpha // 3)
    draw.rounded_rectangle(
        diagram_bbox,
        radius=20,
        outline=tuple(min(255, c + 30) for c in accent_rgb),
        width=2,
        fill=panel_fill,
    )
    inner_bbox = (diagram_bbox[0] + 16, diagram_bbox[1] + 16, diagram_bbox[2] - 16, diagram_bbox[3] - 16)
    draw_diagram(
        draw,
        scene,
        inner_bbox,
        accent_rgb,
        progress=progress,
        frame_t=frame_t,
        label_font=diagram_label_font,
        small_font=diagram_small_font,
    )

    # Bullets fade in after diagram — only when they add info beyond the diagram
    bullet_progress = max(0.0, min(1.0, (progress - 0.6) / 0.35))
    if bullet_progress > 0 and show_bullets:
        y_bullets = diagram_top + diagram_height + 32
        for bullet in bullets:
            wrapped = textwrap.wrap(bullet, width=52)
            for i, line in enumerate(wrapped):
                color = (
                    int(_hex_to_rgb(BULLET_COLOR)[0] * bullet_progress + 18 * (1 - bullet_progress)),
                    int(_hex_to_rgb(BULLET_COLOR)[1] * bullet_progress + 18 * (1 - bullet_progress)),
                    int(_hex_to_rgb(BULLET_COLOR)[2] * bullet_progress + 28 * (1 - bullet_progress)),
                )
                prefix = "• " if i == 0 else "  "
                draw.text((x_start, y_bullets), prefix + line, fill=color, font=bullet_font)
                y_bullets += 44
            y_bullets += 6

    wm = channel_name
    wm_bbox = watermark_font.getbbox(wm)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text((width - wm_w - 40, height - 50), wm, fill=_hex_to_rgb(WATERMARK_COLOR), font=watermark_font)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest


def render_slide(
    scene: dict[str, Any],
    dest: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
) -> Path:
    """Render final slide PNG (fully revealed diagram + bullets)."""
    return render_slide_frame(
        scene,
        dest,
        width=width,
        height=height,
        bg_color=bg_color,
        channel_name=channel_name,
        progress=1.0,
        frame_t=0.5,
    )


def render_slide_frames(
    scene: dict[str, Any],
    frames_dir: Path,
    *,
    n_frames: int = 30,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
) -> list[Path]:
    """Render progressive-reveal animation frames for one scene."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    n = max(12, n_frames)
    anim_frames = max(12, min(n, int(n * ANIM_REVEAL_RATIO)))
    for i in range(n):
        frame_t = i / max(1, n - 1)
        if i < anim_frames:
            progress = i / (anim_frames - 1) if anim_frames > 1 else 1.0
        else:
            progress = 1.0
        dest = frames_dir / f"frame_{i:04d}.png"
        render_slide_frame(
            scene,
            dest,
            width=width,
            height=height,
            bg_color=bg_color,
            channel_name=channel_name,
            progress=progress,
            frame_t=frame_t,
        )
        paths.append(dest)
    return paths


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
