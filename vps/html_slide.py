"""Generate self-contained HTML slides with CSS animations for Xvfb capture."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from diagram_renderer import infer_diagram_type

DEFAULT_BG = "#0f0f1a"
DEFAULT_ACCENT = "#3B82F6"
BULLET_COLOR = "#A0A0B0"
WATERMARK_COLOR = "#3a3a4a"

_SELF_CONTAINED = frozenset({"list_items", "warning_icons", "status_code"})


def _esc(text: str) -> str:
    return html.escape(str(text).strip())


def _labels(scene: dict[str, Any], count: int, defaults: list[str]) -> list[str]:
    raw = scene.get("diagram_labels", [])
    if isinstance(raw, str):
        raw = [raw]
    labels = [str(x).strip() for x in raw if str(x).strip()][:count]
    while len(labels) < count:
        labels.append(defaults[len(labels)] if len(labels) < len(defaults) else "")
    return labels


def _show_bullets(scene: dict[str, Any], bullets: list[str]) -> bool:
    if not bullets:
        return False
    return infer_diagram_type(scene) not in _SELF_CONTAINED


def _diagram_html(scene: dict[str, Any], accent: str) -> str:
    dtype = infer_diagram_type(scene)
    labels = _labels(scene, 4, [])
    bullets = [str(b) for b in scene.get("visual_bullets", [])][:4]

    if dtype == "memory_layout":
        cells = "".join(
            f'<div class="mem-cell" style="animation-delay:{0.15 + i * 0.12:.2f}s">'
            f'<span class="mem-addr">0x{i * 8:03X}</span></div>'
            for i in range(6)
        )
        caption = _esc(labels[1] if len(labels) > 1 else "contiguous block")
        return f'<div class="diagram memory-layout"><div class="mem-label">{_esc(labels[0] or "RAM")}</div><div class="mem-cells">{cells}</div><div class="mem-caption anim-fade" style="animation-delay:1.1s">{caption}</div></div>'

    if dtype == "array_access":
        lockers = "".join(
            f'<div class="locker{" locker-target" if i == 3 else ""}" style="animation-delay:{0.1 + i * 0.1:.2f}s">'
            f'<span class="locker-idx">[{i}]</span><span class="locker-id">L{i}</span></div>'
            for i in range(5)
        )
        math_lbl = _esc(labels[1] if len(labels) > 1 else "base + index × size")
        result = _esc(labels[2] if len(labels) > 2 else "→ target locker")
        return (
            f'<div class="diagram array-access"><div class="array-base anim-fade">{_esc(labels[0] or "base address")}</div>'
            f'<div class="lockers">{lockers}</div>'
            f'<div class="array-math anim-fade" style="animation-delay:0.8s">{math_lbl}</div>'
            f'<div class="array-result anim-fade" style="animation-delay:1.1s">{result}</div></div>'
        )

    if dtype == "warning_icons":
        items = labels or bullets or ["Issue 1", "Issue 2", "Issue 3"]
        icons = ["DB", "!", "MEM"]
        cards = "".join(
            f'<div class="warn-card" style="animation-delay:{0.15 + i * 0.2:.2f}s">'
            f'<div class="warn-icon">{icons[i % len(icons)]}</div>'
            f'<div class="warn-label">{_esc(item)}</div></div>'
            for i, item in enumerate(items[:3])
        )
        return f'<div class="diagram warning-icons">{cards}</div>'

    if dtype == "flow_steps":
        steps = [lbl for lbl in (labels or bullets or ["Step 1", "Step 2", "Step 3"]) if lbl.strip()]
        rows = "".join(
            f'<div class="flow-step" style="animation-delay:{0.1 + i * 0.18:.2f}s">'
            f'<span class="flow-num">{i + 1}</span><span class="flow-label">{_esc(lbl)}</span></div>'
            + (f'<div class="flow-arrow anim-fade" style="animation-delay:{0.2 + i * 0.18:.2f}s">↓</div>' if i < len(steps) - 1 else "")
            for i, lbl in enumerate(steps)
        )
        return f'<div class="diagram flow-steps">{rows}</div>'

    if dtype == "list_items":
        rows = "".join(
            f'<div class="list-row" style="animation-delay:{0.1 + i * 0.15:.2f}s">'
            f'<span class="list-num">{i + 1}</span><span class="list-text">{_esc(b)}</span></div>'
            for i, b in enumerate(bullets)
        )
        return f'<div class="diagram list-items">{rows}</div>'

    if dtype == "linked_nodes":
        nodes = labels or ["Head", "A", "B", "null"]
        parts = []
        for i, lbl in enumerate(nodes[:4]):
            parts.append(f'<div class="node" style="animation-delay:{0.1 + i * 0.15:.2f}s">{_esc(lbl)}</div>')
            if i < min(3, len(nodes) - 1):
                parts.append(f'<div class="node-arrow anim-fade" style="animation-delay:{0.18 + i * 0.15:.2f}s">→</div>')
        return f'<div class="diagram linked-nodes">{"".join(parts)}</div>'

    if dtype == "comparison":
        left = _esc(bullets[0] if bullets else labels[0] if labels else "Option A")
        right = _esc(bullets[1] if len(bullets) > 1 else labels[1] if len(labels) > 1 else "Option B")
        return (
            f'<div class="diagram comparison">'
            f'<div class="cmp-box cmp-left anim-slide" style="animation-delay:0.1s">{left}</div>'
            f'<div class="cmp-vs anim-fade" style="animation-delay:0.3s">vs</div>'
            f'<div class="cmp-box cmp-right anim-slide" style="animation-delay:0.2s">{right}</div>'
            f'</div>'
        )

    if dtype == "http_request":
        req = _esc(labels[0] if labels else "Request")
        res = _esc(labels[1] if len(labels) > 1 else "Response")
        return (
            f'<div class="diagram http-request">'
            f'<div class="http-box anim-slide" style="animation-delay:0.1s">Client</div>'
            f'<div class="http-arrow anim-draw" style="animation-delay:0.35s">→ {req}</div>'
            f'<div class="http-box anim-slide" style="animation-delay:0.2s">Server</div>'
            f'<div class="http-arrow back anim-draw" style="animation-delay:0.6s">← {res}</div>'
            f'</div>'
        )

    # concept / fallback — diagram_prompt is internal metadata, never shown on slide
    title = _esc(scene.get("visual_title", "Concept"))
    label_src = labels or bullets[:3]
    nodes = "".join(
        f'<div class="concept-node" style="animation-delay:{0.1 + i * 0.12:.2f}s">'
        f'{_esc(label_src[i - 1]) if i > 0 and i - 1 < len(label_src) else ""}</div>'
        for i in range(5)
    )
    return (
        f'<div class="diagram concept">{nodes}'
        f'<div class="concept-title anim-fade" style="animation-delay:0.5s">{title}</div></div>'
    )


_BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; background: __BG__; color: #fff; font-family: 'Segoe UI', system-ui, sans-serif; }
.accent-bar { position: absolute; left: 0; top: 0; width: 8px; height: 100%; background: __ACCENT__; }
.title { font-size: 64px; font-weight: 700; padding: 72px 80px 0 80px; line-height: 1.15; }
.panel { margin: 28px 48px 0; height: 520px; border: 2px solid __ACCENT__; border-radius: 20px; background: rgba(18,18,28,0.95); position: relative; overflow: hidden; }
.panel::before { content: ''; position: absolute; inset: 0; background-image: radial-gradient(circle, rgba(60,60,80,0.35) 1px, transparent 1px); background-size: 28px 28px; opacity: 0.5; }
.diagram { position: relative; z-index: 1; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; flex-direction: column; }
.bullets { padding: 32px 80px 0; }
.bullet { font-size: 32px; color: __BULLET__; margin-bottom: 12px; opacity: 0; animation: fadeUp 0.5s ease forwards; }
.watermark { position: absolute; bottom: 40px; right: 40px; font-size: 24px; color: __WM__; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes slideIn { from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: none; } }
@keyframes popIn { from { opacity: 0; transform: translateY(20px) scale(0.9); } to { opacity: 1; transform: none; } }
@keyframes drawIn { from { opacity: 0; width: 0; } to { opacity: 1; width: auto; } }
.anim-fade { opacity: 0; animation: fadeUp 0.6s ease forwards; }
.anim-slide { opacity: 0; animation: slideIn 0.6s ease forwards; }
.anim-draw { opacity: 0; animation: fadeUp 0.5s ease forwards; }
.mem-cells { display: flex; gap: 10px; }
.mem-cell { width: 84px; height: 52px; border: 2px solid __ACCENT__; border-radius: 8px; display: flex; align-items: center; justify-content: center; opacity: 0; animation: popIn 0.5s ease forwards; background: rgba(22,22,36,0.9); }
.mem-addr { font-size: 14px; color: #a0a0b0; }
.mem-label { position: absolute; top: 36px; color: #a0a0b0; font-size: 22px; }
.mem-caption { margin-top: 24px; font-size: 28px; font-weight: 600; }
.lockers { display: flex; gap: 8px; }
.locker { width: 72px; height: 56px; border: 2px solid __ACCENT__; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0; animation: popIn 0.5s ease forwards; background: rgba(22,22,36,0.9); }
.locker-target { border-color: #fff; box-shadow: 0 0 20px __ACCENT__; }
.locker-idx { font-size: 16px; font-weight: 600; }
.locker-id { font-size: 12px; color: #a0a0b0; }
.array-base { position: absolute; top: 120px; left: 120px; color: __ACCENT__; font-size: 20px; }
.array-math { margin-top: 20px; font-size: 28px; font-weight: 600; }
.array-result { margin-top: 8px; font-size: 28px; color: __ACCENT__; font-weight: 600; }
.warn-card { display: flex; flex-direction: column; align-items: center; gap: 16px; margin: 0 24px; opacity: 0; animation: popIn 0.6s ease forwards; }
.warn-icon { width: 72px; height: 72px; border: 2px solid #ef4444; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 700; color: #ef4444; background: rgba(40,18,22,0.9); }
.warn-label { font-size: 20px; text-align: center; max-width: 200px; }
.warning-icons { flex-direction: row; }
.flow-steps { align-items: stretch; padding: 40px 80px; width: 100%; }
.flow-step { display: flex; align-items: center; gap: 20px; padding: 16px 24px; border: 2px solid __ACCENT__; border-radius: 12px; background: rgba(22,22,36,0.9); opacity: 0; animation: slideIn 0.5s ease forwards; margin-bottom: 4px; }
.flow-num { width: 36px; height: 36px; border-radius: 50%; background: __ACCENT__; color: #0f0f1a; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.flow-label { font-size: 24px; }
.flow-arrow { text-align: center; color: #666; font-size: 20px; margin: 2px 0; }
.list-items { align-items: stretch; padding: 40px 80px; width: 100%; gap: 12px; }
.list-row { display: flex; align-items: center; gap: 20px; opacity: 0; animation: slideIn 0.5s ease forwards; }
.list-num { width: 36px; height: 36px; border-radius: 8px; border: 2px solid __ACCENT__; display: flex; align-items: center; justify-content: center; color: __ACCENT__; font-weight: 600; flex-shrink: 0; }
.list-text { font-size: 26px; }
.linked-nodes { flex-direction: row; gap: 8px; }
.node { padding: 16px 28px; border: 2px solid __ACCENT__; border-radius: 10px; background: rgba(22,22,36,0.9); font-size: 22px; opacity: 0; animation: popIn 0.5s ease forwards; }
.node-arrow { font-size: 28px; color: __ACCENT__; }
.comparison { flex-direction: row; gap: 40px; }
.cmp-box { width: 360px; min-height: 160px; border: 2px solid __ACCENT__; border-radius: 14px; padding: 32px; font-size: 24px; display: flex; align-items: center; justify-content: center; text-align: center; background: rgba(22,22,36,0.9); }
.cmp-vs { font-size: 36px; color: #666; font-weight: 700; }
.http-request { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: auto auto; gap: 20px 60px; padding: 60px; width: 100%; }
.http-box { padding: 24px 40px; border: 2px solid __ACCENT__; border-radius: 12px; text-align: center; font-size: 24px; background: rgba(22,22,36,0.9); }
.http-arrow { grid-column: 1 / -1; text-align: center; font-size: 22px; color: __ACCENT__; }
.http-arrow.back { color: #10b981; }
.concept { position: relative; }
.concept-node { position: absolute; width: 48px; height: 48px; border: 2px solid __ACCENT__; border-radius: 50%; opacity: 0; animation: popIn 0.5s ease forwards; }
.concept-node:nth-child(1) { left: 50%; top: 40%; transform: translate(-50%,-50%); }
.concept-node:nth-child(2) { left: 30%; top: 25%; }
.concept-node:nth-child(3) { left: 70%; top: 25%; }
.concept-node:nth-child(4) { left: 35%; top: 60%; }
.concept-node:nth-child(5) { left: 65%; top: 60%; }
.concept-title { font-size: 32px; font-weight: 700; margin-top: 120px; }
.concept-prompt { font-size: 20px; color: #a0a0b0; margin-top: 12px; max-width: 700px; text-align: center; }
"""


def build_slide_html(
    scene: dict[str, Any],
    *,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
) -> str:
    """Return a complete HTML document for one scene."""
    accent = str(scene.get("accent_color", DEFAULT_ACCENT))
    title = _esc(scene.get("visual_title", "Concept"))
    bullets = [str(b).strip() for b in scene.get("visual_bullets", []) if str(b).strip()][:3]
    show_bullets = _show_bullets(scene, bullets)

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


def write_slide_html(
    scene: dict[str, Any],
    dest: Path,
    *,
    bg_color: str = DEFAULT_BG,
    channel_name: str = "Byte Glossary",
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build_slide_html(scene, bg_color=bg_color, channel_name=channel_name), encoding="utf-8")
    return dest


def write_scene_manifest(scenes: list[dict[str, Any]], dest: Path) -> Path:
    """Optional debug manifest listing scene HTML paths."""
    dest.write_text(json.dumps({"scenes": [int(s.get("scene_id", i + 1)) for i, s in enumerate(scenes)]}, indent=2), encoding="utf-8")
    return dest
