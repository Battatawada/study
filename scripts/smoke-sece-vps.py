"""SECE render smoke test — render_ir.json + HTML capture on VPS."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RUN_ID = "smoke-sece-test"
APP_ROOT = Path(os.environ.get("APP_ROOT", "/opt/retro-movies"))
runs = Path(os.environ.get("RUNS_DIR", APP_ROOT / "runs"))
inp = runs / RUN_ID / "inputs"
inp.mkdir(parents=True, exist_ok=True)

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from composition_motion.semantic_ops import compile_semantic_ops  # noqa: E402

scene = {
    "scene_id": 1,
    "visual_title": "Array Access",
    "visual_bullets": ["base + index × size"],
    "diagram_type": "array_access",
    "diagram_labels": ["base", "index", "target"],
    "accent_color": "#3B82F6",
}

segment = {
    "segment_id": 1,
    "duration_sec": 4.0,
    "entities": [
        {"entity_id": "s1_cell_0", "type": "memory_cell", "label": "[0]"},
        {"entity_id": "s1_cell_1", "type": "memory_cell", "label": "[1]"},
        {"entity_id": "s1_cell_2", "type": "memory_cell", "label": "[2]"},
        {"entity_id": "s1_cell_3", "type": "memory_cell", "label": "[3]"},
    ],
    "beats": [
        {"beat_id": "s1_b1", "start_sec": 0.0, "end_sec": 2.0, "text": "Arrays use base address.", "kind": "explanation"},
        {"beat_id": "s1_b2", "start_sec": 2.0, "end_sec": 4.0, "text": "Index selects the cell.", "kind": "explanation"},
    ],
    "semantic_ops": [
        {"op": "allocate", "entity_ids": ["s1_cell_0", "s1_cell_1", "s1_cell_2", "s1_cell_3"], "trigger_beat_id": "s1_b1"},
        {"op": "highlight", "entity_id": "s1_cell_2", "trigger_beat_id": "s1_b2"},
    ],
    "layout_recipe": "memory_row",
}

anim_spec = compile_semantic_ops(segment)
render_ir_body = {
    "schema_version": "1.0",
    "segment_id": 1,
    "duration_sec": 4.0,
    "kind": anim_spec.get("kind", "memory"),
    "timeline": anim_spec.get("timeline", []),
    "values": anim_spec.get("values"),
    "addresses": anim_spec.get("addresses"),
    "beat_locked": True,
    "layout": {
        "schema_version": "1.0",
        "segment_id": 1,
        "recipe": "memory_row",
        "stage": {"width": 1824, "height": 516},
        "entities": [
            {"entity_id": "s1_cell_0", "type": "memory_cell", "label": "[0]", "box": {"x": 700, "y": 230, "w": 88, "h": 56}, "z_index": 10},
            {"entity_id": "s1_cell_1", "type": "memory_cell", "label": "[1]", "box": {"x": 798, "y": 230, "w": 88, "h": 56}, "z_index": 11},
            {"entity_id": "s1_cell_2", "type": "memory_cell", "label": "[2]", "box": {"x": 896, "y": 230, "w": 88, "h": 56}, "z_index": 12},
            {"entity_id": "s1_cell_3", "type": "memory_cell", "label": "[3]", "box": {"x": 994, "y": 230, "w": 88, "h": 56}, "z_index": 13},
        ],
    },
    "typography": {
        "segment_title": {"family": "Segoe UI", "size": 64, "weight": 700},
        "entity_label": {"family": "Segoe UI", "size": 20, "weight": 600},
        "entity_address": {"family": "Segoe UI", "size": 13, "weight": 400},
        "caption": {"family": "Segoe UI", "size": 24, "weight": 600},
    },
    "attention_timeline": [
        {
            "beat_id": "s1_b1",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "primary_entity_id": "s1_cell_0",
            "focus_point": {"x": 744.0, "y": 258.0},
            "salience": [
                {"entity_id": "s1_cell_0", "weight": 1.0},
                {"entity_id": "s1_cell_1", "weight": 0.45},
            ],
        },
        {
            "beat_id": "s1_b2",
            "start_sec": 2.0,
            "end_sec": 4.0,
            "primary_entity_id": "s1_cell_2",
            "focus_point": {"x": 940.0, "y": 258.0},
            "salience": [
                {"entity_id": "s1_cell_2", "weight": 1.0},
                {"entity_id": "s1_cell_0", "weight": 0.45},
            ],
        },
    ],
    "camera": [
        {"at_sec": 0.0, "duration_sec": 2.0, "center_x": 744.0, "center_y": 258.0, "zoom": 1.05},
        {"at_sec": 2.0, "duration_sec": 2.0, "center_x": 940.0, "center_y": 258.0, "zoom": 1.12},
    ],
}

(inp / "scene_clips.json").write_text(
    json.dumps({"render_mode": "slides", "scenes": [scene]}), encoding="utf-8"
)
(inp / "scene_durations.json").write_text(
    json.dumps([{"scene_id": 1, "duration_sec": 4.0}]), encoding="utf-8"
)
(inp / "metadata.json").write_text(
    json.dumps({"niche": "Byte Glossary", "render_mode": "slides"}), encoding="utf-8"
)
(inp / "render_ir.json").write_text(
    json.dumps({
        "schema_version": "1.0",
        "segments": [{
            "segment_id": 1,
            "duration_sec": 4.0,
            "animation_spec": anim_spec,
            "render_ir": render_ir_body,
            "beat_locked": True,
        }],
    }, indent=2),
    encoding="utf-8",
)

pipeline = json.loads((APP_ROOT / "config" / "pipeline.json").read_text(encoding="utf-8"))
pipeline["render_engine"] = "html"
pipeline["slide_capture_fps"] = 24
pipeline["composition_engine"] = {"enabled": True, "fail_on_validation_error": True}
(inp / "pipeline.json").write_text(json.dumps(pipeline, indent=2), encoding="utf-8")

(inp / "state.json").write_text(json.dumps({"run_id": RUN_ID, "status": "pending"}), encoding="utf-8")
(runs / RUN_ID / "state.json").write_text(json.dumps({"run_id": RUN_ID, "status": "pending"}), encoding="utf-8")

narr = inp / "narration.mp3"
subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "4", "-q:a", "9", str(narr)],
    check=True,
    capture_output=True,
)

sys.path.insert(0, str(APP_ROOT / "vps"))
from phase3_render import _run_slide_render_sync  # noqa: E402

_run_slide_render_sync(RUN_ID, runs_dir=runs)
out = runs / RUN_ID / "output" / "final_video.mp4"
html = runs / RUN_ID / "work" / "scene_01.html"
clip = runs / RUN_ID / "work" / "clip_01.mp4"
print("final_video:", out, out.stat().st_size if out.exists() else "MISSING")
print("clip:", clip, clip.stat().st_size if clip.exists() else "MISSING")
print("html:", html, html.exists())
if not out.exists() or out.stat().st_size < 10000:
    raise SystemExit("SECE smoke render failed")
