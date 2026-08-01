"""Composition rules — hierarchy, salience, reading order before layout."""

from __future__ import annotations

from typing import Any

from sece.constants import SCHEMA_VERSION


def build_composition_spec(segment: dict[str, Any]) -> dict[str, Any]:
    """Deterministic composition metadata for one aligned segment."""
    sid = int(segment["segment_id"])
    entities = list(segment.get("entities", []))
    beats = list(segment.get("beats", []))
    attention_plan = list(segment.get("attention_plan", []))
    intent = segment.get("teaching_intent", {})

    salience: dict[str, str] = {}
    for ent in entities:
        eid = ent.get("entity_id", "")
        if not eid:
            continue
        etype = ent.get("type", "")
        if etype in ("memory_cell", "node") and "0" in eid.split("_")[-1]:
            salience[eid] = "secondary"
        elif etype in ("region", "concept", "panel"):
            salience[eid] = "primary"
        else:
            salience[eid] = "secondary"

    beat_composition: list[dict[str, Any]] = []
    for beat in beats:
        bid = beat["beat_id"]
        att = next((a for a in attention_plan if a.get("beat_id") == bid), None)
        primary = att.get("primary_entity_id") if att else None
        secondary = list(att.get("secondary", [])) if att else []
        visible = [primary] if primary else []
        visible.extend([s for s in secondary if s and s not in visible])
        if not visible and entities:
            visible = [entities[0]["entity_id"]]
        beat_composition.append({
            "beat_id": bid,
            "primary_entity_id": primary or (visible[0] if visible else None),
            "visible_entity_ids": visible[:4],
            "max_visible": 4,
            "reading_order": visible,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "segment_id": sid,
        "layout_recipe": segment.get("layout_recipe", "stage_single"),
        "build_policy": intent.get("build_policy", "construct_only"),
        "salience": salience,
        "beat_composition": beat_composition,
        "regions": {
            "title": "title_band",
            "stage": "stage",
            "caption": "caption_band",
        },
    }
