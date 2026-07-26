"""PIL diagram templates for teaching slides — request flows, caches, errors, comparisons."""

from __future__ import annotations

import re
from typing import Any

from PIL import ImageDraw, ImageFont

# Diagram area is drawn inside bbox (x, y, w, h)


def infer_diagram_type(scene: dict[str, Any]) -> str:
    """Pick diagram template from scene metadata or narration keywords."""
    explicit = str(scene.get("diagram_type", "")).strip().lower()
    if explicit:
        return explicit

    title = str(scene.get("visual_title", ""))
    narration = str(scene.get("narration", ""))
    bullets = " ".join(scene.get("visual_bullets", []))
    text = f"{title} {narration} {bullets}".lower()

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
    if scene.get("visual_type") == "comparison" or " vs " in text or "versus" in text:
        return "comparison"
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


def _draw_rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    radius: int = 12,
) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=2)


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    *,
    progress: float = 1.0,
    label: str = "",
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
) -> None:
    sx, sy = start
    ex, ey = end
    t = _clamp(progress)
    cx = _lerp(sx, ex, t)
    cy = _lerp(sy, ey, t)
    draw.line([(sx, sy), (cx, cy)], fill=color, width=3)
    if t > 0.85:
        head_t = (t - 0.85) / 0.15
        angle = __import__("math").atan2(ey - sy, ex - sx)
        size = 10 * head_t
        import math

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


def draw_diagram(
    draw: ImageDraw.ImageDraw,
    scene: dict[str, Any],
    bbox: tuple[int, int, int, int],
    accent: tuple[int, int, int],
    *,
    progress: float = 1.0,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Render animated diagram inside bbox according to diagram_type."""
    diagram_type = infer_diagram_type(scene)
    x, y, w, h = bbox
    bg_fill = tuple(max(0, c - 30) for c in accent)
    box_fill = (22, 22, 36)
    outline = tuple(min(255, c + 40) for c in accent)
    muted = (120, 120, 140)
    white = (240, 240, 245)

    p = _clamp(progress)

    if diagram_type == "status_code":
        code = _extract_status_code(scene) or 200
        cat, cat_color = _status_category(code)
        scale = _alpha(p, 0.1, 0.5)
        cx, cy = x + w // 2, y + h // 2 - 20
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
        left_x = x + 40
        right_x = x + w - box_w - 40
        mid_y = y + h // 2
        box_alpha = _alpha(p, 0.1, 0.35)
        if box_alpha > 0:
            _draw_rounded_box(
                draw,
                (left_x, mid_y - box_h // 2, left_x + box_w, mid_y + box_h // 2),
                box_fill,
                outline,
            )
            _draw_rounded_box(
                draw,
                (right_x, mid_y - box_h // 2, right_x + box_w, mid_y + box_h // 2),
                box_fill,
                outline,
            )
            draw.text((left_x + box_w // 2, mid_y - 10), "Client", fill=white, font=small_font, anchor="mm")
            draw.text((right_x + box_w // 2, mid_y - 10), "Server", fill=white, font=small_font, anchor="mm")
        req_p = _alpha(p, 0.35, 0.6)
        if req_p > 0:
            _draw_arrow(
                draw,
                (left_x + box_w + 8, mid_y - 15),
                (right_x - 8, mid_y - 15),
                accent,
                progress=req_p,
                label=req_label,
                label_font=small_font,
            )
        res_p = _alpha(p, 0.55, 0.8)
        if res_p > 0:
            code = _extract_status_code(scene)
            res_color = _status_category(code)[1] if code else (16, 185, 129)
            _draw_arrow(
                draw,
                (right_x - 8, mid_y + 15),
                (left_x + box_w + 8, mid_y + 15),
                res_color,
                progress=res_p,
                label=res_label,
                label_font=small_font,
            )
        return

    if diagram_type == "http_cache":
        labels = _diagram_labels(scene, 2, ["GET + If-Modified-Since", "304 Not Modified (no body)"])
        req_label, res_label = labels[0], labels[1]
        box_w, box_h = 150, 95
        left_x = x + 30
        right_x = x + w - box_w - 30
        mid_y = y + h // 2
        if _alpha(p, 0.1, 0.3) > 0:
            _draw_rounded_box(
                draw,
                (left_x, mid_y - box_h // 2, left_x + box_w, mid_y + box_h // 2),
                box_fill,
                outline,
            )
            _draw_rounded_box(
                draw,
                (right_x, mid_y - box_h // 2, right_x + box_w, mid_y + box_h // 2),
                box_fill,
                outline,
            )
            draw.text((left_x + box_w // 2, mid_y - 18), "Browser", fill=white, font=small_font, anchor="mm")
            cache_y = mid_y + 8
            _draw_rounded_box(
                draw,
                (left_x + 20, cache_y, left_x + box_w - 20, cache_y + 28),
                bg_fill,
                accent,
                radius=6,
            )
            draw.text((left_x + box_w // 2, cache_y + 14), "cached copy", fill=accent, font=small_font, anchor="mm")
            draw.text((right_x + box_w // 2, mid_y), "Server", fill=white, font=small_font, anchor="mm")
        req_p = _alpha(p, 0.3, 0.55)
        if req_p > 0:
            _draw_arrow(
                draw,
                (left_x + box_w + 6, mid_y - 12),
                (right_x - 6, mid_y - 12),
                accent,
                progress=req_p,
                label=req_label,
                label_font=small_font,
            )
        res_p = _alpha(p, 0.55, 0.8)
        if res_p > 0:
            _draw_arrow(
                draw,
                (right_x - 6, mid_y + 18),
                (left_x + box_w + 6, mid_y + 18),
                (245, 158, 11),
                progress=res_p,
                label=res_label,
                label_font=small_font,
            )
        return

    if diagram_type == "http_redirect":
        labels = _diagram_labels(scene, 3, ["GET /page", "302 Redirect", "follow redirect"])
        box_w, box_h = 130, 80
        y0 = y + h // 2 - box_h // 2
        positions = [x + 30, x + w // 2 - box_w // 2, x + w - box_w - 30]
        labels = ["Browser", "Server A", "Server B"]
        for i, (px, lbl) in enumerate(zip(positions, labels)):
            if _alpha(p, 0.1 + i * 0.12, 0.25 + i * 0.12) > 0:
                _draw_rounded_box(draw, (px, y0, px + box_w, y0 + box_h), box_fill, outline)
                draw.text((px + box_w // 2, y0 + box_h // 2), lbl, fill=white, font=small_font, anchor="mm")
        if _alpha(p, 0.4, 0.6) > 0:
            _draw_arrow(
                draw,
                (positions[0] + box_w + 4, y0 + box_h // 2),
                (positions[1] - 4, y0 + box_h // 2),
                accent,
                progress=_alpha(p, 0.4, 0.6),
                label=labels[0],
                label_font=small_font,
            )
        if _alpha(p, 0.62, 0.82) > 0:
            _draw_arrow(
                draw,
                (positions[1] + box_w // 2, y0 + box_h + 4),
                (positions[1] + box_w // 2, y0 + box_h + 50),
                (245, 158, 11),
                progress=_alpha(p, 0.62, 0.82),
                label=labels[1],
                label_font=small_font,
            )
            draw.text(
                (positions[1] + box_w // 2, y0 + box_h + 62),
                "Location: new-url",
                fill=muted,
                font=small_font,
                anchor="mm",
            )
        if _alpha(p, 0.82, 1.0) > 0:
            _draw_arrow(
                draw,
                (positions[1] - 4, y0 + box_h // 2),
                (positions[2] + box_w + 4, y0 + box_h // 2),
                (16, 185, 129),
                progress=_alpha(p, 0.82, 1.0),
                label=labels[2],
                label_font=small_font,
            )
        return

    if diagram_type == "http_error_client":
        code = _extract_status_code(scene) or 404
        cx, cy = x + w // 2, y + h // 2
        if _alpha(p, 0.1, 0.4) > 0:
            r = int(70 * _alpha(p, 0.1, 0.4))
            draw.ellipse((cx - r, cy - r - 10, cx + r, cy + r - 10), outline=(239, 68, 68), width=3)
            draw.text((cx, cy - 10), str(code), fill=(239, 68, 68), font=label_font, anchor="mm")
        if _alpha(p, 0.45, 0.7) > 0:
            draw.text((cx, cy + 60), "Client Error", fill=muted, font=small_font, anchor="mm")
            draw.text((cx, cy + 90), "request was valid — resource/problem on client side", fill=muted, font=small_font, anchor="mm")
        return

    if diagram_type == "http_error_server":
        code = _extract_status_code(scene) or 500
        cx = x + w // 2
        sy = y + 40
        if _alpha(p, 0.1, 0.35) > 0:
            _draw_rounded_box(draw, (cx - 90, sy, cx + 90, sy + 70), box_fill, (139, 92, 246))
            draw.text((cx, sy + 35), "Server", fill=white, font=small_font, anchor="mm")
        if _alpha(p, 0.35, 0.6) > 0:
            draw.text((cx, sy + 100), str(code), fill=(139, 92, 246), font=label_font, anchor="mm")
            draw.text((cx, sy + 150), "Server failed to fulfill a valid request", fill=muted, font=small_font, anchor="mm")
        return

    if diagram_type == "comparison":
        bullets = [str(b) for b in scene.get("visual_bullets", [])][:2]
        left_label = bullets[0] if bullets else "Option A"
        right_label = bullets[1] if len(bullets) > 1 else "Option B"
        gap = 30
        half_w = (w - gap) // 2
        ly = y + 20
        if _alpha(p, 0.1, 0.4) > 0:
            _draw_rounded_box(draw, (x, ly, x + half_w, y + h - 20), box_fill, accent)
            _draw_rounded_box(draw, (x + half_w + gap, ly, x + w, y + h - 20), box_fill, outline)
            draw.text((x + half_w // 2, ly + 40), left_label[:28], fill=white, font=small_font, anchor="mm")
            draw.text((x + half_w + gap + half_w // 2, ly + 40), right_label[:28], fill=white, font=small_font, anchor="mm")
            draw.text((x + half_w + gap // 2, ly + h // 2), "vs", fill=muted, font=label_font, anchor="mm")
        return

    if diagram_type == "flow_steps":
        label_src = _diagram_labels(scene, 3, [])
        bullets = label_src or [str(b) for b in scene.get("visual_bullets", [])][:3]
        if not bullets:
            bullets = ["Step 1", "Step 2", "Step 3"]
        step_w = min(200, (w - 80) // len(bullets))
        start_x = x + (w - step_w * len(bullets) - 40 * (len(bullets) - 1)) // 2
        for i, label in enumerate(bullets):
            reveal = _alpha(p, 0.1 + i * 0.2, 0.3 + i * 0.2)
            if reveal <= 0:
                continue
            px = start_x + i * (step_w + 40)
            py = y + h // 2 - 40
            _draw_rounded_box(draw, (px, py, px + step_w, py + 80), box_fill, outline)
            draw.text((px + step_w // 2, py + 25), f"{i + 1}", fill=accent, font=label_font, anchor="mm")
            draw.text((px + step_w // 2, py + 55), label[:20], fill=white, font=small_font, anchor="mm")
            if i < len(bullets) - 1 and _alpha(p, 0.25 + i * 0.2, 0.45 + i * 0.2) > 0:
                ax = px + step_w + 4
                _draw_arrow(
                    draw,
                    (ax, py + 40),
                    (ax + 32, py + 40),
                    muted,
                    progress=_alpha(p, 0.25 + i * 0.2, 0.45 + i * 0.2),
                )
        return

    if diagram_type == "list_items":
        bullets = [str(b) for b in scene.get("visual_bullets", [])][:4]
        for i, bullet in enumerate(bullets):
            reveal = _alpha(p, 0.1 + i * 0.15, 0.25 + i * 0.15)
            if reveal <= 0:
                continue
            py = y + 30 + i * 55
            _draw_rounded_box(draw, (x + 20, py, x + 50, py + 36), bg_fill, accent, radius=8)
            draw.text((x + 35, py + 18), str(i + 1), fill=accent, font=small_font, anchor="mm")
            draw.text((x + 70, py + 18), bullet[:42], fill=white, font=small_font, anchor="lm")
        return

    # concept — decorative accent nodes
    cx, cy = x + w // 2, y + h // 2
    for i, (dx, dy, delay) in enumerate([(0, 0, 0.1), (-80, -30, 0.2), (80, -30, 0.3), (-60, 50, 0.4), (60, 50, 0.5)]):
        r = int(28 * _alpha(p, delay, delay + 0.25))
        if r > 0:
            draw.ellipse((cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r), outline=accent, width=2)
    if _alpha(p, 0.55, 0.8) > 0:
        draw.text((cx, cy), str(scene.get("visual_title", "Concept"))[:24], fill=white, font=small_font, anchor="mm")
