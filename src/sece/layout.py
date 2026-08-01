"""Layout engine — recipe catalog places entities in stage coordinates."""

from __future__ import annotations

from typing import Any

from sece.constants import SCHEMA_VERSION
from sece.regions import STAGE_HEIGHT, STAGE_WIDTH, box_center, entity_box


def build_layout_spec(segment: dict[str, Any], composition: dict[str, Any]) -> dict[str, Any]:
    recipe = segment.get("layout_recipe", composition.get("layout_recipe", "stage_single"))
    entities = list(segment.get("entities", []))
    placed = _place_recipe(recipe, entities, segment)
    return {
        "schema_version": SCHEMA_VERSION,
        "segment_id": int(segment["segment_id"]),
        "recipe": recipe,
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "entities": placed,
    }


def _place_recipe(
    recipe: str,
    entities: list[dict[str, Any]],
    segment: dict[str, Any],
) -> list[dict[str, Any]]:
    if recipe in ("memory_row", "array_access"):
        return _layout_memory_row(entities)
    if recipe == "linked_row":
        return _layout_linked_row(entities)
    if recipe == "comparison_columns":
        return _layout_comparison(entities)
    if recipe == "flow_vertical":
        return _layout_flow_vertical(entities)
    if recipe == "http_exchange":
        return _layout_http_exchange(entities)
    if recipe == "tree_layered":
        return _layout_tree(entities)
    return _layout_stage_single(entities, segment)


def _layout_memory_row(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells = [e for e in entities if e.get("type") in ("memory_cell", "node")]
    if not cells:
        cells = entities
    cell_w, cell_h, gap = 88, 56, 10
    n = max(1, len(cells))
    total_w = n * cell_w + (n - 1) * gap
    start_x = int((STAGE_WIDTH - total_w) / 2)
    y = int(STAGE_HEIGHT / 2 - cell_h / 2 - 16)
    out: list[dict[str, Any]] = []
    for i, ent in enumerate(cells):
        x = start_x + i * (cell_w + gap)
        out.append({
            "entity_id": ent["entity_id"],
            "type": ent.get("type", "memory_cell"),
            "label": ent.get("label", ""),
            "box": entity_box(x, y, cell_w, cell_h),
            "z_index": 10 + i,
        })
    for ent in entities:
        if ent.get("type") == "region":
            out.insert(0, {
                "entity_id": ent["entity_id"],
                "type": "region",
                "label": ent.get("label", ""),
                "box": entity_box(start_x - 20, y - 48, total_w + 40, cell_h + 56),
                "z_index": 1,
            })
    return out


def _layout_linked_row(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = [e for e in entities if e.get("type") == "node"] or entities
    node_w, node_h, gap = 100, 52, 48
    n = max(1, len(nodes))
    total_w = n * node_w + (n - 1) * gap
    start_x = int((STAGE_WIDTH - total_w) / 2)
    y = int(STAGE_HEIGHT / 2 - node_h / 2)
    out: list[dict[str, Any]] = []
    for i, ent in enumerate(nodes):
        x = start_x + i * (node_w + gap)
        out.append({
            "entity_id": ent["entity_id"],
            "type": "node",
            "label": ent.get("label", ""),
            "box": entity_box(x, y, node_w, node_h),
            "z_index": 10 + i,
        })
    return out


def _layout_comparison(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    panels = [e for e in entities if e.get("type") == "panel"] or entities[:2]
    box_w, box_h = 360, 160
    gap = 80
    total = 2 * box_w + gap
    left_x = int((STAGE_WIDTH - total) / 2)
    right_x = left_x + box_w + gap
    y = int(STAGE_HEIGHT / 2 - box_h / 2)
    out: list[dict[str, Any]] = []
    for i, ent in enumerate(panels[:2]):
        x = left_x if i == 0 else right_x
        out.append({
            "entity_id": ent["entity_id"],
            "type": "panel",
            "label": ent.get("label", ""),
            "box": entity_box(x, y, box_w, box_h),
            "z_index": 10 + i,
        })
    return out


def _layout_flow_vertical(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = entities or []
    row_h, gap = 52, 14
    n = max(1, len(items))
    total_h = n * row_h + (n - 1) * gap
    start_y = int((STAGE_HEIGHT - total_h) / 2)
    row_w = min(900, STAGE_WIDTH - 160)
    x = int((STAGE_WIDTH - row_w) / 2)
    out: list[dict[str, Any]] = []
    for i, ent in enumerate(items):
        y = start_y + i * (row_h + gap)
        out.append({
            "entity_id": ent["entity_id"],
            "type": ent.get("type", "step"),
            "label": ent.get("label", ""),
            "box": entity_box(x, y, row_w, row_h),
            "z_index": 10 + i,
        })
    return out


def _layout_http_exchange(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    box_w, box_h = 280, 80
    y = int(STAGE_HEIGHT / 2 - box_h / 2)
    left_x = int(STAGE_WIDTH * 0.2 - box_w / 2)
    right_x = int(STAGE_WIDTH * 0.8 - box_w / 2)
    labels = [e.get("label", "") for e in entities[:2]]
    return [
        {
            "entity_id": entities[0]["entity_id"] if entities else "client",
            "type": "http_box",
            "label": labels[0] if labels else "Client",
            "box": entity_box(left_x, y, box_w, box_h),
            "z_index": 10,
        },
        {
            "entity_id": entities[1]["entity_id"] if len(entities) > 1 else "server",
            "type": "http_box",
            "label": labels[1] if len(labels) > 1 else "Server",
            "box": entity_box(right_x, y, box_w, box_h),
            "z_index": 11,
        },
    ]


def _layout_tree(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = entities[:3] if entities else []
    if not nodes:
        return _layout_stage_single([], {})
    positions = [
        (STAGE_WIDTH // 2 - 24, STAGE_HEIGHT // 2 - 60),
        (STAGE_WIDTH // 2 - 120, STAGE_HEIGHT // 2 + 20),
        (STAGE_WIDTH // 2 + 72, STAGE_HEIGHT // 2 + 20),
    ]
    out: list[dict[str, Any]] = []
    for i, ent in enumerate(nodes):
        px, py = positions[i] if i < len(positions) else (100 + i * 80, STAGE_HEIGHT // 2)
        out.append({
            "entity_id": ent["entity_id"],
            "type": "tree_node",
            "label": ent.get("label", ""),
            "box": entity_box(px, py, 48, 48),
            "z_index": 10 + i,
        })
    return out


def _layout_stage_single(entities: list[dict[str, Any]], segment: dict[str, Any]) -> list[dict[str, Any]]:
    label = ""
    eid = "main"
    if entities:
        eid = entities[0]["entity_id"]
        label = entities[0].get("label", "")
    w, h = 480, 120
    x = int((STAGE_WIDTH - w) / 2)
    y = int((STAGE_HEIGHT - h) / 2)
    return [{
        "entity_id": eid,
        "type": entities[0].get("type", "concept") if entities else "concept",
        "label": label or segment.get("visual_title", "Concept"),
        "box": entity_box(x, y, w, h),
        "z_index": 10,
    }]


def layout_entity_center(layout: dict[str, Any], entity_id: str | None) -> tuple[float, float]:
    if not entity_id:
        return STAGE_WIDTH / 2, STAGE_HEIGHT / 2
    for ent in layout.get("entities", []):
        if ent.get("entity_id") == entity_id:
            return box_center(ent["box"])
    return STAGE_WIDTH / 2, STAGE_HEIGHT / 2
