"""SECE schema versions and feature flags."""

from __future__ import annotations

SCHEMA_VERSION = "1.0"
RENDER_IR_VERSION = "1.2"

# Beat kinds used across beats.json and validators
BEAT_KINDS = frozenset({
    "concept_label",
    "explanation",
    "example",
    "contrast",
    "recap",
    "transition",
    "unknown",
})
