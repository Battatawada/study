"""Merge visual_plan + beats → aligned_plan.json."""

from __future__ import annotations

from typing import Any


def align_visual_plan_to_beats(
    visual_plan: dict[str, Any],
    beats_doc: dict[str, Any],
) -> dict[str, Any]:
    beats_by_id = {int(b["segment_id"]): b for b in beats_doc.get("segments", [])}
    out_segments: list[dict[str, Any]] = []

    for row in visual_plan.get("segments", []):
        sid = int(row["segment_id"])
        beat_block = beats_by_id.get(sid, {})
        beats = list(beat_block.get("beats", []))
        beat_ids = [b["beat_id"] for b in beats]

        semantic_ops = []
        for i, op in enumerate(row.get("semantic_ops", [])):
            op_copy = dict(op)
            tb = op_copy.get("trigger_beat_id")
            if not tb and beats:
                idx = min(i, len(beats) - 1)
                op_copy["trigger_beat_id"] = beats[idx]["beat_id"]
            semantic_ops.append(op_copy)

        attention_plan = list(row.get("attention_plan", []))
        if beats and not attention_plan:
            primary = None
            entities = row.get("entities", [])
            if entities:
                primary = entities[0].get("entity_id")
            for b in beats:
                attention_plan.append({
                    "beat_id": b["beat_id"],
                    "primary_entity_id": primary,
                    "secondary": [],
                })
        elif beats and len(attention_plan) < len(beats):
            for b in beats:
                if b["beat_id"] not in {a.get("beat_id") for a in attention_plan}:
                    attention_plan.append({
                        "beat_id": b["beat_id"],
                        "primary_entity_id": attention_plan[0].get("primary_entity_id") if attention_plan else None,
                        "secondary": [],
                    })

        out_segments.append({
            "segment_id": sid,
            "duration_sec": float(beat_block.get("duration_sec", 0)),
            "beats": beats,
            "teaching_intent": row.get("teaching_intent", {}),
            "layout_recipe": row.get("layout_recipe", "stage_single"),
            "entities": row.get("entities", []),
            "relationships": row.get("relationships", []),
            "semantic_ops": semantic_ops,
            "attention_plan": attention_plan,
            "visualization": row.get("visualization"),
            "algorithm_state": row.get("algorithm_state"),
            "visual_title": row.get("visual_title"),
            "visual_bullets": row.get("visual_bullets", []),
            "accent_color": row.get("accent_color"),
            "diagram_type": row.get("diagram_type"),
        })

    return {
        "schema_version": visual_plan.get("schema_version", "1.0"),
        "segments": out_segments,
    }
