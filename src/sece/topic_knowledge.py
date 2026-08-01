"""Topic Knowledge Document stub from topic metadata (expanded by LLM later)."""

from __future__ import annotations

from typing import Any

from sece.constants import SCHEMA_VERSION


def build_topic_knowledge_stub(
    *,
    topic_slug: str,
    topic_title: str,
    scene_clips: list[dict[str, Any]],
) -> dict[str, Any]:
    concepts: list[dict[str, Any]] = []
    seen: set[str] = set()
    order = 0
    for row in scene_clips:
        title = str(row.get("visual_title", "")).strip()
        if not title:
            continue
        cid = _concept_id(title)
        if cid in seen:
            continue
        seen.add(cid)
        order += 1
        concepts.append({
            "concept_id": cid,
            "label": title,
            "definition": str(row.get("diagram_prompt", "")).strip(),
            "relations": [],
            "teaching_order": order,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "topic_slug": topic_slug,
        "topic_title": topic_title,
        "concepts": concepts,
        "through_lines": [],
    }


def _concept_id(title: str) -> str:
    import re

    t = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return t[:64] or "concept"
