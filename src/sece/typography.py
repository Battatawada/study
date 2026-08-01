"""Typography roles → font tokens for render IR."""

from __future__ import annotations

from typing import Any

from sece.constants import SCHEMA_VERSION


DEFAULT_TYPOGRAPHY: dict[str, dict[str, Any]] = {
    "segment_title": {"family": "Segoe UI", "size": 64, "weight": 700, "line_height": 1.15},
    "entity_label": {"family": "Segoe UI", "size": 20, "weight": 600},
    "entity_address": {"family": "Segoe UI", "size": 13, "weight": 400},
    "caption": {"family": "Segoe UI", "size": 24, "weight": 600},
    "bullet": {"family": "Segoe UI", "size": 32, "weight": 400},
    "watermark": {"family": "Segoe UI", "size": 24, "weight": 400},
    "comparison_body": {"family": "Segoe UI", "size": 22, "weight": 400},
}


def build_typography_spec(pipeline: dict[str, Any] | None = None) -> dict[str, Any]:
    pipeline = pipeline or {}
    sece = pipeline.get("composition_engine", {})
    overrides = sece.get("typography", {}) if isinstance(sece, dict) else {}
    roles = {k: dict(v) for k, v in DEFAULT_TYPOGRAPHY.items()}
    for role, tok in overrides.items():
        if isinstance(tok, dict) and role in roles:
            roles[role].update(tok)
    return {"schema_version": SCHEMA_VERSION, "roles": roles}
