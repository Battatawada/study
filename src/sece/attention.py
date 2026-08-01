"""Attention resolver — beat-level focal points from layout geometry."""

from __future__ import annotations

from typing import Any

from sece.constants import SCHEMA_VERSION
from sece.layout import layout_entity_center
from sece.regions import STAGE_HEIGHT, STAGE_WIDTH


def resolve_attention_timeline(
    segment: dict[str, Any],
    layout: dict[str, Any],
    composition: dict[str, Any],
) -> dict[str, Any]:
    sid = int(segment["segment_id"])
    beats = segment.get("beats", [])
    beat_comp = {b["beat_id"]: b for b in composition.get("beat_composition", [])}
    attention_plan = {a["beat_id"]: a for a in segment.get("attention_plan", [])}

    timeline: list[dict[str, Any]] = []
    for beat in beats:
        bid = beat["beat_id"]
        att = attention_plan.get(bid, {})
        comp = beat_comp.get(bid, {})
        primary = att.get("primary_entity_id") or comp.get("primary_entity_id")
        cx, cy = layout_entity_center(layout, primary)
        salience: list[dict[str, Any]] = []
        for eid in comp.get("reading_order", []):
            if eid == primary:
                salience.append({"entity_id": eid, "weight": 1.0})
            else:
                salience.append({"entity_id": eid, "weight": 0.45})

        timeline.append({
            "beat_id": bid,
            "start_sec": float(beat.get("start_sec", 0)),
            "end_sec": float(beat.get("end_sec", 0)),
            "primary_entity_id": primary,
            "focus_point": {"x": round(cx, 2), "y": round(cy, 2)},
            "salience": salience,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "segment_id": sid,
        "timeline": timeline,
        "stage_center": {"x": STAGE_WIDTH / 2, "y": STAGE_HEIGHT / 2},
    }
