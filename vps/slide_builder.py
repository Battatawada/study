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


def render_slide_frame(
    scene: dict[str, Any],
    dest: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
    progress: float = 1.0,
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
    diagram_type = infer_diagram_type(scene)

    x_start = 80
    y = 80
    max_text_width = width - 160

    for line in _wrap_title(title, title_font, max_text_width):
        draw.text((x_start, y), line, fill=_hex_to_rgb(TITLE_COLOR), font=title_font)
        y += 78

    # Diagram panel — center of slide
    diagram_top = 200
    diagram_height = 420
    diagram_bbox = (60, diagram_top, width - 60, diagram_height)
    draw.rounded_rectangle(
        diagram_bbox,
        radius=16,
        outline=tuple(min(255, c + 20) for c in accent_rgb),
        width=1,
        fill=(18, 18, 28),
    )
    inner_bbox = (diagram_bbox[0] + 12, diagram_bbox[1] + 12, diagram_bbox[2] - 12, diagram_bbox[3] - 12)
    draw_diagram(
        draw,
        scene,
        inner_bbox,
        accent_rgb,
        progress=progress,
        label_font=diagram_label_font,
        small_font=diagram_small_font,
    )

    diagram_prompt = str(scene.get("diagram_prompt", "")).strip()
    if diagram_prompt and progress > 0.55:
        caption_alpha = max(0.0, min(1.0, (progress - 0.55) / 0.35))
        cap_color = (
            int(100 * caption_alpha + 40 * (1 - caption_alpha)),
            int(100 * caption_alpha + 40 * (1 - caption_alpha)),
            int(120 * caption_alpha + 50 * (1 - caption_alpha)),
        )
        cap_y = inner_bbox[3] - 8
        cap_text = diagram_prompt[:72] + ("…" if len(diagram_prompt) > 72 else "")
        draw.text((inner_bbox[0] + 8, cap_y), cap_text, fill=cap_color, font=diagram_small_font, anchor="ls")

    # Bullets fade in during final third of animation
    bullet_progress = max(0.0, min(1.0, (progress - 0.65) / 0.35))
    if bullet_progress > 0 and bullets:
        y_bullets = diagram_top + diagram_height + 36
        for bullet in bullets:
            wrapped = textwrap.wrap(bullet, width=48)
            for i, line in enumerate(wrapped):
                alpha = int(255 * bullet_progress)
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
    n = max(8, n_frames)
    # Animation completes in first ~40% of frames; hold final state for the rest
    anim_frames = max(8, min(n, int(n * 0.4)))
    for i in range(n):
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
