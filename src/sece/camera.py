"""Camera compiler — 2D pan/zoom channel following attention."""

from __future__ import annotations

from typing import Any

from sece.constants import SCHEMA_VERSION
from sece.regions import STAGE_HEIGHT, STAGE_WIDTH

DEFAULT_ZOOM = 1.0
FOCUS_ZOOM = 1.12
PAN_DURATION = 0.65


def compile_camera_channel(
    attention: dict[str, Any],
    *,
    duration_sec: float,
) -> dict[str, Any]:
    sid = int(attention.get("segment_id", 0))
    timeline = list(attention.get("timeline", []))
    channel: list[dict[str, Any]] = []

    if not timeline:
        channel.append({
            "at_sec": 0.0,
            "duration_sec": duration_sec,
            "center_x": STAGE_WIDTH / 2,
            "center_y": STAGE_HEIGHT / 2,
            "zoom": DEFAULT_ZOOM,
            "easing": "emphasize",
        })
    else:
        for i, beat_att in enumerate(timeline):
            fp = beat_att.get("focus_point", {})
            at = float(beat_att.get("start_sec", 0))
            cx = float(fp.get("x", STAGE_WIDTH / 2))
            cy = float(fp.get("y", STAGE_HEIGHT / 2))
            zoom = FOCUS_ZOOM if beat_att.get("primary_entity_id") else DEFAULT_ZOOM
            channel.append({
                "at_sec": round(at, 4),
                "duration_sec": PAN_DURATION,
                "center_x": round(cx, 2),
                "center_y": round(cy, 2),
                "zoom": zoom,
                "easing": "emphasize",
                "beat_id": beat_att.get("beat_id"),
            })

    return {
        "schema_version": SCHEMA_VERSION,
        "segment_id": sid,
        "duration_sec": duration_sec,
        "channel": channel,
    }
