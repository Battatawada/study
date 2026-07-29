"""PIL diagram templates for teaching slides — CS concepts, HTTP flows, comparisons."""

from __future__ import annotations

import math
import re
from typing import Any

from PIL import ImageDraw, ImageFont

# Diagram area is drawn inside bbox (x0, y0, x1, y1)


def infer_diagram_type(scene: dict[str, Any]) -> str:
    """Pick diagram template from scene metadata or narration keywords."""
    explicit = str(scene.get("diagram_type", "")).strip().lower()
    # "concept" is a soft fallback from the visual-map LLM — always try keyword routing first.
    if explicit and explicit != "concept":
        return explicit

    title = str(scene.get("visual_title", ""))
    narration = str(scene.get("narration", ""))
    bullets = " ".join(scene.get("visual_bullets", []))
    text = f"{title} {narration} {bullets}".lower()

    if any(k in text for k in ("linked list", "linked node", "pointer", "next node")):
        return "linked_nodes"
    if any(k in text for k in ("binary tree", "tree node", "parent node", "child node", "bst")):
        return "tree_nodes"
    if any(k in text for k in ("stack", "heap", "call stack")):
        return "stack_heap"
    if scene.get("visual_type") == "comparison" or " vs " in text or "versus" in text:
        return "comparison"
    if any(k in text for k in ("array", "index", "locker", "offset", "element at")):
        return "array_access"
    if any(k in text for k in ("contiguous", "memory block", "ram", "address space", "allocation")):
        return "memory_layout"
    if any(k in text for k in ("crash", "stall", "failure", "consequence", "wrong choice", "inefficient")):
        return "warning_icons"
    if any(k in text for k in ("304", "not modified", "cache", "if-modified", "etag")):
        return "http_cache"
    if any(k in text for k in ("redirect", "301", "302", "303", "307", "308")):
        return "http_redirect"
    if re.search(r"\b4\d{2}\b", text) or "client error" in text or "client-side" in text:
        return "http_error_client"
    if re.search(r"\b5\d{2}\b", text) or "server error" in text or "server-side" in text:
        return "http_error_server"
    if any(k in text for k in ("request", "response", "get ", "post ", "put ", "delete ", "patch ")):
        return "http_request"
    if any(k in text for k in ("data structure", "software structure")):
        return "list_items"
    if scene.get("visual_type") == "list":
        return "list_items"
    if re.search(r"\bstep \d|first.*then|flow|pipeline|lifecycle", text):
        return "flow_steps"
    if re.search(r"\b\d{3}\b", title) or "http " in text or "status code" in text:
        return "status_code"
    return "concept"


def _clamp(progress: float) -> float:
    return max(0.0, min(1.0, progress))


def _ease(progress: float) -> float:
    p = _clamp(progress)
    return p * p * (3 - 2 * p)


def _alpha(progress: float, start: float, end: float) -> float:
    if progress <= start:
        return 0.0
    if progress >= end:
        return 1.0
    return _ease((progress - start) / (end - start))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * _clamp(t)


def _pulse(frame_t: float, *, speed: float = 2.0, amount: float = 0.15) -> float:
    """Subtle breathing effect during hold phase (frame_t 0..1 over full clip)."""
    return 1.0 + amount * math.sin(frame_t * math.pi * 2 * speed)


def _slide_x(base_x: float, reveal: float, offset: float = 40.0) -> float:
    return base_x + (1.0 - _ease(reveal)) * offset


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return []
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


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    *,
    max_width: int,
    anchor: str = "mm",
    line_spacing: int = 4,
) -> int:
    lines = _wrap_text(text, font, max_width)
    if not lines:
        return 0
    line_h = font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + line_spacing
    total_h = line_h * len(lines)
    if anchor == "mm":
        start_y = xy[1] - total_h / 2 + line_h / 2
        start_x = xy[0]
        anchor_each = "mm"
    else:
        start_y, start_x = xy[1], xy[0]
        anchor_each = anchor
    for i, line in enumerate(lines):
        draw.text((start_x, start_y + i * line_h), line, fill=fill, font=font, anchor=anchor_each)
    return total_h


def _draw_dot_grid(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    color: tuple[int, int, int] = (30, 30, 45),
    spacing: int = 28,
) -> None:
    x0, y0, x1, y1 = bbox
    for gx in range(x0 + spacing // 2, x1, spacing):
        for gy in range(y0 + spacing // 2, y1, spacing):
            draw.ellipse((gx - 1, gy - 1, gx + 1, gy + 1), fill=color)


def _draw_rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    *,
    radius: int = 12,
    width: int = 2,
    glow: tuple[int, int, int] | None = None,
) -> None:
    if glow:
        gx0, gy0, gx1, gy1 = xy[0] - 3, xy[1] - 3, xy[2] + 3, xy[3] + 3
        draw.rounded_rectangle((gx0, gy0, gx1, gy1), radius=radius + 2, outline=glow, width=1)
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    *,
    progress: float = 1.0,
    label: str = "",
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
    width: int = 3,
) -> None:
    sx, sy = start
    ex, ey = end
    t = _clamp(progress)
    cx = _lerp(sx, ex, t)
    cy = _lerp(sy, ey, t)
    draw.line([(sx, sy), (cx, cy)], fill=color, width=width)
    if t > 0.85:
        head_t = (t - 0.85) / 0.15
        angle = math.atan2(ey - sy, ex - sx)
        size = 10 * head_t
        a1 = angle + math.pi * 0.85
        a2 = angle - math.pi * 0.85
        p1 = (cx + size * math.cos(a1), cy + size * math.sin(a1))
        p2 = (cx + size * math.cos(a2), cy + size * math.sin(a2))
        draw.polygon([(cx, cy), p1, p2], fill=color)
    if label and label_font and t > 0.5:
        lx = (sx + cx) / 2
        ly = (sy + cy) / 2 - 18
        draw.text((lx, ly), label, fill=color, font=label_font, anchor="mm")


def _status_category(code: int) -> tuple[str, tuple[int, int, int]]:
    if 100 <= code < 200:
        return "1xx Informational", (6, 182, 212)
    if 200 <= code < 300:
        return "2xx Success", (16, 185, 129)
    if 300 <= code < 400:
        return "3xx Redirect", (245, 158, 11)
    if 400 <= code < 500:
        return "4xx Client Error", (239, 68, 68)
    if 500 <= code < 600:
        return "5xx Server Error", (139, 92, 246)
    return "Status", (59, 130, 246)


def _diagram_labels(scene: dict[str, Any], count: int, defaults: list[str]) -> list[str]:
    raw = scene.get("diagram_labels", [])
    if isinstance(raw, str):
        raw = [raw]
    labels = [str(x).strip() for x in raw if str(x).strip()][:count]
    while len(labels) < count:
        labels.append(defaults[len(labels)] if len(labels) < len(defaults) else "")
    return labels


def _extract_status_code(scene: dict[str, Any]) -> int | None:
    for src in (scene.get("visual_title", ""), scene.get("narration", "")):
        m = re.search(r"\b(\d{3})\b", str(src))
        if m:
            return int(m.group(1))
    return None


def _draw_memory_layout(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    labels: list[str],
    *,
    progress: float,
    frame_t: float,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    box_fill = (22, 22, 36)
    outline = tuple(min(255, c + 40) for c in accent)
    muted = (120, 120, 140)
    white = (240, 240, 245)

    n_cells = max(4, min(8, len(labels) or 6))
    cell_w = min(90, (w - 60) // n_cells)
    total_w = n_cells * cell_w
    start_x = x0 + (w - total_w) // 2
    cell_y = y0 + h // 2 - 30

    title = labels[0] if labels else "RAM"
    if _alpha(progress, 0.05, 0.2) > 0:
        draw.text((x0 + w // 2, y0 + 28), title, fill=muted, font=small_font, anchor="mm")

    for i in range(n_cells):
        reveal = _alpha(progress, 0.1 + i * 0.08, 0.22 + i * 0.08)
        if reveal <= 0:
            continue
        cx = int(_slide_x(start_x + i * cell_w, reveal, 24))
        pulse = _pulse(frame_t + i * 0.1, speed=1.5, amount=0.08 * reveal)
        ch = int(50 * pulse)
        active = i == min(n_cells - 1, int(progress * n_cells * 1.2))
        glow = accent if active and progress > 0.5 else None
        _draw_rounded_box(
            draw,
            (cx, cell_y, cx + cell_w - 6, cell_y + ch),
            box_fill,
            outline if not active else accent,
            radius=8,
            glow=glow,
        )
        addr = f"0x{(i * 8):03X}"
        draw.text((cx + (cell_w - 6) // 2, cell_y + ch + 14), addr, fill=muted, font=small_font, anchor="mm")

    if _alpha(progress, 0.55, 0.75) > 0:
        caption = labels[1] if len(labels) > 1 else "contiguous block"
        draw.text((x0 + w // 2, y1 - 36), caption, fill=white, font=label_font, anchor="mm")


def _draw_array_access(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    labels: list[str],
    *,
    progress: float,
    frame_t: float,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    box_fill = (22, 22, 36)
    outline = tuple(min(255, c + 40) for c in accent)
    muted = (120, 120, 140)
    white = (240, 240, 245)

    n = 5
    cell_w = min(72, (w - 80) // n)
    start_x = x0 + (w - n * cell_w) // 2
    row_y = y0 + h // 2 - 10

    base_label = labels[0] if labels else "base"
    if _alpha(progress, 0.05, 0.2) > 0:
        draw.text((start_x, row_y - 28), base_label, fill=accent, font=small_font, anchor="ls")

    target_idx = 3
    for i in range(n):
        reveal = _alpha(progress, 0.1 + i * 0.1, 0.25 + i * 0.1)
        if reveal <= 0:
            continue
        cx = int(_slide_x(start_x + i * cell_w, reveal, 20))
        is_target = i == target_idx and progress > 0.55
        glow = accent if is_target else None
        _draw_rounded_box(
            draw,
            (cx, row_y, cx + cell_w - 4, row_y + 52),
            box_fill,
            accent if is_target else outline,
            radius=8,
            glow=glow,
        )
        draw.text((cx + (cell_w - 4) // 2, row_y + 18), f"[{i}]", fill=white if not is_target else accent, font=small_font, anchor="mm")
        draw.text((cx + (cell_w - 4) // 2, row_y + 38), f"L{i}", fill=muted, font=small_font, anchor="mm")

    if _alpha(progress, 0.5, 0.7) > 0:
        math_label = labels[1] if len(labels) > 1 else "base + index × size"
        draw.text((x0 + w // 2, row_y + 78), math_label, fill=white, font=label_font, anchor="mm")
    if _alpha(progress, 0.72, 0.9) > 0:
        result = labels[2] if len(labels) > 2 else f"→ locker [{target_idx}]"
        draw.text((x0 + w // 2, row_y + 118), result, fill=accent, font=label_font, anchor="mm")


def _draw_linked_nodes(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    labels: list[str],
    *,
    progress: float,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    box_fill = (22, 22, 36)
    outline = tuple(min(255, c + 40) for c in accent)
    white = (240, 240, 245)
    n = 4
    node_w, node_h = 80, 56
    gap = 50
    total = n * node_w + (n - 1) * gap
    start_x = x0 + (w - total) // 2
    cy = y0 + h // 2

    for i in range(n):
        reveal = _alpha(progress, 0.08 + i * 0.15, 0.22 + i * 0.15)
        if reveal <= 0:
            continue
        px = int(_slide_x(start_x + i * (node_w + gap), reveal, 30))
        _draw_rounded_box(draw, (px, cy - node_h // 2, px + node_w, cy + node_h // 2), box_fill, outline, radius=10)
        lbl = labels[i] if i < len(labels) else f"Node {i}"
        draw.text((px + node_w // 2, cy), lbl[:12], fill=white, font=small_font, anchor="mm")
        if i < n - 1 and _alpha(progress, 0.2 + i * 0.15, 0.38 + i * 0.15) > 0:
            ax = px + node_w + 4
            _draw_arrow(
                draw,
                (ax, cy),
                (ax + gap - 8, cy),
                accent,
                progress=_alpha(progress, 0.2 + i * 0.15, 0.38 + i * 0.15),
                width=2,
            )
            draw.text((ax + gap // 2, cy - 16), "next", fill=accent, font=small_font, anchor="mm")


def _draw_warning_icons(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    labels: list[str],
    *,
    progress: float,
    frame_t: float,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    box_fill = (28, 18, 22)
    warn = (239, 68, 68)
    white = (240, 240, 245)
    muted = (120, 120, 140)

    items = labels or [str(b) for b in scene.get("visual_bullets", [])][:3]
    bullets = items if items else ["Database stalls", "Application crashes", "Inefficient memory"]

    n = len(bullets)
    col_w = (w - 40) // n
    icons = ["DB", "!", "MEM"]
    for i, (label, icon) in enumerate(zip(bullets, icons)):
        reveal = _alpha(progress, 0.1 + i * 0.18, 0.28 + i * 0.18)
        if reveal <= 0:
            continue
        cx = x0 + 20 + i * col_w + col_w // 2
        cy = y0 + h // 2 - 20
        pulse = _pulse(frame_t + i * 0.2, speed=1.2, amount=0.06)
        r = int(36 * pulse)
        _draw_rounded_box(
            draw,
            (int(cx - r), int(cy - r), int(cx + r), int(cy + r)),
            box_fill,
            warn,
            radius=12,
            glow=warn if progress > 0.6 else None,
        )
        draw.text((cx, cy), icon, fill=warn, font=label_font, anchor="mm")
        _draw_wrapped_text(draw, (cx, cy + r + 28), label, small_font, white, max_width=col_w - 16, anchor="mm")


def _draw_flow_steps(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    labels: list[str],
    *,
    progress: float,
    frame_t: float,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    box_fill = (22, 22, 36)
    outline = tuple(min(255, c + 40) for c in accent)
    white = (240, 240, 245)
    muted = (120, 120, 140)

    if not labels:
        labels = ["Step 1", "Step 2", "Step 3"]
    n = len(labels)
    use_vertical = any(len(lbl) > 18 for lbl in labels) or n > 3

    if use_vertical:
        step_h = min(72, (h - 40) // n)
        gap = 16
        start_y = y0 + (h - n * step_h - (n - 1) * gap) // 2
        box_w = w - 80
        box_x = x0 + 40
        for i, label in enumerate(labels):
            reveal = _alpha(progress, 0.08 + i * 0.15, 0.22 + i * 0.15)
            if reveal <= 0:
                continue
            py = int(_slide_x(start_y + i * (step_h + gap), reveal, 30))
            active = i == min(n - 1, int(progress * n * 1.1))
            _draw_rounded_box(
                draw,
                (box_x, py, box_x + box_w, py + step_h),
                box_fill,
                accent if active else outline,
                radius=10,
                glow=accent if active and progress > 0.4 else None,
            )
            draw.ellipse((box_x + 14, py + step_h // 2 - 14, box_x + 42, py + step_h // 2 + 14), fill=accent)
            draw.text((box_x + 28, py + step_h // 2), str(i + 1), fill=(15, 15, 25), font=label_font, anchor="mm")
            _draw_wrapped_text(draw, (box_x + 56, py + step_h // 2), label, small_font, white, max_width=box_w - 70, anchor="lm")
            if i < n - 1 and _alpha(progress, 0.18 + i * 0.15, 0.32 + i * 0.15) > 0:
                mid_x = box_x + box_w // 2
                _draw_arrow(draw, (mid_x, py + step_h + 2), (mid_x, py + step_h + gap - 2), muted, progress=1.0, width=2)
    else:
        step_w = min(220, (w - 60 - 36 * (n - 1)) // n)
        total_w = n * step_w + (n - 1) * 36
        start_x = x0 + (w - total_w) // 2
        step_h = 90
        py = y0 + h // 2 - step_h // 2
        for i, label in enumerate(labels):
            reveal = _alpha(progress, 0.1 + i * 0.18, 0.28 + i * 0.18)
            if reveal <= 0:
                continue
            px = int(_slide_x(start_x + i * (step_w + 36), reveal, 35))
            active = i == min(n - 1, int(progress * n * 1.1))
            _draw_rounded_box(
                draw,
                (px, py, px + step_w, py + step_h),
                box_fill,
                accent if active else outline,
                radius=10,
                glow=accent if active and progress > 0.4 else None,
            )
            draw.text((px + step_w // 2, py + 22), str(i + 1), fill=accent, font=label_font, anchor="mm")
            _draw_wrapped_text(draw, (px + step_w // 2, py + 58), label, small_font, white, max_width=step_w - 16, anchor="mm")
            if i < n - 1 and _alpha(progress, 0.22 + i * 0.18, 0.38 + i * 0.18) > 0:
                ax = px + step_w + 4
                _draw_arrow(
                    draw,
                    (ax, py + step_h // 2),
                    (ax + 28, py + step_h // 2),
                    muted,
                    progress=_alpha(progress, 0.22 + i * 0.18, 0.38 + i * 0.18),
                )


def draw_diagram(
    draw: ImageDraw.ImageDraw,
    scene: dict[str, Any],
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    *,
    progress: float = 1.0,
    frame_t: float = 0.0,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Render animated diagram inside bbox according to diagram_type."""
    diagram_type = infer_diagram_type(scene)
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    bg_fill = tuple(max(0, c - 30) for c in accent)
    box_fill = (22, 22, 36)
    outline = tuple(min(255, c + 40) for c in accent)
    muted = (120, 120, 140)
    white = (240, 240, 245)

    p = _clamp(progress)
    _draw_dot_grid(draw, bbox)

    if diagram_type == "memory_layout":
        labels = _diagram_labels(scene, 3, ["RAM", "contiguous block", ""])
        _draw_memory_layout(draw, bbox, accent, labels, progress=p, frame_t=frame_t, label_font=label_font, small_font=small_font)
        return

    if diagram_type == "array_access":
        labels = _diagram_labels(scene, 3, ["base address", "base + index × size", "target element"])
        _draw_array_access(draw, bbox, accent, labels, progress=p, frame_t=frame_t, label_font=label_font, small_font=small_font)
        return

    if diagram_type == "linked_nodes":
        labels = _diagram_labels(scene, 4, ["Head", "A", "B", "null"])
        _draw_linked_nodes(draw, bbox, accent, labels, progress=p, label_font=label_font, small_font=small_font)
        return

    if diagram_type == "warning_icons":
        labels = _diagram_labels(scene, 3, [])
        if not labels:
            labels = [str(b) for b in scene.get("visual_bullets", [])][:3]
        _draw_warning_icons(draw, bbox, accent, labels, progress=p, frame_t=frame_t, label_font=label_font, small_font=small_font)
        return

    if diagram_type == "stack_heap":
        labels = _diagram_labels(scene, 2, ["Stack", "Heap"])
        half = (w - 30) // 2
        for i, (lbl, col) in enumerate(zip(labels, [accent, (139, 92, 246)])):
            reveal = _alpha(p, 0.1 + i * 0.2, 0.35 + i * 0.2)
            if reveal <= 0:
                continue
            px = x0 + 10 + i * (half + 10)
            _draw_rounded_box(draw, (px, y0 + 30, px + half, y1 - 30), box_fill, col, radius=12, glow=col if p > 0.5 else None)
            draw.text((px + half // 2, y0 + 55), lbl, fill=col, font=label_font, anchor="mm")
            for j in range(4):
                block_reveal = _alpha(p, 0.3 + j * 0.1 + i * 0.05, 0.42 + j * 0.1 + i * 0.05)
                if block_reveal <= 0:
                    continue
                by = y0 + 80 + j * 42
                _draw_rounded_box(draw, (px + 16, by, px + half - 16, by + 32), bg_fill, col, radius=6)
        return

    if diagram_type == "tree_nodes":
        labels = _diagram_labels(scene, 3, ["root", "left", "right"])
        cx, cy = x0 + w // 2, y0 + 55
        if _alpha(p, 0.1, 0.3) > 0:
            _draw_rounded_box(draw, (cx - 40, cy - 22, cx + 40, cy + 22), box_fill, accent, radius=10, glow=accent)
            draw.text((cx, cy), labels[0], fill=white, font=small_font, anchor="mm")
        for i, (dx, lbl) in enumerate([(-80, labels[1] if len(labels) > 1 else "L"), (80, labels[2] if len(labels) > 2 else "R")]):
            reveal = _alpha(p, 0.35 + i * 0.15, 0.5 + i * 0.15)
            if reveal <= 0:
                continue
            child_x = cx + dx
            child_y = cy + 80
            _draw_arrow(draw, (cx, cy + 22), (child_x, child_y - 22), muted, progress=reveal, width=2)
            _draw_rounded_box(draw, (child_x - 36, child_y - 22, child_x + 36, child_y + 22), box_fill, outline, radius=8)
            draw.text((child_x, child_y), lbl, fill=white, font=small_font, anchor="mm")
        return

    if diagram_type == "status_code":
        code = _extract_status_code(scene) or 200
        cat, cat_color = _status_category(code)
        scale = _alpha(p, 0.1, 0.5)
        cx, cy = x0 + w // 2, y0 + h // 2 - 20
        size = int(120 * scale) if scale > 0 else 0
        if size > 0:
            draw.text((cx, cy), str(code), fill=cat_color, font=label_font, anchor="mm")
        if _alpha(p, 0.45, 0.75) > 0:
            draw.text((cx, cy + 70), cat, fill=muted, font=small_font, anchor="mm")
        return

    if diagram_type == "http_request":
        labels = _diagram_labels(scene, 2, ["Request", "Response"])
        req_label, res_label = labels[0], labels[1]
        box_w, box_h = 160, 100
        left_x = x0 + 40
        right_x = x0 + w - box_w - 40
        mid_y = y0 + h // 2
        if _alpha(p, 0.1, 0.35) > 0:
            _draw_rounded_box(draw, (left_x, mid_y - box_h // 2, left_x + box_w, mid_y + box_h // 2), box_fill, outline)
            _draw_rounded_box(draw, (right_x, mid_y - box_h // 2, right_x + box_w, mid_y + box_h // 2), box_fill, outline)
            draw.text((left_x + box_w // 2, mid_y - 10), "Client", fill=white, font=small_font, anchor="mm")
            draw.text((right_x + box_w // 2, mid_y - 10), "Server", fill=white, font=small_font, anchor="mm")
        req_p = _alpha(p, 0.35, 0.6)
        if req_p > 0:
            _draw_arrow(draw, (left_x + box_w + 8, mid_y - 15), (right_x - 8, mid_y - 15), accent, progress=req_p, label=req_label, label_font=small_font)
        res_p = _alpha(p, 0.55, 0.8)
        if res_p > 0:
            code = _extract_status_code(scene)
            res_color = _status_category(code)[1] if code else (16, 185, 129)
            _draw_arrow(draw, (right_x - 8, mid_y + 15), (left_x + box_w + 8, mid_y + 15), res_color, progress=res_p, label=res_label, label_font=small_font)
        return

    if diagram_type == "http_cache":
        labels = _diagram_labels(scene, 2, ["GET + If-Modified-Since", "304 Not Modified (no body)"])
        box_w, box_h = 150, 95
        left_x = x0 + 30
        right_x = x0 + w - box_w - 30
        mid_y = y0 + h // 2
        if _alpha(p, 0.1, 0.3) > 0:
            _draw_rounded_box(draw, (left_x, mid_y - box_h // 2, left_x + box_w, mid_y + box_h // 2), box_fill, outline)
            _draw_rounded_box(draw, (right_x, mid_y - box_h // 2, right_x + box_w, mid_y + box_h // 2), box_fill, outline)
            draw.text((left_x + box_w // 2, mid_y - 18), "Browser", fill=white, font=small_font, anchor="mm")
            cache_y = mid_y + 8
            _draw_rounded_box(draw, (left_x + 20, cache_y, left_x + box_w - 20, cache_y + 28), bg_fill, accent, radius=6)
            draw.text((left_x + box_w // 2, cache_y + 14), "cached copy", fill=accent, font=small_font, anchor="mm")
            draw.text((right_x + box_w // 2, mid_y), "Server", fill=white, font=small_font, anchor="mm")
        req_p = _alpha(p, 0.3, 0.55)
        if req_p > 0:
            _draw_arrow(draw, (left_x + box_w + 6, mid_y - 12), (right_x - 6, mid_y - 12), accent, progress=req_p, label=labels[0], label_font=small_font)
        res_p = _alpha(p, 0.55, 0.8)
        if res_p > 0:
            _draw_arrow(draw, (right_x - 6, mid_y + 18), (left_x + box_w + 6, mid_y + 18), (245, 158, 11), progress=res_p, label=labels[1], label_font=small_font)
        return

    if diagram_type == "http_redirect":
        box_w, box_h = 130, 80
        y_mid = y0 + h // 2 - box_h // 2
        positions = [x0 + 30, x0 + w // 2 - box_w // 2, x0 + w - box_w - 30]
        node_labels = ["Browser", "Server A", "Server B"]
        arrow_labels = _diagram_labels(scene, 3, ["GET /page", "302 Redirect", "follow redirect"])
        for i, (px, lbl) in enumerate(zip(positions, node_labels)):
            if _alpha(p, 0.1 + i * 0.12, 0.25 + i * 0.12) > 0:
                _draw_rounded_box(draw, (px, y_mid, px + box_w, y_mid + box_h), box_fill, outline)
                draw.text((px + box_w // 2, y_mid + box_h // 2), lbl, fill=white, font=small_font, anchor="mm")
        if _alpha(p, 0.4, 0.6) > 0:
            _draw_arrow(draw, (positions[0] + box_w + 4, y_mid + box_h // 2), (positions[1] - 4, y_mid + box_h // 2), accent, progress=_alpha(p, 0.4, 0.6), label=arrow_labels[0], label_font=small_font)
        if _alpha(p, 0.62, 0.82) > 0:
            _draw_arrow(draw, (positions[1] + box_w // 2, y_mid + box_h + 4), (positions[1] + box_w // 2, y_mid + box_h + 50), (245, 158, 11), progress=_alpha(p, 0.62, 0.82), label=arrow_labels[1], label_font=small_font)
            draw.text((positions[1] + box_w // 2, y_mid + box_h + 62), "Location: new-url", fill=muted, font=small_font, anchor="mm")
        if _alpha(p, 0.82, 1.0) > 0:
            _draw_arrow(draw, (positions[1] - 4, y_mid + box_h // 2), (positions[2] + box_w + 4, y_mid + box_h // 2), (16, 185, 129), progress=_alpha(p, 0.82, 1.0), label=arrow_labels[2], label_font=small_font)
        return

    if diagram_type == "http_error_client":
        code = _extract_status_code(scene) or 404
        cx, cy = x0 + w // 2, y0 + h // 2
        if _alpha(p, 0.1, 0.4) > 0:
            r = int(70 * _alpha(p, 0.1, 0.4))
            draw.ellipse((cx - r, cy - r - 10, cx + r, cy + r - 10), outline=(239, 68, 68), width=3)
            draw.text((cx, cy - 10), str(code), fill=(239, 68, 68), font=label_font, anchor="mm")
        if _alpha(p, 0.45, 0.7) > 0:
            draw.text((cx, cy + 60), "Client Error", fill=muted, font=small_font, anchor="mm")
        return

    if diagram_type == "http_error_server":
        code = _extract_status_code(scene) or 500
        cx = x0 + w // 2
        sy = y0 + 40
        if _alpha(p, 0.1, 0.35) > 0:
            _draw_rounded_box(draw, (cx - 90, sy, cx + 90, sy + 70), box_fill, (139, 92, 246))
            draw.text((cx, sy + 35), "Server", fill=white, font=small_font, anchor="mm")
        if _alpha(p, 0.35, 0.6) > 0:
            draw.text((cx, sy + 100), str(code), fill=(139, 92, 246), font=label_font, anchor="mm")
        return

    if diagram_type == "comparison":
        bullets = [str(b) for b in scene.get("visual_bullets", [])][:2]
        left_label = bullets[0] if bullets else "Option A"
        right_label = bullets[1] if len(bullets) > 1 else "Option B"
        gap = 30
        half_w = (w - gap) // 2
        ly = y0 + 20
        if _alpha(p, 0.1, 0.4) > 0:
            _draw_rounded_box(draw, (x0, ly, x0 + half_w, y1 - 20), box_fill, accent, glow=accent if p > 0.5 else None)
            _draw_rounded_box(draw, (x0 + half_w + gap, ly, x0 + w, y1 - 20), box_fill, outline)
            _draw_wrapped_text(draw, (x0 + half_w // 2, ly + 50), left_label, small_font, white, max_width=half_w - 24, anchor="mm")
            _draw_wrapped_text(draw, (x0 + half_w + gap + half_w // 2, ly + 50), right_label, small_font, white, max_width=half_w - 24, anchor="mm")
            draw.text((x0 + half_w + gap // 2, ly + h // 2), "vs", fill=muted, font=label_font, anchor="mm")
        return

    if diagram_type == "flow_steps":
        label_src = _diagram_labels(scene, 4, [])
        bullets = [lbl for lbl in (label_src or [str(b) for b in scene.get("visual_bullets", [])][:4]) if lbl.strip()]
        _draw_flow_steps(draw, bbox, accent, bullets, progress=p, frame_t=frame_t, label_font=label_font, small_font=small_font)
        return

    if diagram_type == "list_items":
        bullets = [str(b) for b in scene.get("visual_bullets", [])][:4]
        for i, bullet in enumerate(bullets):
            reveal = _alpha(p, 0.08 + i * 0.14, 0.22 + i * 0.14)
            if reveal <= 0:
                continue
            py = int(_slide_x(y0 + 24 + i * 62, reveal, 25))
            active = i == min(len(bullets) - 1, int(p * len(bullets) * 1.1))
            _draw_rounded_box(
                draw,
                (x0 + 20, py, x0 + 54, py + 40),
                bg_fill,
                accent if active else outline,
                radius=8,
                glow=accent if active and p > 0.4 else None,
            )
            draw.text((x0 + 37, py + 20), str(i + 1), fill=accent, font=small_font, anchor="mm")
            _draw_wrapped_text(draw, (x0 + 72, py + 20), bullet, small_font, white, max_width=w - 100, anchor="lm")
        return

    # concept — hub-and-spoke; diagram_prompt is internal metadata, never shown on slide
    labels = _diagram_labels(scene, 3, [])
    bullets = [str(b) for b in scene.get("visual_bullets", [])][:3]
    cx, cy = x0 + w // 2, y0 + h // 2
    title = str(scene.get("visual_title", "Concept"))
    for i, (dx, dy, delay) in enumerate([(0, 0, 0.05), (-100, -40, 0.15), (100, -40, 0.25), (-70, 55, 0.35), (70, 55, 0.45)]):
        r = int(24 * _alpha(p, delay, delay + 0.2))
        if r > 0:
            color = accent if i == 0 else outline
            draw.ellipse((cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r), outline=color, width=2)
            if i > 0:
                lbl = labels[min(i - 1, len(labels) - 1)] if labels else (bullets[min(i - 1, len(bullets) - 1)] if bullets else "")
                if lbl:
                    draw.text((cx + dx, cy + dy), lbl[:12], fill=white, font=small_font, anchor="mm")
    if _alpha(p, 0.5, 0.7) > 0:
        draw.text((cx, cy), title[:20], fill=white, font=label_font, anchor="mm")
