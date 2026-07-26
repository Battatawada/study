"""One-scene diagram render smoke test — run on VPS as niche user."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RUN_ID = "smoke-diagram-test"
APP_ROOT = Path(os.environ.get("APP_ROOT", "/opt/retro-movies"))
runs = Path(os.environ.get("RUNS_DIR", APP_ROOT / "runs"))
inp = runs / RUN_ID / "inputs"
inp.mkdir(parents=True, exist_ok=True)

scene = {
    "scene_id": 1,
    "visual_title": "HTTP 304 Not Modified",
    "visual_bullets": ["Conditional response", "Uses browser cache"],
    "diagram_type": "http_cache",
    "diagram_prompt": "Browser checks cache, sends conditional GET, server returns 304",
    "diagram_labels": ["GET + If-Modified-Since", "304 Not Modified (no body)"],
    "accent_color": "#F59E0B",
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
(inp / "pipeline.json").write_text(
    (APP_ROOT / "config" / "pipeline.json").read_text(encoding="utf-8"), encoding="utf-8"
)
(inp / "state.json").write_text(
    json.dumps({"run_id": RUN_ID, "status": "pending"}), encoding="utf-8"
)
(runs / RUN_ID / "state.json").write_text(
    json.dumps({"run_id": RUN_ID, "status": "pending"}), encoding="utf-8"
)
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
slide = runs / RUN_ID / "work" / "slide_01.png"
print("final_video:", out, out.stat().st_size if out.exists() else "MISSING")
print("slide:", slide, slide.stat().st_size if slide.exists() else "MISSING")
