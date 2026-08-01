"""Algorithm state model — AI describes *what* changed, not *how* to animate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

_EMPTY = object()


@dataclass
class MemoryState:
    """Contiguous memory — cells are addresses, not decorative boxes."""

    cells: list[str | None]
    addresses: list[str] = field(default_factory=list)
    pointers: dict[str, int] = field(default_factory=dict)
    highlight: list[int] = field(default_factory=list)
    links: list[tuple[int, int]] = field(default_factory=list)
    caption: str = ""

    def copy(self) -> MemoryState:
        return MemoryState(
            cells=list(self.cells),
            addresses=list(self.addresses),
            pointers=dict(self.pointers),
            highlight=list(self.highlight),
            links=list(self.links),
            caption=self.caption,
        )


@dataclass
class ComparisonState:
    left: str = ""
    right: str = ""
    highlight: str = "left"  # left | right | both | none
    caption: str = ""


State = MemoryState | ComparisonState


def _cell_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "_", "·", "null", "empty"):
        return None
    return s


def _addresses_for(n: int, existing: list[str] | None = None) -> list[str]:
    if existing and len(existing) >= n:
        return list(existing[:n])
    return [f"0x{i * 8:03X}" for i in range(n)]


def normalize_memory_state(raw: dict[str, Any]) -> MemoryState:
    """Accept algorithm_state / state blobs from the visual mapper."""
    cells_raw = raw.get("array") or raw.get("cells") or raw.get("memory") or []
    if not isinstance(cells_raw, list):
        cells_raw = []
    cells = [_cell_str(v) for v in cells_raw]

    pointers: dict[str, int] = {}
    if raw.get("pointers") and isinstance(raw["pointers"], dict):
        for k, v in raw["pointers"].items():
            if v is not None:
                pointers[str(k)] = int(v)
    if raw.get("basePointer") is not None:
        pointers.setdefault("base", int(raw["basePointer"]))
    if raw.get("activeIndex") is not None:
        pointers.setdefault("index", int(raw["activeIndex"]))

    highlight = raw.get("highlight") or raw.get("highlights") or []
    if isinstance(highlight, int):
        highlight = [highlight]
    highlight = [int(i) for i in highlight if isinstance(i, (int, float))]

    links: list[tuple[int, int]] = []
    for item in raw.get("links") or []:
        if isinstance(item, dict):
            links.append((int(item["from"]), int(item["to"])))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            links.append((int(item[0]), int(item[1])))

    addrs = raw.get("addresses")
    addresses = _addresses_for(len(cells), addrs if isinstance(addrs, list) else None)

    return MemoryState(
        cells=cells,
        addresses=addresses,
        pointers=pointers,
        highlight=highlight,
        links=links,
        caption=str(raw.get("caption", "")).strip(),
    )


def normalize_comparison_state(raw: dict[str, Any]) -> ComparisonState:
    return ComparisonState(
        left=str(raw.get("left", "")).strip(),
        right=str(raw.get("right", "")).strip(),
        highlight=str(raw.get("highlight", "left")).strip() or "left",
        caption=str(raw.get("caption", "")).strip(),
    )


def empty_memory() -> MemoryState:
    return MemoryState(cells=[], addresses=[], pointers={}, highlight=[], links=[], caption="")


# --- Semantic event vocabulary (universal visualization language) ---

def apply_event(state: MemoryState, event: dict[str, Any]) -> MemoryState:
    """Apply one semantic event → new state. Events describe computation, not graphics."""
    name = str(event.get("event") or event.get("op") or "").strip()
    s = state.copy()
    params = {k: v for k, v in event.items() if k not in ("event", "op")}

    if name in ("Allocate", "Init"):
        cells = [_cell_str(v) for v in params.get("cells") or params.get("array") or []]
        s.cells = cells
        s.addresses = _addresses_for(len(cells), params.get("addresses"))
        return s

    if name == "Visit":
        idx = int(params.get("index", params.get("i", 0)))
        label = str(params.get("pointer", "index"))
        s.pointers[label] = idx
        return s

    if name == "Highlight":
        indices = params.get("indices") or params.get("highlight") or []
        if isinstance(indices, int):
            indices = [indices]
        s.highlight = [int(i) for i in indices]
        return s

    if name == "Compare":
        a, b = int(params.get("a", 0)), int(params.get("b", 1))
        s.highlight = [a, b]
        return s

    if name == "Swap":
        a, b = int(params.get("a", 0)), int(params.get("b", 1))
        if 0 <= a < len(s.cells) and 0 <= b < len(s.cells):
            s.cells[a], s.cells[b] = s.cells[b], s.cells[a]
        s.highlight = [a, b]
        return s

    if name == "Shift":
        start = int(params.get("from", params.get("index", 0)))
        count = int(params.get("count", 1))
        direction = str(params.get("direction", "right"))
        cells = list(s.cells)
        if direction == "right":
            for _ in range(count):
                cells.insert(start, None)
        else:
            for _ in range(count):
                if start < len(cells):
                    cells.pop(start)
        s.cells = cells
        s.addresses = _addresses_for(len(cells), s.addresses)
        return s

    if name in ("Insert", "Write"):
        idx = int(params.get("index", 0))
        value = _cell_str(params.get("value"))
        cells = list(s.cells)
        while len(cells) <= idx:
            cells.append(None)
        cells[idx] = value
        s.cells = cells
        s.addresses = _addresses_for(len(cells), s.addresses)
        s.highlight = [idx]
        return s

    if name == "Link":
        s.links.append((int(params.get("from", 0)), int(params.get("to", 1))))
        return s

    if name == "Caption":
        s.caption = str(params.get("text", "")).strip()
        return s

    if name == "Pointer":
        s.pointers[str(params.get("name", "ptr"))] = int(params.get("index", 0))
        return s

    return s


def events_to_states(events: list[dict[str, Any]]) -> list[MemoryState]:
    """Expand semantic event stream into a state sequence."""
    states: list[MemoryState] = [empty_memory()]
    current = empty_memory()
    for ev in events:
        current = apply_event(current, ev)
        states.append(current.copy())
    return states


def parse_visualization(raw: dict[str, Any]) -> tuple[str, list[Any]]:
    """Return (kind, state_sequence) from visualization blob."""
    kind = str(raw.get("kind") or raw.get("type") or "memory").lower()

    if raw.get("events"):
        return "memory", events_to_states(raw["events"])

    transitions = raw.get("transitions") or raw.get("states") or []
    if transitions:
        seq: list[Any] = []
        for item in transitions:
            if isinstance(item, dict) and "state" in item:
                st = normalize_memory_state(item["state"])
                cap = item.get("caption") or item["state"].get("caption")
                if cap:
                    st.caption = str(cap)
                seq.append(st)
            elif isinstance(item, dict):
                seq.append(normalize_memory_state(item))
        if seq:
            return kind, seq

    if raw.get("algorithm_state") or raw.get("state"):
        inner = raw.get("algorithm_state") or raw.get("state")
        if isinstance(inner, dict):
            return kind, [normalize_memory_state(inner)]

    return kind, []


def memory_states_equal(a: MemoryState, b: MemoryState) -> bool:
    return (
        a.cells == b.cells
        and a.pointers == b.pointers
        and a.highlight == b.highlight
        and a.links == b.links
        and a.caption == b.caption
    )
