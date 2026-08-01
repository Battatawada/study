"""Full SECE compile chain: composition → layout → attention → motion → camera → render IR."""

from __future__ import annotations

from typing import Any

from sece.attention import resolve_attention_timeline
from sece.camera import compile_camera_channel
from sece.composition import build_composition_spec
from sece.constants import RENDER_IR_VERSION, SCHEMA_VERSION
from sece.layout import build_layout_spec
from sece.motion_compiler import compile_segment_motion
from sece.performance import compile_segment_performance, performance_enabled
from sece.typography import build_typography_spec


def compile_segment_full(
    segment: dict[str, Any],
    *,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one aligned segment through all deterministic stages."""
    typography_doc = build_typography_spec(pipeline)
    composition = build_composition_spec(segment)
    layout = build_layout_spec(segment, composition)
    attention = resolve_attention_timeline(segment, layout, composition)
    motion = compile_segment_motion(segment)
    camera = compile_camera_channel(attention, duration_sec=float(segment.get("duration_sec", 0.5)))

    render_ir = dict(motion.get("render_ir", {}))
    render_ir["schema_version"] = RENDER_IR_VERSION
    render_ir["layout"] = layout
    render_ir["composition"] = composition
    render_ir["attention_timeline"] = attention.get("timeline", [])
    render_ir["camera"] = camera.get("channel", [])
    render_ir["typography"] = typography_doc.get("roles", {})

    performance_spec = None
    if performance_enabled(pipeline):
        perf = compile_segment_performance(
            segment,
            render_ir=render_ir,
            attention=attention,
            camera=camera,
            animation_spec=motion.get("animation_spec", {}),
            pipeline=pipeline,
        )
        render_ir = perf["render_ir"]
        performance_spec = {k: v for k, v in perf.items() if k != "render_ir"}

    return {
        "segment_id": int(segment["segment_id"]),
        "duration_sec": float(segment.get("duration_sec", render_ir.get("duration_sec", 0.5))),
        "animation_spec": motion.get("animation_spec", {}),
        "render_ir": render_ir,
        "beat_locked": motion.get("beat_locked", False),
        "composition_spec": composition,
        "layout_spec": layout,
        "attention_timeline": attention,
        "camera_channel": camera,
        "typography_spec": typography_doc,
        "performance_spec": performance_spec,
    }


def compile_full_document(
    aligned_plan: dict[str, Any],
    *,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    segments_out: list[dict[str, Any]] = []
    composition_segments: list[dict[str, Any]] = []
    layout_segments: list[dict[str, Any]] = []
    attention_segments: list[dict[str, Any]] = []
    camera_segments: list[dict[str, Any]] = []

    performance_segments: list[dict[str, Any]] = []

    typography_doc = build_typography_spec(pipeline)

    for segment in aligned_plan.get("segments", []):
        row = compile_segment_full(segment, pipeline=pipeline)
        segments_out.append({
            "segment_id": row["segment_id"],
            "duration_sec": row["duration_sec"],
            "animation_spec": row["animation_spec"],
            "render_ir": row["render_ir"],
            "beat_locked": row["beat_locked"],
        })
        composition_segments.append(row["composition_spec"])
        layout_segments.append(row["layout_spec"])
        attention_segments.append(row["attention_timeline"])
        camera_segments.append(row["camera_channel"])
        if row.get("performance_spec"):
            performance_segments.append(row["performance_spec"])

    result: dict[str, Any] = {
        "schema_version": RENDER_IR_VERSION,
        "typography": typography_doc,
        "composition": {"schema_version": SCHEMA_VERSION, "segments": composition_segments},
        "layout": {"schema_version": SCHEMA_VERSION, "segments": layout_segments},
        "attention": {"schema_version": SCHEMA_VERSION, "segments": attention_segments},
        "camera": {"schema_version": SCHEMA_VERSION, "segments": camera_segments},
        "render_ir": {"schema_version": RENDER_IR_VERSION, "segments": segments_out},
    }
    if performance_segments:
        result["performance"] = {
            "schema_version": "1.0",
            "enabled": True,
            "segments": performance_segments,
        }
    return result
