"""Visualization resolution for compile-time motion (no VPS diagram_renderer)."""

from __future__ import annotations

from typing import Any

from composition_motion.planner import plan_from_visualization


def normalize_visualization(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("transitions") or raw.get("events") or raw.get("algorithm_state") or raw.get("state"):
        return raw
    if raw.get("visualization"):
        inner = raw["visualization"]
        return inner if isinstance(inner, dict) else None
    return None


def resolve_visualization_from_segment(segment: dict[str, Any]) -> dict[str, Any]:
    for key in ("visualization", "animation"):
        viz = normalize_visualization(segment.get(key))
        if viz:
            return viz
    if segment.get("algorithm_state"):
        return {"kind": "memory", "transitions": [{"state": segment["algorithm_state"]}]}
    return {}


def resolve_animation_from_segment(
    segment: dict[str, Any],
    *,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    prebuilt = segment.get("animation_spec")
    if isinstance(prebuilt, dict) and prebuilt.get("timeline") and segment.get("beat_locked"):
        return prebuilt
    render_ir = segment.get("render_ir")
    if isinstance(render_ir, dict) and render_ir.get("timeline") and segment.get("beat_locked"):
        return render_ir
    viz = resolve_visualization_from_segment(segment)
    if not viz:
        return {}
    return plan_from_visualization(viz, duration_sec=duration_sec)
