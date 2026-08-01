"""Load render_ir.json as authoritative scene list when SECE is enabled."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def composition_enabled(pipeline: dict[str, Any]) -> bool:
    sece = pipeline.get("composition_engine", {})
    if isinstance(sece, bool):
        return sece
    return bool(sece.get("enabled", False))


def load_render_scenes(
    inputs: Path,
    pipeline: dict[str, Any],
    *,
    require_ir: bool = False,
) -> tuple[list[dict[str, Any]], dict[int, float], bool]:
    """
    Merge scene_clips metadata with render_ir segments.
    Returns (scenes, dur_by_id, used_render_ir).
    """
    clips_path = inputs / "scene_clips.json"
    durations_path = inputs / "scene_durations.json"
    scene_clips = json.loads(clips_path.read_text(encoding="utf-8"))
    legacy_scenes = scene_clips.get("scenes", scene_clips if isinstance(scene_clips, list) else [])
    scene_by_id = {int(s["scene_id"]): dict(s) for s in legacy_scenes}

    durations = json.loads(durations_path.read_text(encoding="utf-8"))
    dur_by_id = {int(d["scene_id"]): float(d["duration_sec"]) for d in durations}

    ir_path = inputs / "render_ir.json"
    sece_on = composition_enabled(pipeline)
    if not sece_on or not ir_path.exists():
        if require_ir and sece_on:
            raise FileNotFoundError("composition_engine enabled but render_ir.json missing in inputs")
        return legacy_scenes, dur_by_id, False

    ir_doc = json.loads(ir_path.read_text(encoding="utf-8"))
    ir_segments = ir_doc.get("segments", [])
    if not ir_segments:
        if require_ir:
            raise ValueError("render_ir.json has no segments")
        return legacy_scenes, dur_by_id, False

    scenes: list[dict[str, Any]] = []
    for ir_row in ir_segments:
        sid = int(ir_row.get("segment_id", ir_row.get("scene_id", 0)))
        scene = dict(scene_by_id.get(sid, {}))
        scene["scene_id"] = sid
        scene["render_ir"] = ir_row.get("render_ir", {})
        scene["animation_spec"] = ir_row.get("animation_spec", {})
        scene["beat_locked"] = ir_row.get("beat_locked", False)
        if ir_row.get("duration_sec"):
            dur_by_id[sid] = float(ir_row["duration_sec"])
        scenes.append(scene)

    return scenes, dur_by_id, True


def rerender_segment_ids(pipeline: dict[str, Any]) -> set[int]:
    raw = pipeline.get("rerender_segment_ids") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]
    return {int(x) for x in raw}
