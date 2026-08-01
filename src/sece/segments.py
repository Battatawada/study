"""Build segments.json from legacy scene_clips (segment = narration/audio unit)."""

from __future__ import annotations

import re
from typing import Any

from sece.constants import SCHEMA_VERSION


def _slug(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return t[:48] or "concept"


def build_segments_from_scene_clips(
    scene_clips: list[dict[str, Any]],
    *,
    topic_slug: str = "",
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for i, row in enumerate(scene_clips):
        sid = int(row.get("scene_id", i + 1))
        title = str(row.get("visual_title", "")).strip()
        concept_id = _slug(row.get("diagram_type", "") or title or f"segment_{sid}")
        segments.append({
            "segment_id": sid,
            "concept_id": concept_id,
            "text": str(row.get("narration", "")).strip(),
            "teaching_goal": str(row.get("diagram_type", row.get("visual_type", "concept"))).strip(),
            "music_mood": str(row.get("music_mood", "calm")).strip(),
            "layout_recipe": _layout_recipe_from_diagram(str(row.get("diagram_type", ""))),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "topic_slug": topic_slug,
        "segments": segments,
    }


def _layout_recipe_from_diagram(diagram_type: str) -> str:
    mapping = {
        "memory_layout": "memory_row",
        "array_access": "memory_row",
        "linked_nodes": "linked_row",
        "comparison": "comparison_columns",
        "flow_steps": "flow_vertical",
        "tree_nodes": "tree_layered",
        "http_request": "http_exchange",
        "http_cache": "http_exchange",
        "http_redirect": "http_exchange",
        "http_error_client": "http_exchange",
        "http_error_server": "http_exchange",
        "status_code": "stage_single",
        "list_items": "flow_vertical",
        "warning_icons": "stage_single",
        "stack_heap": "flow_vertical",
        "concept": "stage_single",
    }
    return mapping.get(diagram_type.strip().lower(), "stage_single")


def segment_durations_from_scene_durations(scene_durations: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in scene_durations:
        sid = int(row["scene_id"])
        rows.append({
            "segment_id": sid,
            "scene_id": sid,
            "duration_sec": float(row["duration_sec"]),
            "file": row.get("file", f"scene_{sid:02d}.mp4"),
            "voice": row.get("voice"),
            "tts_backend": row.get("tts_backend"),
            "music_volume": row.get("music_volume"),
            "music_mood": row.get("music_mood"),
        })
    return {"schema_version": SCHEMA_VERSION, "segments": rows}
