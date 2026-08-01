"""Animation planner — diff states, choreograph timeline. Renderer only draws."""

from __future__ import annotations

from typing import Any

from composition_motion.algorithm_state import ComparisonState, MemoryState, empty_memory, memory_states_equal

# Primitive timeline ops (renderer vocabulary — never sent to LLM)
DUR_POINTER = 0.65
DUR_SHIFT_CELL = 0.22
DUR_SWAP = 0.55
DUR_HIGHLIGHT = 0.18
DUR_APPEAR = 0.32
DUR_APPEAR_STAGGER = 0.09
DUR_SET_VALUE = 0.38
DUR_LINK = 0.35
DUR_CAPTION = 0.28
DUR_COMPARE = 0.5
GAP = 0.12


def _find_swap(prev: list[str | None], nxt: list[str | None]) -> tuple[int, int] | None:
    if len(prev) != len(nxt):
        return None
    diffs = [i for i, (a, b) in enumerate(zip(prev, nxt)) if a != b]
    if len(diffs) != 2:
        return None
    i, j = diffs
    if prev[i] == nxt[j] and prev[j] == nxt[i]:
        return (i, j)
    return None


def _find_insertion(prev: list[str | None], nxt: list[str | None]) -> tuple[int, str | None] | None:
    """Detect single-cell insertion (shift-right) at index."""
    if len(nxt) != len(prev) + 1:
        return None
    for idx in range(len(nxt)):
        without = nxt[:idx] + nxt[idx + 1 :]
        if without == prev:
            return idx, nxt[idx]
    return None


def _find_deletion(prev: list[str | None], nxt: list[str | None]) -> int | None:
    if len(prev) != len(nxt) + 1:
        return None
    for idx in range(len(prev)):
        without = prev[:idx] + prev[idx + 1 :]
        if without == nxt:
            return idx
    return None


def diff_memory(prev: MemoryState, nxt: MemoryState) -> list[dict[str, Any]]:
    """State A → State B: what changed in memory / pointers / highlights."""
    ops: list[dict[str, Any]] = []
    caption_op: dict[str, Any] | None = None

    if nxt.caption and nxt.caption != prev.caption:
        caption_op = {"op": "caption", "text": nxt.caption}

    # New links (linked list)
    prev_links = set(prev.links)
    for fr, to in nxt.links:
        if (fr, to) not in prev_links:
            ops.append({"op": "link", "from": fr, "to": to})

    # Pointer moves (before cell motion so viewer follows attention)
    for name, idx in nxt.pointers.items():
        prev_idx = prev.pointers.get(name)
        if prev_idx is None:
            ops.append({"op": "pointer_set", "name": name, "index": idx})
        elif prev_idx != idx:
            ops.append({"op": "pointer", "name": name, "from": prev_idx, "to": idx})

    # Cell mutations
    if prev.cells != nxt.cells:
        swap = _find_swap(prev.cells, nxt.cells)
        if swap:
            ops.append({"op": "swap", "a": swap[0], "b": swap[1]})
        else:
            ins = _find_insertion(prev.cells, nxt.cells)
            if ins:
                idx, val = ins
                ops.append({"op": "shift", "from": idx, "direction": "right", "count": 1})
                if val is not None:
                    ops.append({"op": "set_value", "index": idx, "value": val})
            else:
                deletion = _find_deletion(prev.cells, nxt.cells)
                if deletion is not None:
                    ops.append({"op": "shift", "from": deletion, "direction": "left", "count": 1})
                else:
                    # In-place value writes
                    for i in range(min(len(prev.cells), len(nxt.cells))):
                        if prev.cells[i] != nxt.cells[i] and nxt.cells[i] is not None:
                            ops.append({"op": "set_value", "index": i, "value": nxt.cells[i]})
                    # Length change without detected pattern — rebuild
                    if len(prev.cells) != len(nxt.cells) and not ins and deletion is None:
                        ops.append({"op": "sync_cells", "values": nxt.cells, "addresses": nxt.addresses})

    # Highlights (after structural changes)
    if nxt.highlight != prev.highlight:
        ops.append({"op": "highlight", "indices": nxt.highlight, "prev": prev.highlight})

    if caption_op:
        ops.append(caption_op)

    return ops


def plan_appear_all(cells: list[str | None], addresses: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "op": "appear_all",
            "values": [c if c is not None else "" for c in cells],
            "addresses": addresses,
        }
    ]


def schedule_ops(
    planned: list[dict[str, Any]],
    *,
    start: float,
    is_first: bool,
) -> tuple[list[dict[str, Any]], float]:
    """Assign timestamps and durations to primitive ops."""
    timeline: list[dict[str, Any]] = []
    t = start

    for op in planned:
        kind = op["op"]

        if kind == "appear_all":
            timeline.append({
                "op": "appear_all",
                "at": t,
                "duration": DUR_APPEAR,
                "stagger": DUR_APPEAR_STAGGER,
                "values": op["values"],
                "addresses": op.get("addresses", []),
            })
            n = len(op["values"])
            t += DUR_APPEAR + max(0, n - 1) * DUR_APPEAR_STAGGER + GAP
            continue

        if kind == "pointer_set":
            timeline.append({
                "op": "pointer_set",
                "at": t,
                "duration": DUR_HIGHLIGHT,
                "name": op["name"],
                "index": op["index"],
            })
            t += DUR_HIGHLIGHT + GAP
            continue

        if kind == "pointer":
            timeline.append({
                "op": "pointer",
                "at": t,
                "duration": DUR_POINTER,
                "name": op["name"],
                "from": op["from"],
                "to": op["to"],
            })
            t += DUR_POINTER + GAP
            continue

        if kind == "highlight":
            timeline.append({
                "op": "highlight",
                "at": t,
                "duration": DUR_HIGHLIGHT,
                "indices": op["indices"],
            })
            t += DUR_HIGHLIGHT + GAP
            continue

        if kind == "shift":
            count = op.get("count", 1)
            for c in range(count):
                timeline.append({
                    "op": "shift",
                    "at": t,
                    "duration": DUR_SHIFT_CELL,
                    "from": op["from"] + c,
                    "direction": op.get("direction", "right"),
                })
                t += DUR_SHIFT_CELL * 0.85
            t += GAP
            continue

        if kind == "swap":
            timeline.append({
                "op": "swap",
                "at": t,
                "duration": DUR_SWAP,
                "a": op["a"],
                "b": op["b"],
            })
            t += DUR_SWAP + GAP
            continue

        if kind == "set_value":
            timeline.append({
                "op": "set_value",
                "at": t,
                "duration": DUR_SET_VALUE,
                "index": op["index"],
                "value": op["value"],
            })
            t += DUR_SET_VALUE + GAP
            continue

        if kind == "link":
            timeline.append({
                "op": "link",
                "at": t,
                "duration": DUR_LINK,
                "from": op["from"],
                "to": op["to"],
            })
            t += DUR_LINK + GAP
            continue

        if kind == "caption":
            timeline.append({
                "op": "caption",
                "at": t,
                "duration": DUR_CAPTION,
                "text": op["text"],
            })
            t += DUR_CAPTION + GAP
            continue

        if kind == "sync_cells":
            timeline.append({
                "op": "sync_cells",
                "at": t,
                "duration": DUR_APPEAR,
                "values": [v if v is not None else "" for v in op["values"]],
                "addresses": op.get("addresses", []),
            })
            t += DUR_APPEAR + GAP

    return timeline, t


def plan_memory_sequence(states: list[MemoryState]) -> dict[str, Any]:
    """Plan full timeline from a sequence of memory states."""
    if not states:
        return {}

    timeline: list[dict[str, Any]] = []
    t = 0.05
    prev = empty_memory()

    for i, nxt in enumerate(states):
        if memory_states_equal(prev, nxt):
            prev = nxt
            continue

        if not prev.cells and nxt.cells:
            chunk, t = schedule_ops(plan_appear_all(nxt.cells, nxt.addresses), start=t, is_first=i == 0)
            timeline.extend(chunk)
            mid = MemoryState(cells=list(nxt.cells), addresses=list(nxt.addresses))
            planned = diff_memory(mid, nxt)
        else:
            planned = diff_memory(prev, nxt)

        if planned:
            chunk, t = schedule_ops(planned, start=t, is_first=i == 0)
            timeline.extend(chunk)

        prev = nxt

    final = states[-1]
    return {
        "kind": "memory",
        "values": [c if c is not None else "" for c in final.cells],
        "addresses": final.addresses,
        "timeline": timeline,
    }


def plan_comparison_sequence(states: list[ComparisonState]) -> dict[str, Any]:
    if not states:
        return {}
    timeline: list[dict[str, Any]] = []
    t = 0.1
    for i, st in enumerate(states):
        timeline.append({
            "op": "comparison",
            "at": t,
            "duration": DUR_COMPARE,
            "left": st.left,
            "right": st.right,
            "highlight": st.highlight,
        })
        t += DUR_COMPARE + GAP
        if st.caption:
            timeline.append({"op": "caption", "at": t, "duration": DUR_CAPTION, "text": st.caption})
            t += DUR_CAPTION + GAP
    final = states[-1]
    return {
        "kind": "comparison",
        "left": final.left,
        "right": final.right,
        "timeline": timeline,
    }


def scale_timeline(timeline: list[dict[str, Any]], duration_sec: float) -> list[dict[str, Any]]:
    if not timeline or duration_sec <= 0:
        return timeline
    max_end = max((item.get("at", 0) + item.get("duration", 0.4)) for item in timeline)
    if max_end <= 0:
        return timeline
    factor = (duration_sec * 0.88) / max_end
    out: list[dict[str, Any]] = []
    for item in timeline:
        row = dict(item)
        row["at"] = round(item.get("at", 0) * factor, 4)
        if "duration" in item:
            row["duration"] = round(item["duration"] * factor, 4)
        if "stagger" in item:
            row["stagger"] = round(item["stagger"] * factor, 4)
        out.append(row)
    return out


def plan_from_visualization(viz: dict[str, Any], *, duration_sec: float | None = None) -> dict[str, Any]:
    """Algorithm → states → planner → timeline."""
    from composition_motion.algorithm_state import ComparisonState, normalize_comparison_state, parse_visualization

    kind, states = parse_visualization(viz)
    if not states:
        return {}

    if kind == "comparison":
        cmp_states = [
            s if isinstance(s, ComparisonState) else normalize_comparison_state(s)  # type: ignore[arg-type]
            for s in states
        ]
        spec = plan_comparison_sequence(cmp_states)
    else:
        mem_states = [s if isinstance(s, MemoryState) else s for s in states]  # type: ignore[misc]
        spec = plan_memory_sequence(mem_states)

    if duration_sec and spec.get("timeline"):
        spec = dict(spec)
        spec["timeline"] = scale_timeline(spec["timeline"], duration_sec)
    return spec
