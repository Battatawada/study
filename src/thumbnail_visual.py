"""Visual thumbnails for CS / DSA explainers — frozen animation frames + structure montage."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from thumbnail_builder import _hex_to_rgb, _load_font


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int] | None = None,
    outline: tuple[int, int, int] | None = None,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _dot_grid(draw: ImageDraw.ImageDraw, w: int, h: int, color: tuple[int, int, int] = (28, 28, 42)) -> None:
    for x in range(24, w, 32):
        for y in range(24, h, 32):
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=color)


def _glow_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    color: tuple[int, int, int],
    *,
    radius: int = 8,
) -> None:
    x0, y0, x1, y1 = xy
    for pad, w in ((6, 1), (3, 2), (0, 3)):
        draw.rounded_rectangle(
            (x0 - pad, y0 - pad, x1 + pad, y1 + pad),
            radius=radius + pad // 2,
            outline=tuple(min(255, c + 30) for c in color),
            width=w,
        )


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    *,
    width: int = 2,
) -> None:
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 9
    ex, ey = end
    p1 = (ex - size * math.cos(angle - 0.45), ey - size * math.sin(angle - 0.45))
    p2 = (ex - size * math.cos(angle + 0.45), ey - size * math.sin(angle + 0.45))
    draw.polygon([end, p1, p2], fill=color)


def _memory_cell(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    value: str,
    *,
    w: int = 52,
    h: int = 44,
    outline: tuple[int, int, int],
    fill: tuple[int, int, int] = (22, 22, 36),
    highlight: bool = False,
    addr: str = "",
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    addr_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    box = (x, y, x + w, y + h)
    if highlight:
        _glow_rect(draw, box, outline, radius=8)
    else:
        _rounded_rect(draw, box, 8, fill=fill, outline=outline, width=2)
    if value:
        draw.text((x + w // 2, y + h // 2 - 2), value, font=font, fill=(240, 240, 245), anchor="mm")
    if addr:
        draw.text((x + w // 2, y + h + 14), addr, font=addr_font, fill=(120, 120, 140), anchor="mm")


def _draw_hero_array_insertion(
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    *,
    blue: tuple[int, int, int],
    cyan: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Frozen frame: array mid-insert — cells shifting, new value dropping in."""
    cell_w, gap = 54, 8
    values = ["10", "20", "", "30", "40"]
    addrs = ["0x00", "0x08", "0x10", "0x18", "0x20"]
    offsets = [0, 0, 0, 14, 14]  # 30 and 40 mid-shift right

    # Falling "25" block above gap
    drop_x = ox + 2 * (cell_w + gap) + cell_w // 2
    drop_y = oy - 28
    _memory_cell(draw, drop_x - 26, drop_y, "25", w=52, h=40, outline=cyan, highlight=True, font=font, addr_font=small)
    _draw_arrow(draw, (drop_x, drop_y + 42), (drop_x, oy - 6), cyan, width=3)

    for i, (val, addr, off) in enumerate(zip(values, addrs, offsets)):
        x = ox + i * (cell_w + gap) + off
        hl = i == 2 or (i == 3 and off > 0)
        col = cyan if hl else blue
        _memory_cell(
            draw, x, oy, val, w=cell_w, h=44,
            outline=col, highlight=hl, addr=addr, font=font, addr_font=small,
        )

    # Pointer
    px = ox + 2 * (cell_w + gap) + cell_w // 2 + 7
    draw.text((px, oy - 52), "insert", font=small, fill=cyan, anchor="mm")
    _draw_arrow(draw, (px, oy - 38), (px, oy - 8), cyan)


def _draw_linked_list(
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    *,
    blue: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    labels = ["A", "B", "C"]
    node_w, gap = 48, 36
    for i, lbl in enumerate(labels):
        x = ox + i * (node_w + gap)
        _rounded_rect(draw, (x, oy, x + node_w, oy + 38), 8, fill=(22, 22, 36), outline=blue, width=2)
        draw.text((x + node_w // 2, oy + 19), lbl, font=font, fill=(240, 240, 245), anchor="mm")
        if i < len(labels) - 1:
            _draw_arrow(draw, (x + node_w + 4, oy + 19), (x + node_w + gap - 4, oy + 19), blue)


def _draw_binary_tree(
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    *,
    blue: tuple[int, int, int],
    cyan: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    nodes = [(ox + 70, oy, "8"), (ox + 20, oy + 58, "3"), (ox + 120, oy + 58, "12")]
    edges = [(0, 1), (0, 2)]
    for a, b in edges:
        ax, ay, _ = nodes[a]
        bx, by, _ = nodes[b]
        _draw_arrow(draw, (ax, ay + 20), (bx + 18, by - 2), blue, width=2)
    for i, (x, y, lbl) in enumerate(nodes):
        hl = i == 0
        col = cyan if hl else blue
        _rounded_rect(draw, (x, y, x + 36, y + 28), 6, fill=(22, 22, 36), outline=col, width=3 if hl else 2)
        draw.text((x + 18, y + 14), lbl, font=font, fill=(240, 240, 245), anchor="mm")


def _draw_graph(
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    *,
    blue: tuple[int, int, int],
    cyan: tuple[int, int, int],
) -> None:
    pts = [(ox + 50, oy + 10), (ox + 10, oy + 55), (ox + 90, oy + 55), (ox + 50, oy + 90)]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (0, 3)]
    for a, b in edges:
        _draw_arrow(draw, pts[a], pts[b], blue, width=2)
    for i, (x, y) in enumerate(pts):
        hl = i == 0
        col = cyan if hl else blue
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=(22, 22, 36), outline=col, width=3 if hl else 2)


def _draw_stack(
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    *,
    blue: tuple[int, int, int],
    cyan: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    blocks = ["push", "pop", "top"]
    for i, lbl in enumerate(blocks):
        y = oy + i * 34
        hl = i == 2
        col = cyan if hl else blue
        _rounded_rect(draw, (ox, y, ox + 72, y + 28), 6, fill=(22, 22, 36), outline=col, width=2)
        draw.text((ox + 36, y + 14), lbl, font=font, fill=(240, 240, 245), anchor="mm")


def _stroke_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    *,
    anchor: str | None = None,
) -> None:
    x, y = xy
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0), anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def compose_visual_thumbnail(meta: dict[str, Any], dest: Path, *, size: tuple[int, int] = (1280, 720)) -> Path:
    """High-CTR visual thumbnail: typography left, DSA montage right."""
    bg = _hex_to_rgb(str(meta.get("bg_color", "#0a0a14")))
    white = (255, 255, 255)
    blue = _hex_to_rgb(str(meta.get("accent_color", "#3B82F6")))
    cyan = _hex_to_rgb(str(meta.get("highlight_color", "#06B6D4")))

    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    _dot_grid(draw, size[0], size[1])

    # Subtle right-side panel glow
    for x in range(size[0] // 2, size[0]):
        alpha = int(18 * (x - size[0] // 2) / (size[0] // 2))
        draw.line([(x, 0), (x, size[1])], fill=(blue[0] // 8 + alpha, blue[1] // 8 + alpha, blue[2] // 6 + alpha))

    title_line1 = str(meta.get("title_line1") or "DATA").upper()
    title_line2 = str(meta.get("title_line2") or meta.get("overlay_title") or "STRUCTURES").upper()
    # If overlay_title is multi-word like "DATA STRUCTURES", split
    if " " in title_line2 and title_line1 == "DATA" and title_line2.startswith("DATA"):
        parts = title_line2.split()
        title_line1 = parts[0]
        title_line2 = " ".join(parts[1:]) if len(parts) > 1 else "STRUCTURES"

    subtitle = str(meta.get("overlay_subtitle") or meta.get("thumbnail_subtitle") or "VISUALIZED").upper()
    time_badge = str(meta.get("time_badge", "22 MIN")).upper()

    font_huge = _load_font(108)
    font_big = _load_font(88)
    font_sub = _load_font(64)
    font_badge = _load_font(26)
    font_cell = _load_font(20)
    font_small = _load_font(14)
    font_label = _load_font(16)

    # --- Left typography ---
    lx, ly = 56, 120
    _stroke_text(draw, (lx, ly), title_line1, font_huge, white)
    _stroke_text(draw, (lx, ly + 108), title_line2, font_big, blue)
    _stroke_text(draw, (lx, ly + 210), subtitle, font_sub, cyan)

    # Accent bar
    draw.rounded_rectangle((lx, ly + 300, lx + 120, ly + 308), radius=4, fill=cyan)

    # --- Right visual montage ---
    panel_x = 520
    # Hero: array insertion (Option 2)
    draw.text((panel_x, 88), "ARRAY", font=font_label, fill=(100, 100, 120))
    _draw_hero_array_insertion(draw, panel_x + 20, 200, blue=blue, cyan=cyan, font=font_cell, small=font_small)

    # Linked list — top right
    draw.text((panel_x + 420, 88), "LIST", font=font_label, fill=(100, 100, 120))
    _draw_linked_list(draw, panel_x + 400, 118, blue=blue, font=font_cell)

    # Binary tree
    draw.text((panel_x, 310), "TREE", font=font_label, fill=(100, 100, 120))
    _draw_binary_tree(draw, panel_x + 10, 340, blue=blue, cyan=cyan, font=font_cell)

    # Graph
    draw.text((panel_x + 200, 310), "GRAPH", font=font_label, fill=(100, 100, 120))
    _draw_graph(draw, panel_x + 180, 330, blue=blue, cyan=cyan)

    # Stack
    draw.text((panel_x + 400, 310), "STACK", font=font_label, fill=(100, 100, 120))
    _draw_stack(draw, panel_x + 420, 340, blue=blue, cyan=cyan, font=font_small)

    # Connecting arrows between structures (subtle)
    _draw_arrow(draw, (panel_x + 350, 250), (panel_x + 400, 130), (*[c // 2 + 40 for c in blue],), width=1)
    _draw_arrow(draw, (panel_x + 180, 280), (panel_x + 60, 340), (*[c // 2 + 40 for c in cyan],), width=1)

    # Time badge
    if time_badge:
        bx, by = size[0] - 150, size[1] - 58
        draw.rounded_rectangle((bx, by, bx + 120, by + 40), radius=8, fill=blue)
        draw.text((bx + 60, by + 20), time_badge, font=font_badge, fill=white, anchor="mm")

    # Channel watermark
    draw.text((size[0] - 24, size[1] - 24), "Byte Glossary", font=font_small, fill=(60, 60, 80), anchor="rb")

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG", optimize=True)
    return dest


def should_use_visual_thumbnail(meta: dict[str, Any]) -> bool:
    style = str(meta.get("thumbnail_style", "")).lower()
    if style in ("visual", "dsa", "algorithm", "cs"):
        return True
    if style == "text":
        return False
    topic = f"{meta.get('topic', '')} {meta.get('title', '')}".lower()
    if any(k in topic for k in ("data structure", "algorithm", "leetcode", "binary tree", "linked list")):
        return True
    return meta.get("render_mode") == "slides" and meta.get("visual_thumbnail", True)
