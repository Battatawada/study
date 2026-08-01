"""Merge visual_plan + beats → aligned_plan.json.

LLM trigger_beat_id values are advisory only. The authoritative beat graph
is produced after narration/TTS; this module remaps every semantic op onto
the real beat list before SECE compile/validation.
"""

from __future__ import annotations

import re
from typing import Any


_BEAT_NUM_RE = re.compile(r"_b(\d+)\s*$", re.IGNORECASE)


def _parse_beat_number(beat_id: str | None) -> int | None:
    if not beat_id:
        return None
    m = _BEAT_NUM_RE.search(str(beat_id))
    if not m:
        return None
    return int(m.group(1))


def resolve_trigger_beat_id(
    advisory: str | None,
    beats: list[dict[str, Any]],
    *,
    op_index: int,
) -> tuple[str | None, dict[str, Any] | None]:
    """
    Resolve an advisory trigger_beat_id onto the actual beat list.

    Returns (resolved_beat_id, remap_record_or_None).
    Deterministic: keep if valid; else clamp advisory beat index; else op_index.
    Never invents beats. Never drops the op.
    """
    if not beats:
        if advisory:
            return None, {
                "from": advisory,
                "to": None,
                "reason": "no_beats_available",
            }
        return None, None

    beat_ids = [b["beat_id"] for b in beats]
    if advisory and advisory in beat_ids:
        return advisory, None

    # Prefer clamping the advisory beat index (s7_b3 → last beat if only 2).
    advisory_n = _parse_beat_number(advisory)
    if advisory_n is not None:
        idx = max(0, min(advisory_n - 1, len(beats) - 1))
    else:
        idx = min(op_index, len(beats) - 1)

    resolved = beat_ids[idx]
    if not advisory:
        return resolved, {
            "from": None,
            "to": resolved,
            "reason": "missing_advisory_assigned",
        }

    reason = "advisory_beat_missing"
    if advisory_n is not None and advisory_n > len(beats):
        reason = "advisory_beat_index_clamped"
    return resolved, {
        "from": advisory,
        "to": resolved,
        "reason": reason,
    }


def align_visual_plan_to_beats(
    visual_plan: dict[str, Any],
    beats_doc: dict[str, Any],
) -> dict[str, Any]:
    beats_by_id = {int(b["segment_id"]): b for b in beats_doc.get("segments", [])}
    out_segments: list[dict[str, Any]] = []
    remaps: list[dict[str, Any]] = []

    for row in visual_plan.get("segments", []):
        sid = int(row["segment_id"])
        beat_block = beats_by_id.get(sid, {})
        beats = list(beat_block.get("beats", []))
        beat_ids = {b["beat_id"] for b in beats}

        semantic_ops = []
        for i, op in enumerate(row.get("semantic_ops", [])):
            op_copy = dict(op)
            # LLM concrete IDs are stripped to null; optional advisory retained for remap hints.
            advisory = op_copy.get("trigger_beat_id") or op_copy.get("llm_trigger_beat_id_advisory")
            resolved, remap = resolve_trigger_beat_id(advisory, beats, op_index=i)
            if resolved is not None:
                op_copy["trigger_beat_id"] = resolved
            elif "trigger_beat_id" in op_copy:
                op_copy["trigger_beat_id"] = None
            if remap:
                remaps.append({
                    "segment_id": sid,
                    "op_index": i,
                    "op": op_copy.get("op"),
                    **remap,
                })
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

        # Remap attention_plan beat_ids that don't exist onto nearest real beats.
        fixed_attention: list[dict[str, Any]] = []
        for j, att in enumerate(attention_plan):
            att_copy = dict(att)
            bid = att_copy.get("beat_id")
            if beats and bid and bid not in beat_ids:
                resolved, remap = resolve_trigger_beat_id(bid, beats, op_index=j)
                if resolved:
                    att_copy["beat_id"] = resolved
                if remap:
                    remaps.append({
                        "segment_id": sid,
                        "op_index": j,
                        "op": "attention_plan",
                        **remap,
                    })
            fixed_attention.append(att_copy)

        out_segments.append({
            "segment_id": sid,
            "duration_sec": float(beat_block.get("duration_sec", 0)),
            "beats": beats,
            "teaching_intent": row.get("teaching_intent", {}),
            "layout_recipe": row.get("layout_recipe", "stage_single"),
            "entities": row.get("entities", []),
            "relationships": row.get("relationships", []),
            "semantic_ops": semantic_ops,
            "attention_plan": fixed_attention,
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
        "beat_id_remaps": remaps,
    }
