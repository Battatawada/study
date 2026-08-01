"""Compile semantic_ops + trigger_beat_id into animation timelines."""

from __future__ import annotations

from typing import Any

from composition_motion.algorithm_state import normalize_comparison_state
from composition_motion.planner import (
    DUR_APPEAR,
    DUR_APPEAR_STAGGER,
    DUR_CAPTION,
    DUR_COMPARE,
    DUR_HIGHLIGHT,
    DUR_LINK,
    DUR_POINTER,
    DUR_SET_VALUE,
    DUR_SWAP,
    GAP,
    plan_from_visualization,
)

_DUR_SHIFT_CELL = 0.22


def _beat_start(beats: list[dict[str, Any]], beat_id: str | None) -> float:
    if not beat_id:
        return 0.0
    for b in beats:
        if b.get("beat_id") == beat_id:
            return float(b.get("start_sec", 0))
    return 0.0


def _cell_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in entities if e.get("type") in ("memory_cell", "node")]


def _entity_index(entities: list[dict[str, Any]], entity_id: str | None) -> int | None:
    if not entity_id:
        return None
    cells = _cell_entities(entities)
    for i, ent in enumerate(cells):
        if ent.get("entity_id") == entity_id:
            return i
    return None


def _entity_label(entities: list[dict[str, Any]], entity_id: str | None) -> str:
    if not entity_id:
        return ""
    for ent in entities:
        if ent.get("entity_id") == entity_id:
            return str(ent.get("label", "")).strip()
    return ""


def _labels_for_ids(entities: list[dict[str, Any]], entity_ids: list[str]) -> list[str]:
    out: list[str] = []
    for eid in entity_ids:
        lbl = _entity_label(entities, eid)
        out.append(lbl if lbl else eid)
    return out


def compile_semantic_ops(segment: dict[str, Any]) -> dict[str, Any]:
    """Lower semantic_ops to renderer timeline using trigger_beat_id timing."""
    ops = list(segment.get("semantic_ops", []))
    beats = list(segment.get("beats", []))
    entities = list(segment.get("entities", []))

    if not ops:
        return {}

    for op in ops:
        if op.get("op") == "use_visualization" and isinstance(op.get("visualization"), dict):
            return plan_from_visualization(op["visualization"], duration_sec=None)

    if any(op.get("op") == "use_visualization" for op in ops):
        viz = segment.get("visualization")
        if isinstance(viz, dict):
            return plan_from_visualization(viz, duration_sec=None)

    cells = _cell_entities(entities)
    values: list[str] = []
    timeline: list[dict[str, Any]] = []

    for op in ops:
        kind = str(op.get("op", "")).strip()
        at = round(_beat_start(beats, op.get("trigger_beat_id")), 4)

        if kind == "allocate":
            eids = list(op.get("entity_ids", []))
            vals = _labels_for_ids(entities, eids) if eids else [str(c.get("label", "")) for c in cells]
            if not vals and cells:
                vals = [str(c.get("label", "")) for c in cells]
            values = vals
            timeline.append({
                "op": "appear_all",
                "at": at,
                "duration": DUR_APPEAR,
                "stagger": DUR_APPEAR_STAGGER,
                "values": vals,
                "addresses": [f"0x{i * 8:03X}" for i in range(len(vals))],
                "trigger_beat_id": op.get("trigger_beat_id"),
            })

        elif kind == "highlight":
            idx = _entity_index(entities, op.get("entity_id"))
            if idx is not None:
                timeline.append({
                    "op": "highlight",
                    "at": at,
                    "duration": DUR_HIGHLIGHT,
                    "indices": [idx],
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "pointer":
            idx = _entity_index(entities, op.get("entity_id"))
            name = str(op.get("name", "index"))
            if idx is not None:
                timeline.append({
                    "op": "pointer_set",
                    "at": at,
                    "duration": DUR_HIGHLIGHT,
                    "name": name,
                    "index": idx,
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "link":
            fr = _entity_index(entities, op.get("from"))
            to = _entity_index(entities, op.get("to"))
            if fr is not None and to is not None:
                timeline.append({
                    "op": "link",
                    "at": at,
                    "duration": DUR_LINK,
                    "from": fr,
                    "to": to,
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "caption":
            text = str(op.get("text", "")).strip()
            if text:
                timeline.append({
                    "op": "caption",
                    "at": at,
                    "duration": DUR_CAPTION,
                    "text": text,
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "set_value":
            idx = _entity_index(entities, op.get("entity_id"))
            if idx is not None:
                timeline.append({
                    "op": "set_value",
                    "at": at,
                    "duration": DUR_SET_VALUE,
                    "index": idx,
                    "value": str(op.get("value", _entity_label(entities, op.get("entity_id")))),
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "swap":
            a = _entity_index(entities, op.get("a"))
            b = _entity_index(entities, op.get("b"))
            if a is not None and b is not None:
                timeline.append({
                    "op": "swap",
                    "at": at,
                    "duration": DUR_SWAP,
                    "a": a,
                    "b": b,
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "shift":
            idx = _entity_index(entities, op.get("entity_id"))
            if idx is not None:
                timeline.append({
                    "op": "shift",
                    "at": at,
                    "duration": _DUR_SHIFT_CELL,
                    "from": idx,
                    "direction": op.get("direction", "right"),
                    "count": int(op.get("count", 1)),
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

        elif kind == "compare":
            left = _entity_label(entities, op.get("left"))
            right = _entity_label(entities, op.get("right"))
            cmp_timeline = [
                {
                    "op": "comparison",
                    "at": at,
                    "duration": DUR_COMPARE,
                    "left": left,
                    "right": right,
                    "highlight": "left",
                    "trigger_beat_id": op.get("trigger_beat_id"),
                },
            ]
            if len(beats) > 1:
                second_at = round(_beat_start(beats, beats[1].get("beat_id")), 4)
                cmp_timeline.append({
                    "op": "comparison",
                    "at": second_at,
                    "duration": DUR_COMPARE,
                    "left": left,
                    "right": right,
                    "highlight": "right",
                    "trigger_beat_id": beats[1].get("beat_id"),
                })
            return {"kind": "comparison", "left": left, "right": right, "timeline": cmp_timeline}

        elif kind == "introduce":
            eid = op.get("entity_id")
            idx = _entity_index(entities, eid)
            lbl = _entity_label(entities, eid)
            if idx is not None:
                if not values:
                    values = [""] * (idx + 1)
                while len(values) <= idx:
                    values.append("")
                values[idx] = lbl
                timeline.append({
                    "op": "set_value",
                    "at": at,
                    "duration": DUR_SET_VALUE,
                    "index": idx,
                    "value": lbl,
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })
            elif lbl:
                timeline.append({
                    "op": "caption",
                    "at": at,
                    "duration": DUR_CAPTION,
                    "text": lbl,
                    "trigger_beat_id": op.get("trigger_beat_id"),
                })

    if not timeline:
        return {}

    if not values:
        values = [str(c.get("label", "")) for c in cells]

    return {
        "kind": "memory",
        "values": values,
        "addresses": [f"0x{i * 8:03X}" for i in range(len(values))],
        "timeline": timeline,
    }


def lock_timeline_to_beat_ids(
    spec: dict[str, Any],
    beats: list[dict[str, Any]],
    semantic_ops: list[dict[str, Any]] | None = None,
    *,
    pad_end_sec: float = 0.15,
) -> dict[str, Any]:
    """Re-time timeline ops using trigger_beat_id or aligned semantic_ops order."""
    if not spec or not beats:
        return spec
    timeline = list(spec.get("timeline", []))
    if not timeline:
        return spec

    beat_by_id = {b["beat_id"]: b for b in beats}
    op_beat_ids: list[str | None] = []
    if semantic_ops:
        op_beat_ids = [op.get("trigger_beat_id") for op in semantic_ops]
    while len(op_beat_ids) < len(timeline):
        op_beat_ids.append(None)

    out = dict(spec)
    new_timeline: list[dict[str, Any]] = []
    for i, op in enumerate(timeline):
        row = dict(op)
        beat_id = row.get("trigger_beat_id") or op_beat_ids[i]
        if beat_id and beat_id in beat_by_id:
            row["at"] = round(float(beat_by_id[beat_id]["start_sec"]), 4)
        elif beats:
            beat_idx = min(i, len(beats) - 1)
            row["at"] = round(float(beats[beat_idx]["start_sec"]), 4)
        new_timeline.append(row)

    duration = float(beats[-1].get("end_sec", 0))
    if duration > 0:
        max_end = max((item.get("at", 0) + item.get("duration", 0.4)) for item in new_timeline)
        if max_end > duration - pad_end_sec:
            shift = max_end - (duration - pad_end_sec)
            for row in new_timeline:
                row["at"] = round(max(0.0, row["at"] - shift), 4)

    out["timeline"] = new_timeline
    return out
