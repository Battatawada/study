"""Phrase-level beats from segment text + audio duration (authoritative after Phase 2)."""

from __future__ import annotations

import re
from typing import Any

from sece.constants import BEAT_KINDS, SCHEMA_VERSION


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _beat_kind(sentence: str) -> str:
    s = sentence.strip()
    words = s.split()
    if len(words) <= 4 and re.search(r"[A-Z0-9]", s) and s.endswith("."):
        return "concept_label"
    if " vs " in s.lower() or "versus" in s.lower():
        return "contrast"
    if s.lower().startswith(("for example", "imagine", "consider")):
        return "example"
    if s.lower().startswith(("in summary", "to recap", "finally")):
        return "recap"
    return "explanation"


def _beats_from_word_timings(
    segment_id: int,
    sentences: list[str],
    words: list[dict[str, Any]],
    duration_sec: float,
) -> list[dict[str, Any]]:
    """Align sentence beats to word boundary timings when available."""
    if not sentences:
        return []

    full_text = " ".join(sentences)
    beats: list[dict[str, Any]] = []
    word_idx = 0
    n_words = len(words)

    for i, sent in enumerate(sentences):
        sent_words = re.findall(r"\S+", sent)
        if not sent_words:
            continue
        start_word = word_idx
        end_word = min(word_idx + len(sent_words), n_words)
        if start_word < n_words:
            start_sec = float(words[start_word].get("start", 0))
            end_sec = float(words[end_word - 1].get("end", duration_sec)) if end_word > start_word else start_sec
        else:
            # Fallback slice of remaining duration
            frac_start = start_word / max(1, len(re.findall(r"\S+", full_text)))
            frac_end = min(1.0, (start_word + len(sent_words)) / max(1, len(re.findall(r"\S+", full_text))))
            start_sec = duration_sec * frac_start
            end_sec = duration_sec * frac_end

        beat_id = f"s{segment_id}_b{i + 1}"
        beats.append({
            "beat_id": beat_id,
            "start_sec": round(max(0.0, start_sec), 4),
            "end_sec": round(min(duration_sec, max(end_sec, start_sec + 0.05)), 4),
            "text": sent,
            "kind": _beat_kind(sent),
        })
        word_idx = end_word

    return beats


def build_beats_for_segment(
    segment_id: int,
    text: str,
    duration_sec: float,
    *,
    words: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    sentences = _split_sentences(text)
    if not sentences:
        return [{
            "beat_id": f"s{segment_id}_b1",
            "start_sec": 0.0,
            "end_sec": round(max(0.1, duration_sec), 4),
            "text": text.strip(),
            "kind": "unknown",
        }]

    if words:
        raw = _beats_from_word_timings(segment_id, sentences, words, duration_sec)
        for j, b in enumerate(raw):
            b["beat_id"] = f"s{segment_id}_b{j + 1}"
        return _normalize_beat_span(raw, duration_sec)

    tokens = text.split()
    total = max(1, sum(max(1, len(re.sub(r"[^\w']", "", t))) for t in tokens))
    beats: list[dict[str, Any]] = []
    t = 0.0
    for i, sent in enumerate(sentences):
        weight = sum(max(1, len(re.sub(r"[^\w']", "", w))) for w in sent.split())
        span = duration_sec * (weight / total)
        end = min(duration_sec, t + span)
        beats.append({
            "beat_id": f"s{segment_id}_b{i + 1}",
            "start_sec": round(t, 4),
            "end_sec": round(max(end, t + 0.05), 4),
            "text": sent,
            "kind": _beat_kind(sent),
        })
        t = end

    return _normalize_beat_span(beats, duration_sec)


def _normalize_beat_span(beats: list[dict[str, Any]], duration_sec: float) -> list[dict[str, Any]]:
    if not beats:
        return beats
    beats[0]["start_sec"] = 0.0
    beats[-1]["end_sec"] = round(duration_sec, 4)
    for b in beats:
        if b["kind"] not in BEAT_KINDS:
            b["kind"] = "unknown"
    return beats


def build_beats_document(
    segments: list[dict[str, Any]],
    durations: list[dict[str, Any]],
    word_timings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dur_by_id = {int(d["segment_id"] if "segment_id" in d else d["scene_id"]): float(d["duration_sec"]) for d in durations}
    words_by_id: dict[int, list[dict[str, Any]]] = {}
    if word_timings:
        for row in word_timings:
            sid = int(row.get("scene_id", row.get("segment_id", 0)))
            words_by_id[sid] = list(row.get("words", []))

    out_segments: list[dict[str, Any]] = []
    for seg in segments:
        sid = int(seg.get("segment_id", seg.get("scene_id", 0)))
        text = str(seg.get("text", "")).strip()
        dur = dur_by_id.get(sid, 0.5)
        beats = build_beats_for_segment(sid, text, dur, words=words_by_id.get(sid))
        out_segments.append({
            "segment_id": sid,
            "duration_sec": round(dur, 4),
            "beats": beats,
        })

    return {"schema_version": SCHEMA_VERSION, "segments": out_segments}
