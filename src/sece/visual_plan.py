"""Bridge scene_clips → visual_plan.json (semantic layer for SECE)."""

from __future__ import annotations

import re
from typing import Any

from sece.constants import SCHEMA_VERSION


def _entity_id(prefix: str, index: int) -> str:
    return f"{prefix}_{index}"


def _segment_plan_from_row(
    row: dict[str, Any],
    segment_id: int,
    seg_meta: dict[str, Any],
) -> dict[str, Any]:
    intent = row.get("teaching_intent", {})
    if not isinstance(intent, dict):
        intent = {}
    return {
        "segment_id": segment_id,
        "teaching_intent": {
            "viewer_question": intent.get("viewer_question", row.get("visual_title", "Concept")),
            "visual_goal": intent.get("visual_goal", row.get("diagram_prompt", "")),
            "build_policy": intent.get("build_policy", "construct_only"),
        },
        "layout_recipe": row.get("layout_recipe", seg_meta.get("layout_recipe", "stage_single")),
        "entities": list(row.get("entities", [])),
        "relationships": list(row.get("relationships", [])),
        "semantic_ops": list(row.get("semantic_ops", [])),
        "attention_plan": list(row.get("attention_plan", [])),
        "carry_forward": list(row.get("carry_forward", [])),
        "visual_title": row.get("visual_title", "Concept"),
        "visual_bullets": row.get("visual_bullets", []),
        "accent_color": row.get("accent_color", "#3B82F6"),
        "diagram_type": row.get("diagram_type", "concept"),
        "visualization": row.get("visualization"),
        "algorithm_state": row.get("algorithm_state"),
    }


def build_visual_plan_from_scene_clips(
    scene_clips: list[dict[str, Any]],
    segments_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seg_by_id = {}
    if segments_doc:
        for s in segments_doc.get("segments", []):
            seg_by_id[int(s["segment_id"])] = s

    out_segments: list[dict[str, Any]] = []
    for i, row in enumerate(scene_clips):
        sid = int(row.get("scene_id", i + 1))
        seg_meta = seg_by_id.get(sid, {})

        if isinstance(row.get("entities"), list) and row.get("semantic_ops"):
            segment_plan = _segment_plan_from_row(row, sid, seg_meta)
            out_segments.append(segment_plan)
            continue

        title = str(row.get("visual_title", "Concept")).strip()
        diagram_type = str(row.get("diagram_type", "concept")).strip().lower()
        labels = row.get("diagram_labels", [])
        if isinstance(labels, str):
            labels = [labels]
        labels = [str(x).strip() for x in labels if str(x).strip()]

        entities, relationships = _entities_for_diagram(diagram_type, labels, sid)
        semantic_ops = _default_ops_for_diagram(diagram_type, entities, labels)

        if isinstance(row.get("visualization"), dict):
            viz = row["visualization"]
            semantic_ops = [{"op": "use_visualization", "visualization": viz}]

        segment_plan = {
            "segment_id": sid,
            "teaching_intent": {
                "viewer_question": title,
                "visual_goal": str(row.get("diagram_prompt", title)).strip(),
                "build_policy": "construct_only",
            },
            "layout_recipe": seg_meta.get("layout_recipe", "stage_single"),
            "entities": entities,
            "relationships": relationships,
            "semantic_ops": semantic_ops,
            "attention_plan": _default_attention(sid, entities),
            "carry_forward": [],
            "visual_title": title,
            "visual_bullets": row.get("visual_bullets", []),
            "accent_color": row.get("accent_color", "#3B82F6"),
            "diagram_type": diagram_type,
        }
        if row.get("visualization"):
            segment_plan["visualization"] = row["visualization"]
        if row.get("algorithm_state"):
            segment_plan["algorithm_state"] = row["algorithm_state"]
        out_segments.append(segment_plan)

    return {"schema_version": SCHEMA_VERSION, "segments": out_segments}


def _entities_for_diagram(
    diagram_type: str,
    labels: list[str],
    segment_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    prefix = f"s{segment_id}"

    if diagram_type in ("memory_layout", "array_access"):
        entities.append({"entity_id": f"{prefix}_ram", "type": "region", "label": labels[0] if labels else "RAM"})
        for i in range(5):
            eid = f"{prefix}_cell_{i}"
            entities.append({
                "entity_id": eid,
                "type": "memory_cell",
                "label": labels[i + 1] if i + 1 < len(labels) else f"[{i}]",
                "parent": f"{prefix}_ram",
            })
            if i > 0:
                relationships.append({
                    "from": f"{prefix}_cell_{i - 1}",
                    "to": eid,
                    "type": "adjacent",
                })
    elif diagram_type == "linked_nodes":
        node_labels = labels or ["Head", "A", "B", "null"]
        for i, lbl in enumerate(node_labels[:4]):
            eid = f"{prefix}_node_{i}"
            entities.append({"entity_id": eid, "type": "node", "label": lbl})
            if i > 0:
                relationships.append({
                    "from": f"{prefix}_node_{i - 1}",
                    "to": eid,
                    "type": "points_to",
                })
    elif diagram_type == "comparison":
        entities.append({"entity_id": f"{prefix}_left", "type": "panel", "label": labels[0] if labels else "A"})
        entities.append({"entity_id": f"{prefix}_right", "type": "panel", "label": labels[1] if len(labels) > 1 else "B"})
        relationships.append({"from": f"{prefix}_left", "to": f"{prefix}_right", "type": "compares"})
    else:
        entities.append({"entity_id": f"{prefix}_main", "type": "concept", "label": labels[0] if labels else "Concept"})

    return entities, relationships


def _default_ops_for_diagram(
    diagram_type: str,
    entities: list[dict[str, Any]],
    labels: list[str],
) -> list[dict[str, Any]]:
    cell_ids = [e["entity_id"] for e in entities if e["type"] == "memory_cell"]
    if cell_ids:
        return [
            {"op": "allocate", "entity_ids": cell_ids, "trigger_beat_id": None},
            {"op": "highlight", "entity_id": cell_ids[min(1, len(cell_ids) - 1)], "trigger_beat_id": None},
        ]
    node_ids = [e["entity_id"] for e in entities if e["type"] == "node"]
    if node_ids:
        return [
            {"op": "allocate", "entity_ids": node_ids, "trigger_beat_id": None},
        ]
    if diagram_type == "comparison":
        return [{"op": "compare", "left": f"{entities[0]['entity_id']}", "right": f"{entities[1]['entity_id']}", "trigger_beat_id": None}]
    return [{"op": "introduce", "entity_id": entities[0]["entity_id"], "trigger_beat_id": None}]


def _default_attention(segment_id: int, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entities:
        return []
    primary = entities[0]["entity_id"]
    return [{"beat_id": f"s{segment_id}_b1", "primary_entity_id": primary, "secondary": []}]
