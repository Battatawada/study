"""Validation gates V1–V8 for SECE artifacts."""

from __future__ import annotations

import re
from typing import Any

from sece.constants import BEAT_KINDS, SCHEMA_VERSION


class ValidationError(Exception):
    def __init__(self, stage: str, errors: list[str]) -> None:
        self.stage = stage
        self.errors = errors
        super().__init__(f"{stage}: " + "; ".join(errors))


def _report(stage: str, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
    }


def _normalize_text(text: str) -> str:
    t = re.sub(r"\s+", " ", text.strip().lower())
    t = re.sub(r"[^\w\s]", "", t)
    return t


def validate_segments(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        warnings.append(f"schema_version {doc.get('schema_version')} != {SCHEMA_VERSION}")
    segments = doc.get("segments", [])
    if not segments:
        errors.append("segments empty")
    ids: set[int] = set()
    for row in segments:
        sid = row.get("segment_id")
        if sid is None:
            errors.append("segment missing segment_id")
            continue
        sid = int(sid)
        if sid in ids:
            errors.append(f"duplicate segment_id {sid}")
        ids.add(sid)
        if not str(row.get("text", "")).strip():
            errors.append(f"segment {sid} empty text")
    return _report("V1_segments", errors, warnings)


def validate_visual_plan(doc: dict[str, Any], segments_doc: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    segment_ids = set()
    if segments_doc:
        segment_ids = {int(s["segment_id"]) for s in segments_doc.get("segments", [])}

    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        if segment_ids and sid not in segment_ids:
            errors.append(f"visual_plan segment {sid} not in segments.json")
        entities = row.get("entities", [])
        entity_ids = {e["entity_id"] for e in entities if e.get("entity_id")}
        for rel in row.get("relationships", []):
            if rel.get("from") not in entity_ids or rel.get("to") not in entity_ids:
                errors.append(f"segment {sid} relationship references unknown entity")
        intent = row.get("teaching_intent", {})
        if intent.get("build_policy") != "construct_only":
            warnings.append(f"segment {sid} build_policy not construct_only")
        for op in row.get("semantic_ops", []):
            eid = op.get("entity_id")
            if eid and eid not in entity_ids:
                errors.append(f"segment {sid} op {op.get('op')} references unknown entity {eid}")
            for ref in op.get("entity_ids", []):
                if ref not in entity_ids:
                    errors.append(f"segment {sid} op {op.get('op')} references unknown entity {ref}")
    return _report("V2_visual_plan", errors, warnings)


def validate_beats(doc: dict[str, Any], segments_doc: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    seg_ids = {int(s["segment_id"]) for s in (segments_doc or {}).get("segments", [])}
    seg_text = {
        int(s["segment_id"]): str(s.get("text", "")).strip()
        for s in (segments_doc or {}).get("segments", [])
    }

    for block in doc.get("segments", []):
        sid = int(block.get("segment_id", 0))
        if seg_ids and sid not in seg_ids:
            errors.append(f"beats segment {sid} not in segments.json")
        dur = float(block.get("duration_sec", 0))
        beats = block.get("beats", [])
        if not beats:
            errors.append(f"segment {sid} has no beats")
            continue
        for b in beats:
            if b.get("kind") not in BEAT_KINDS:
                warnings.append(f"beat {b.get('beat_id')} unknown kind")
            if float(b.get("end_sec", 0)) < float(b.get("start_sec", 0)):
                errors.append(f"beat {b.get('beat_id')} end < start")
        last_end = float(beats[-1].get("end_sec", 0))
        if dur > 0 and abs(last_end - dur) > 0.25:
            warnings.append(f"segment {sid} last beat end {last_end} vs duration {dur}")
        if sid in seg_text:
            combined = " ".join(str(b.get("text", "")).strip() for b in beats)
            if _normalize_text(seg_text[sid]) != _normalize_text(combined):
                errors.append(f"segment {sid} beat text does not match segment text")
    return _report("V3_beats", errors, warnings)


def validate_aligned_plan(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        beat_ids = {b["beat_id"] for b in row.get("beats", [])}
        entity_ids = {e["entity_id"] for e in row.get("entities", []) if e.get("entity_id")}
        for op in row.get("semantic_ops", []):
            tb = op.get("trigger_beat_id")
            if tb and tb not in beat_ids:
                errors.append(f"segment {sid} op {op.get('op')} invalid trigger_beat_id {tb}")
            eid = op.get("entity_id")
            if eid and eid not in entity_ids:
                errors.append(f"segment {sid} op {op.get('op')} invalid entity_id {eid}")
            for ref in op.get("entity_ids", []):
                if ref not in entity_ids:
                    errors.append(f"segment {sid} op {op.get('op')} invalid entity_id {ref}")
    return _report("V4_aligned_plan", errors, warnings)


def validate_composition(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        if row.get("build_policy") != "construct_only":
            warnings.append(f"segment {sid} build_policy not construct_only")
        beat_comp = row.get("beat_composition", [])
        if not beat_comp:
            errors.append(f"segment {sid} missing beat_composition")
            continue
        for bc in beat_comp:
            if not bc.get("primary_entity_id"):
                warnings.append(f"segment {sid} beat {bc.get('beat_id')} missing primary_entity_id")
            visible = bc.get("visible_entity_ids", [])
            if len(visible) > int(bc.get("max_visible", 4)):
                errors.append(f"segment {sid} beat {bc.get('beat_id')} exceeds max_visible")
    return _report("V6_composition", errors, warnings)


def validate_topic_knowledge(
    tkd: dict[str, Any],
    visual_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    concepts = {c["concept_id"]: c for c in tkd.get("concepts", [])}
    if not concepts:
        warnings.append("topic_knowledge has no concepts")
    if visual_plan:
        for row in visual_plan.get("segments", []):
            title = str(row.get("visual_title", "")).strip().lower()
            if title and not any(title in c.get("label", "").lower() for c in concepts.values()):
                warnings.append(f"segment {row.get('segment_id')} title not in TKD concepts")
    return _report("V2_tkd", errors, warnings)


def validate_render_ir(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        ir = row.get("render_ir", {})
        dur = float(row.get("duration_sec", ir.get("duration_sec", 0)))
        timeline = ir.get("timeline", [])
        if not timeline:
            warnings.append(f"segment {sid} empty timeline")
        else:
            for ev in timeline:
                at = float(ev.get("at", 0))
                if at < 0 or at > dur + 0.01:
                    errors.append(f"segment {sid} event at {at} outside duration {dur}")
        for cam in ir.get("camera", []):
            at = float(cam.get("at_sec", 0))
            if at < 0 or at > dur + 0.01:
                errors.append(f"segment {sid} camera at {at} outside duration {dur}")
        layout = ir.get("layout", {})
        stage = layout.get("stage", {})
        sw = float(stage.get("width", 1824))
        sh = float(stage.get("height", 516))
        for ent in layout.get("entities", []):
            box = ent.get("box", {})
            x, y = float(box.get("x", 0)), float(box.get("y", 0))
            w, h = float(box.get("w", 0)), float(box.get("h", 0))
            if x < 0 or y < 0 or x + w > sw + 1 or y + h > sh + 1:
                errors.append(f"segment {sid} entity {ent.get('entity_id')} box out of stage bounds")
    return _report("V5_render_ir", errors, warnings)


def validate_layout(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        entities = row.get("entities", [])
        if not entities:
            warnings.append(f"segment {sid} layout has no entities")
        for ent in entities:
            box = ent.get("box", {})
            if box.get("w", 0) <= 0 or box.get("h", 0) <= 0:
                errors.append(f"segment {sid} entity {ent.get('entity_id')} invalid box")
    return _report("V6_layout", errors, warnings)


def validate_attention(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        timeline = row.get("timeline", [])
        if not timeline:
            warnings.append(f"segment {sid} empty attention timeline")
        for item in timeline:
            fp = item.get("focus_point", {})
            if "x" not in fp or "y" not in fp:
                errors.append(f"segment {sid} beat {item.get('beat_id')} missing focus_point")
    return _report("V7_attention", errors, warnings)


def validate_camera(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        channel = row.get("channel", [])
        if not channel:
            warnings.append(f"segment {sid} empty camera channel")
        for seg in channel:
            zoom = float(seg.get("zoom", 1))
            if zoom < 0.5 or zoom > 2.5:
                warnings.append(f"segment {sid} camera zoom {zoom} out of recommended range")
    return _report("V8_camera", errors, warnings)


def validate_performance(
    doc: dict[str, Any],
    render_ir: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not doc.get("enabled", True):
        return _report("V9_performance", errors, warnings)

    ir_by_id: dict[int, dict[str, Any]] = {}
    if render_ir:
        for row in render_ir.get("segments", []):
            ir_by_id[int(row["segment_id"])] = row.get("render_ir", {})

    for row in doc.get("segments", []):
        sid = int(row.get("segment_id", 0))
        dur = float(row.get("duration_sec", 0))
        metrics = row.get("metrics", {})
        retimed = row.get("retimed", {})

        for ev in retimed.get("timeline", []):
            at = float(ev.get("at", 0))
            end = at + float(ev.get("duration", 0)) + float(ev.get("settle_sec", 0))
            if at < 0 or end > dur + 0.02:
                errors.append(f"segment {sid} performance event at {at} outside duration {dur}")

        for cam in retimed.get("camera", []):
            at = float(cam.get("at_sec", 0))
            if at < 0 or at > dur + 0.02:
                errors.append(f"segment {sid} performance camera at {at} outside duration {dur}")

        overlap = float(metrics.get("overlap_ratio", 0))
        if overlap < 0.15 and metrics.get("track_count", 0) > 2:
            warnings.append(f"segment {sid} low overlap_ratio {overlap}")

        procedural = float(metrics.get("procedural_score", 1))
        if procedural > 0.65 and metrics.get("track_count", 0) > 2:
            warnings.append(f"segment {sid} high procedural_score {procedural}")

        ir = ir_by_id.get(sid, {})
        if ir and not ir.get("performance"):
            warnings.append(f"segment {sid} render_ir missing performance block")

        for sec in row.get("secondary_timeline", []):
            if not sec.get("parent_track_id"):
                errors.append(f"segment {sid} secondary event missing parent_track_id")

    return _report("V9_performance", errors, warnings)


def run_all_pre_render(
    segments: dict[str, Any],
    visual_plan: dict[str, Any],
    beats: dict[str, Any],
    aligned: dict[str, Any],
    render_ir: dict[str, Any],
    *,
    composition: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
    attention: dict[str, Any] | None = None,
    camera: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    topic_knowledge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reports = [
        validate_segments(segments),
        validate_visual_plan(visual_plan, segments),
        validate_beats(beats, segments),
        validate_aligned_plan(aligned),
        validate_render_ir(render_ir),
    ]
    if topic_knowledge:
        reports.append(validate_topic_knowledge(topic_knowledge, visual_plan))
    if composition:
        reports.append(validate_composition(composition))
    if layout:
        reports.append(validate_layout(layout))
    if attention:
        reports.append(validate_attention(attention))
    if camera:
        reports.append(validate_camera(camera))
    if performance:
        reports.append(validate_performance(performance, render_ir))
    failed = [r for r in reports if r["status"] == "FAIL"]
    return {
        "status": "FAIL" if failed else "PASS",
        "reports": reports,
    }
