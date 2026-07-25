"""Per-scene background music mood + volume from narration text (teaching format)."""

from __future__ import annotations

import re
from typing import Any

MOOD_VOLUME: dict[str, float] = {
    "calm": 0.60,
    "focus": 0.75,
    "example": 0.85,
    "recap": 0.70,
    "transition": 0.55,
    # legacy recap moods (still accepted)
    "mystery": 0.70,
    "tense": 0.90,
    "action": 1.00,
    "reveal": 0.80,
    "emotional": 0.75,
}

EXAMPLE_WORDS = frozenset(
    {"example", "imagine", "suppose", "real-world", "like when", "for instance", "consider"}
)
RECAP_WORDS = frozenset(
    {"recap", "summary", "remember", "takeaway", "key point", "in conclusion", "to summarize"}
)
FOCUS_WORDS = frozenset(
    {"algorithm", "complexity", "protocol", "implementation", "syntax", "binary", "hexadecimal"}
)


def _word_hits(text: str, vocab: frozenset[str]) -> int:
    lower = text.lower()
    return sum(1 for w in vocab if w in lower)


def infer_music_mood(text: str, *, scene_index: int, total_scenes: int) -> str:
    """Pick dominant mood label for a teaching narration beat."""
    if scene_index == 0:
        return "transition"
    if scene_index >= max(1, total_scenes - 2):
        return "recap"

    scores = {
        "example": _word_hits(text, EXAMPLE_WORDS) * 2,
        "focus": _word_hits(text, FOCUS_WORDS),
        "recap": _word_hits(text, RECAP_WORDS) * 2,
    }
    if text.strip().endswith("?"):
        scores["focus"] += 1
    if re.search(r"\b(next up|moving on|now let's)\b", text, re.I):
        scores["transition"] = 2

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "calm"
    return best


def plan_music_cue(
    text: str,
    *,
    scene_index: int,
    total_scenes: int,
    base_volume: float = 0.08,
    mood_override: str | None = None,
) -> dict[str, Any]:
    mood = mood_override or infer_music_mood(text, scene_index=scene_index, total_scenes=total_scenes)
    mult = MOOD_VOLUME.get(mood, 0.70)
    return {
        "music_mood": mood,
        "music_volume": round(base_volume * mult, 4),
    }


def smooth_scene_volumes(cues: list[dict[str, Any]], *, floor: float = 0.04) -> list[dict[str, Any]]:
    """Prevent jarring volume jumps between adjacent scenes."""
    if len(cues) < 2:
        return cues
    out = [dict(c) for c in cues]
    for i in range(1, len(out)):
        prev = float(out[i - 1].get("music_volume", floor))
        curr = float(out[i].get("music_volume", floor))
        if abs(curr - prev) > 0.04:
            out[i]["music_volume"] = round((prev + curr) / 2, 4)
    return out
