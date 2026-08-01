"""Stage region geometry for 1920x1080 slide layout."""

from __future__ import annotations

from typing import Any

# Canvas inside the diagram panel (matches semantic_slide.html)
STAGE_WIDTH = 1824
STAGE_HEIGHT = 516

REGIONS = {
    "title_band": {"x": 80, "y": 72, "width": 1760, "height": 120},
    "stage": {"x": 0, "y": 0, "width": STAGE_WIDTH, "height": STAGE_HEIGHT},
    "caption_band": {"x": 80, "y": STAGE_HEIGHT - 40, "width": 1664, "height": 36},
    "bullet_band": {"x": 80, "y": 548, "width": 1760, "height": 200},
}


def stage_rect() -> dict[str, int]:
    return dict(REGIONS["stage"])

def entity_box(x: int, y: int, w: int, h: int) -> dict[str, int]:
    return {"x": x, "y": y, "w": w, "h": h}


def box_center(box: dict[str, int]) -> tuple[float, float]:
    return box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
