"""State-transition presets — AI describes states, planner choreographs motion."""

from __future__ import annotations

from typing import Any

from algorithm_state import MemoryState, empty_memory, normalize_memory_state
from animation_planner import plan_from_visualization
from diagram_renderer import infer_diagram_type


def _labels(scene: dict[str, Any], count: int, defaults: list[str]) -> list[str]:
    raw = scene.get("diagram_labels", [])
    if isinstance(raw, str):
        raw = [raw]
    labels = [str(x).strip() for x in raw if str(x).strip()][:count]
    while len(labels) < count:
        labels.append(defaults[len(labels)] if len(labels) < len(defaults) else "")
    return labels


def _viz_transitions(states: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "memory", "transitions": [{"state": s} for s in states]}


def _viz_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "memory", "events": events}


def preset_memory_layout(scene: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(scene, 2, ["RAM", "contiguous block"])
    n = 6
    cells = [labels[0] if i == 0 else str(i) for i in range(n)]
    return _viz_transitions([
        {},
        {"array": cells, "addresses": [f"0x{i * 8:03X}" for i in range(n)]},
        {"array": cells, "basePointer": 0, "highlight": [0]},
        {"array": cells, "basePointer": n - 1, "highlight": [n - 1], "caption": labels[1]},
    ])


def preset_array_access(scene: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(scene, 3, ["base", "base + index × size", "target"])
    target = 3
    cells = [f"[{i}]" for i in range(5)]
    addrs = [f"L{i}" for i in range(5)]
    return _viz_transitions([
        {},
        {"array": cells, "addresses": addrs},
        {"array": cells, "addresses": addrs, "basePointer": 0},
        {"array": cells, "addresses": addrs, "basePointer": 0, "activeIndex": target},
        {"array": cells, "addresses": addrs, "activeIndex": target, "highlight": [target], "caption": labels[1]},
        {"array": cells, "addresses": addrs, "activeIndex": target, "highlight": [target], "caption": labels[2]},
    ])


def preset_linked_nodes(scene: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(scene, 4, ["Head", "A", "B", "null"])
    cells = labels[:4]
    return _viz_events([
        {"event": "Allocate", "cells": cells},
        {"event": "Link", "from": 0, "to": 1},
        {"event": "Link", "from": 1, "to": 2},
        {"event": "Link", "from": 2, "to": 3},
        {"event": "Visit", "index": 0, "pointer": "current"},
        {"event": "Visit", "index": 2, "pointer": "current"},
        {"event": "Highlight", "indices": [2]},
    ])


def preset_comparison(scene: dict[str, Any]) -> dict[str, Any]:
    bullets = [str(b) for b in scene.get("visual_bullets", [])][:2]
    labels = _labels(scene, 2, ["Option A", "Option B"])
    left = bullets[0] if bullets else labels[0]
    right = bullets[1] if len(bullets) > 1 else labels[1]
    return {
        "kind": "comparison",
        "transitions": [
            {"left": left, "right": right, "highlight": "left"},
            {"left": left, "right": right, "highlight": "right"},
        ],
    }


def preset_flow_steps(scene: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(scene, 4, [])
    bullets = [str(b) for b in scene.get("visual_bullets", []) if str(b).strip()][:4]
    steps_labels = [lbl for lbl in (labels or bullets) if lbl.strip()] or ["Step 1", "Step 2", "Step 3"]
    events: list[dict[str, Any]] = [{"event": "Allocate", "cells": steps_labels}]
    for i in range(len(steps_labels)):
        events.append({"event": "Highlight", "indices": [i]})
    return _viz_events(events)


def preset_list_items(scene: dict[str, Any]) -> dict[str, Any]:
    bullets = [str(b) for b in scene.get("visual_bullets", []) if str(b).strip()][:4]
    values = bullets or ["Item 1", "Item 2", "Item 3"]
    events: list[dict[str, Any]] = [{"event": "Allocate", "cells": values}]
    for i in range(len(values)):
        events.append({"event": "Highlight", "indices": [i]})
    return _viz_events(events)


def preset_insert_shift(scene: dict[str, Any]) -> dict[str, Any]:
    """Insertion as state transitions — memory shifts, then new value written."""
    return _viz_transitions([
        {},
        {"array": ["10", "20", "30", "40"]},
        {"array": ["10", "20", "30", "40"], "highlight": [2]},
        {"array": ["10", "20", None, "30", "40"], "highlight": [2]},
        {"array": ["10", "20", "25", "30", "40"], "highlight": [2], "caption": "memory shifted, value inserted"},
    ])


_PRESETS = {
    "memory_layout": preset_memory_layout,
    "array_access": preset_array_access,
    "linked_nodes": preset_linked_nodes,
    "comparison": preset_comparison,
    "flow_steps": preset_flow_steps,
    "list_items": preset_list_items,
}


def normalize_visualization(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("transitions") or raw.get("events") or raw.get("algorithm_state") or raw.get("state"):
        return raw
    if raw.get("visualization"):
        return raw["visualization"] if isinstance(raw["visualization"], dict) else None
    return None


def resolve_visualization(scene: dict[str, Any]) -> dict[str, Any]:
    """Build visualization blob (states/events) from scene — not timeline."""
    for key in ("visualization", "animation"):
        viz = normalize_visualization(scene.get(key))
        if viz:
            return viz

    if scene.get("algorithm_state"):
        return {"kind": "memory", "transitions": [{"state": scene["algorithm_state"]}]}

    dtype = infer_diagram_type(scene)
    fn = _PRESETS.get(dtype)
    if fn:
        return fn(scene)
    return {}


def resolve_animation_spec(scene: dict[str, Any], *, duration_sec: float | None = None) -> dict[str, Any]:
    """Algorithm → state → planner → timeline → renderer."""
    viz = resolve_visualization(scene)
    if not viz:
        return {}
    return plan_from_visualization(viz, duration_sec=duration_sec)


def uses_semantic_animation(scene: dict[str, Any]) -> bool:
    return bool(resolve_visualization(scene))
