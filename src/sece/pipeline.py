"""SECE orchestration hooks for Phase 1 / Phase 2 / compile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sece.align import align_visual_plan_to_beats
from sece.beats import build_beats_document
from sece.compile import compile_full_document
from sece.segments import build_segments_from_scene_clips, segment_durations_from_scene_durations
from sece.topic_knowledge import build_topic_knowledge_stub
from sece.validate import (
    ValidationError,
    run_all_pre_render,
    validate_segments,
    validate_visual_plan,
)
from sece.visual_plan import build_visual_plan_from_scene_clips


def _save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def composition_enabled(pipeline: dict[str, Any]) -> bool:
    sece = pipeline.get("composition_engine", {})
    if isinstance(sece, bool):
        return sece
    return bool(sece.get("enabled", False))


def run_post_phase1(
    out_dir: Path,
    scene_clips: list[dict[str, Any]],
    *,
    topic_slug: str,
    topic_title: str,
    pipeline: dict[str, Any],
) -> None:
    if not composition_enabled(pipeline):
        return

    pipeline_snapshot = out_dir / "pipeline.json"
    if not pipeline_snapshot.exists():
        import shutil
        from common import CONFIG

        src = CONFIG / "pipeline.json"
        if src.exists():
            shutil.copy(src, pipeline_snapshot)

    segments_doc = build_segments_from_scene_clips(scene_clips, topic_slug=topic_slug)
    tkd = build_topic_knowledge_stub(
        topic_slug=topic_slug,
        topic_title=topic_title,
        scene_clips=scene_clips,
    )
    visual_plan = build_visual_plan_from_scene_clips(scene_clips, segments_doc)

    _save(out_dir / "segments.json", segments_doc)
    _save(out_dir / "topic_knowledge.json", tkd)
    _save(out_dir / "visual_plan.json", visual_plan)

    reports = [
        validate_segments(segments_doc),
        validate_visual_plan(visual_plan, segments_doc),
    ]
    _save(out_dir / "validation_report_phase1.json", {
        "reports": reports,
        "status": "PASS" if all(r["status"] == "PASS" for r in reports) else "FAIL",
    })


def run_post_phase2(
    out_dir: Path,
    *,
    pipeline: dict[str, Any],
) -> None:
    if not composition_enabled(pipeline):
        return

    segments_path = out_dir / "segments.json"
    if not segments_path.exists():
        scene_clips_path = out_dir / "scene_clips.json"
        if scene_clips_path.exists():
            clip_data = json.loads(scene_clips_path.read_text(encoding="utf-8"))
            meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
            segments_doc = build_segments_from_scene_clips(
                clip_data.get("scenes", []),
                topic_slug=str(meta.get("topic_slug", "")),
            )
            _save(out_dir / "segments.json", segments_doc)
        else:
            return

    segments_doc = json.loads(segments_path.read_text(encoding="utf-8"))
    scene_durations = json.loads((out_dir / "scene_durations.json").read_text(encoding="utf-8"))
    segment_durations_doc = segment_durations_from_scene_durations(scene_durations)
    _save(out_dir / "segment_durations.json", segment_durations_doc)

    word_timings = None
    wt_path = out_dir / "word_timings.json"
    if wt_path.exists():
        word_timings = json.loads(wt_path.read_text(encoding="utf-8"))

    beats_doc = build_beats_document(
        segments_doc.get("segments", []),
        segment_durations_doc.get("segments", scene_durations),
        word_timings=word_timings,
    )
    _save(out_dir / "beats.json", beats_doc)

    visual_plan_path = out_dir / "visual_plan.json"
    if not visual_plan_path.exists():
        return
    visual_plan = json.loads(visual_plan_path.read_text(encoding="utf-8"))

    aligned = align_visual_plan_to_beats(visual_plan, beats_doc)
    _save(out_dir / "aligned_plan.json", aligned)

    compiled = compile_full_document(aligned, pipeline=pipeline)
    _save(out_dir / "composition_spec.json", compiled["composition"])
    _save(out_dir / "layout_spec.json", compiled["layout"])
    _save(out_dir / "attention_timeline.json", compiled["attention"])
    _save(out_dir / "camera_channel.json", compiled["camera"])
    _save(out_dir / "typography_spec.json", compiled["typography"])
    _save(out_dir / "render_ir.json", compiled["render_ir"])
    if compiled.get("performance"):
        _save(out_dir / "performance_spec.json", compiled["performance"])

    _merge_render_ir_into_scene_clips(out_dir, compiled["render_ir"])

    report = run_all_pre_render(
        segments_doc,
        visual_plan,
        beats_doc,
        aligned,
        compiled["render_ir"],
        composition=compiled["composition"],
        layout=compiled["layout"],
        attention=compiled["attention"],
        camera=compiled["camera"],
        performance=compiled.get("performance"),
        topic_knowledge=json.loads((out_dir / "topic_knowledge.json").read_text(encoding="utf-8"))
        if (out_dir / "topic_knowledge.json").exists()
        else None,
    )
    _save(out_dir / "validation_report.json", report)

    sece_cfg = pipeline.get("composition_engine", {})
    if isinstance(sece_cfg, dict) and sece_cfg.get("fail_on_validation_error", True):
        if report["status"] == "FAIL":
            msgs = []
            for r in report.get("reports", []):
                msgs.extend(r.get("errors", []))
            raise ValidationError("pre_render", msgs)


def _merge_render_ir_into_scene_clips(out_dir: Path, render_ir_doc: dict[str, Any]) -> None:
    clips_path = out_dir / "scene_clips.json"
    if not clips_path.exists():
        return
    data = json.loads(clips_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    ir_by_id = {int(s["segment_id"]): s for s in render_ir_doc.get("segments", [])}
    for scene in scenes:
        sid = int(scene.get("scene_id", 0))
        ir_row = ir_by_id.get(sid)
        if not ir_row:
            continue
        scene["animation_spec"] = ir_row.get("animation_spec")
        scene["beat_locked"] = ir_row.get("beat_locked", False)
        scene["render_ir"] = ir_row.get("render_ir")
    _save(clips_path, data)


def compile_from_directory(work_dir: Path, pipeline: dict[str, Any]) -> None:
    """Standalone compile (re-run without TTS)."""
    run_post_phase2(work_dir, pipeline=pipeline)
