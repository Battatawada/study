"""Lower aligned plans to animation_spec + render_ir (beat-locked timelines)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

from sece.constants import RENDER_IR_VERSION

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from composition_motion.presets import resolve_animation_from_segment  # noqa: E402
from composition_motion.semantic_ops import compile_semantic_ops, lock_timeline_to_beat_ids  # noqa: E402


def _scene_dict_from_aligned(segment: dict[str, Any]) -> dict[str, Any]:
    scene: dict[str, Any] = {
        "scene_id": int(segment["segment_id"]),
        "visual_title": segment.get("visual_title", "Concept"),
        "visual_bullets": segment.get("visual_bullets", []),
        "diagram_type": segment.get("diagram_type", "concept"),
        "accent_color": segment.get("accent_color", "#3B82F6"),
        "narration": " ".join(b.get("text", "") for b in segment.get("beats", [])),
    }
    labels = []
    for ent in segment.get("entities", []):
        if ent.get("label"):
            labels.append(str(ent["label"]))
    if labels:
        scene["diagram_labels"] = labels[:4]
    if segment.get("visualization"):
        scene["visualization"] = segment["visualization"]
    if segment.get("algorithm_state"):
        scene["algorithm_state"] = segment["algorithm_state"]
    return scene


def lock_timeline_to_beats(
    spec: dict[str, Any],
    beats: list[dict[str, Any]],
    *,
    semantic_ops: list[dict[str, Any]] | None = None,
    pad_end_sec: float = 0.15,
) -> dict[str, Any]:
    """Assign timeline op start times to beat boundaries via trigger_beat_id."""
    return lock_timeline_to_beat_ids(
        spec,
        beats,
        semantic_ops=semantic_ops,
        pad_end_sec=pad_end_sec,
    )


def compile_segment_motion(segment: dict[str, Any]) -> dict[str, Any]:
    sid = int(segment["segment_id"])
    duration_sec = float(segment.get("duration_sec", 0.5))
    beats = segment.get("beats", [])
    semantic_ops = list(segment.get("semantic_ops", []))
    scene = _scene_dict_from_aligned(segment)

    spec = compile_semantic_ops(segment)
    if not spec.get("timeline"):
        spec = resolve_animation_from_segment(scene, duration_sec=None)
    if not spec.get("timeline"):
        spec = resolve_animation_from_segment(scene, duration_sec=duration_sec)

    if beats and spec.get("timeline"):
        spec = lock_timeline_to_beats(spec, beats, semantic_ops=semantic_ops)

    render_ir = {
        "schema_version": RENDER_IR_VERSION,
        "segment_id": sid,
        "duration_sec": duration_sec,
        "kind": spec.get("kind", "memory"),
        "timeline": spec.get("timeline", []),
        "values": spec.get("values"),
        "addresses": spec.get("addresses"),
        "left": spec.get("left"),
        "right": spec.get("right"),
        "layout_recipe": segment.get("layout_recipe", "stage_single"),
        "attention_plan": segment.get("attention_plan", []),
        "beat_locked": bool(beats),
    }

    return {
        "segment_id": sid,
        "duration_sec": duration_sec,
        "animation_spec": spec,
        "render_ir": render_ir,
        "beat_locked": bool(beats),
    }


def compile_render_ir_document(aligned_plan: dict[str, Any]) -> dict[str, Any]:
    segments_out: list[dict[str, Any]] = []
    for segment in aligned_plan.get("segments", []):
        segments_out.append(compile_segment_motion(segment))
    return {
        "schema_version": RENDER_IR_VERSION,
        "segments": segments_out,
    }
