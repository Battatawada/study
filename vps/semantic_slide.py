"""HTML slides with semantic canvas animations — motion represents computation."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from animation_presets import resolve_animation_spec, uses_semantic_animation

from html_slide import (
    BULLET_COLOR,
    DEFAULT_ACCENT,
    DEFAULT_BG,
    WATERMARK_COLOR,
    _diagram_html,
    _esc,
    _show_bullets,
)

_ALGO_VIZ_JS = (Path(__file__).resolve().parent / "algo_viz.js").read_text(encoding="utf-8")

_PANEL_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; background: __BG__; color: #fff; font-family: 'Segoe UI', system-ui, sans-serif; }
.accent-bar { position: absolute; left: 0; top: 0; width: 8px; height: 100%; background: __ACCENT__; }
.title { font-size: 64px; font-weight: 700; padding: 72px 80px 0 80px; line-height: 1.15; }
.panel { margin: 28px 48px 0; height: 520px; border: 2px solid __ACCENT__; border-radius: 20px; background: rgba(18,18,28,0.95); position: relative; overflow: hidden; }
.panel::before { content: ''; position: absolute; inset: 0; background-image: radial-gradient(circle, rgba(60,60,80,0.35) 1px, transparent 1px); background-size: 28px 28px; opacity: 0.5; pointer-events: none; }
#viz { position: relative; z-index: 1; display: block; width: 100%; height: 100%; }
.bullets { padding: 32px 80px 0; }
.bullet { font-size: 32px; color: __BULLET__; opacity: 0.55; }
.watermark { position: absolute; bottom: 40px; right: 40px; font-size: 24px; color: __WM__; }
"""


def build_semantic_slide_html(
    scene: dict[str, Any],
    *,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
    duration_sec: float | None = None,
) -> str:
    accent = str(scene.get("accent_color", DEFAULT_ACCENT))
    title = _esc(scene.get("visual_title", "Concept"))
    bullets = [str(b).strip() for b in scene.get("visual_bullets", []) if str(b).strip()][:3]
    show_bullets = _show_bullets(scene, bullets)

    spec = resolve_animation_spec(scene, duration_sec=duration_sec)
    spec_json = json.dumps(spec).replace("</", "<\\/")

    css = (
        _PANEL_CSS.replace("__BG__", bg_color)
        .replace("__ACCENT__", accent)
        .replace("__BULLET__", BULLET_COLOR)
        .replace("__WM__", WATERMARK_COLOR)
    )

    bullet_html = ""
    if show_bullets:
        bullet_html = '<div class="bullets">' + "".join(
            f'<div class="bullet">• {_esc(b)}</div>' for b in bullets
        ) + "</div>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>
<body>
<div class="accent-bar"></div>
<div class="title">{title}</div>
<div class="panel"><canvas id="viz" width="1824" height="516"></canvas></div>
{bullet_html}
<div class="watermark">{_esc(channel_name)}</div>
<script>{_ALGO_VIZ_JS}</script>
<script>
const SPEC = {spec_json};
const ACCENT = {json.dumps(accent)};
const canvas = document.getElementById('viz');
window.__initAlgoViz(canvas, SPEC, ACCENT);
</script>
</body></html>"""


def build_slide_html(
    scene: dict[str, Any],
    *,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
    duration_sec: float | None = None,
    semantic: bool | None = None,
) -> str:
    """Build slide HTML — semantic canvas when supported, else CSS templates."""
    use_semantic = semantic if semantic is not None else uses_semantic_animation(scene)
    if use_semantic:
        return build_semantic_slide_html(
            scene, bg_color=bg_color, channel_name=channel_name, duration_sec=duration_sec
        )

    # Legacy CSS path
    accent = str(scene.get("accent_color", DEFAULT_ACCENT))
    title = _esc(scene.get("visual_title", "Concept"))
    bullets = [str(b).strip() for b in scene.get("visual_bullets", []) if str(b).strip()][:3]
    show_bullets = _show_bullets(scene, bullets)

    from html_slide import _BASE_CSS

    css = (
        _BASE_CSS.replace("__BG__", bg_color)
        .replace("__ACCENT__", accent)
        .replace("__BULLET__", BULLET_COLOR)
        .replace("__WM__", WATERMARK_COLOR)
    )
    bullet_html = ""
    if show_bullets:
        bullet_html = '<div class="bullets">' + "".join(
            f'<div class="bullet" style="animation-delay:{0.9 + i * 0.12:.2f}s">• {_esc(b)}</div>'
            for i, b in enumerate(bullets)
        ) + "</div>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>
<body>
<div class="accent-bar"></div>
<div class="title">{title}</div>
<div class="panel">{_diagram_html(scene, accent)}</div>
{bullet_html}
<div class="watermark">{_esc(channel_name)}</div>
</body></html>"""
