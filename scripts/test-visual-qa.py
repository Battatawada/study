"""Render semantic animation slides for visual QA."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vps"))

from animation_planner import plan_from_visualization  # noqa: E402
from animation_presets import resolve_animation_spec, resolve_visualization  # noqa: E402
from semantic_slide import build_semantic_slide_html  # noqa: E402

OUT = ROOT / "tmp-visual-qa"
OUT.mkdir(exist_ok=True)

SCENES = [
    {
        "scene_id": 1,
        "visual_title": "Contiguous Memory",
        "visual_bullets": ["Items sit side-by-side", "Predictable physical locations", "Instant math calculations"],
        "diagram_type": "memory_layout",
        "diagram_labels": ["RAM", "contiguous block"],
        "accent_color": "#3B82F6",
    },
    {
        "scene_id": 2,
        "visual_title": "Sequential Address Lookup",
        "visual_bullets": ["Sequential lockers", "Known start position", "Instant offset math"],
        "diagram_type": "array_access",
        "diagram_labels": ["base", "base + index × size", "→ locker [3]"],
        "accent_color": "#3B82F6",
    },
    {
        "scene_id": 3,
        "visual_title": "Array Insertion",
        "visual_bullets": ["Elements shift right", "Memory makes room", "O(n) cost"],
        "diagram_type": "memory_layout",
        "visualization": {
            "transitions": [
                {"state": {}},
                {"state": {"array": ["10", "20", "30", "40"]}},
                {"state": {"array": ["10", "20", "30", "40"], "highlight": [2]}},
                {"state": {"array": ["10", "20", None, "30", "40"], "highlight": [2]}},
                {"state": {"array": ["10", "20", "25", "30", "40"], "highlight": [2], "caption": "memory shifted"}},
            ],
        },
        "accent_color": "#10B981",
    },
]

for scene in SCENES:
    sid = scene["scene_id"]
    dur = 5.0
    viz = resolve_visualization(scene)
    spec = resolve_animation_spec(scene, duration_sec=dur)
    print(f"scene {sid}: {len(spec.get('timeline', []))} planned ops")
    html_path = OUT / f"semantic_{sid:02d}.html"
    html_path.write_text(build_semantic_slide_html(scene, duration_sec=dur), encoding="utf-8")
    (OUT / f"timeline_{sid:02d}.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")

print(f"\nOutput: {OUT}")
