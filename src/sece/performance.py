"""Performance Compiler — temporal orchestration of compiled motion channels.

Deterministic post-pass: retimes already-compiled timelines so motion overlaps
naturally while beat anchors remain the narration master clock.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

PERFORMANCE_SCHEMA_VERSION = "1.0"

# Lifecycle profiles: lead_in may be negative (overlap into prior motion)
LIFECYCLE_PROFILES: dict[str, dict[str, float]] = {
    "appear_all": {"lead": 0.00, "main": 0.32, "settle": 0.10, "tail": 0.00, "stagger": 0.09},
    "sync_cells": {"lead": 0.00, "main": 0.32, "settle": 0.10, "tail": 0.00, "stagger": 0.09},
    "set_value": {"lead": -0.06, "main": 0.38, "settle": 0.12, "tail": 0.00, "stagger": 0.0},
    "highlight": {"lead": -0.08, "main": 0.18, "settle": 0.10, "tail": 0.08, "stagger": 0.05},
    "pointer": {"lead": -0.10, "main": 0.65, "settle": 0.15, "tail": 0.00, "stagger": 0.0},
    "pointer_set": {"lead": -0.05, "main": 0.18, "settle": 0.08, "tail": 0.00, "stagger": 0.0},
    "swap": {"lead": 0.00, "main": 0.55, "settle": 0.18, "tail": 0.00, "stagger": 0.0},
    "shift": {"lead": 0.00, "main": 0.22, "settle": 0.08, "tail": 0.00, "stagger": 0.0},
    "link": {"lead": 0.08, "main": 0.35, "settle": 0.10, "tail": 0.00, "stagger": 0.0},
    "caption": {"lead": -0.12, "main": 0.28, "settle": 0.10, "tail": 0.00, "stagger": 0.0},
    "comparison": {"lead": 0.00, "main": 0.50, "settle": 0.12, "tail": 0.00, "stagger": 0.0},
    "camera_pan": {"lead": -0.22, "main": 0.55, "settle": 0.30, "tail": 0.00, "stagger": 0.0},
}

CHANNEL_BY_OP: dict[str, str] = {
    "appear_all": "object",
    "sync_cells": "object",
    "set_value": "object",
    "swap": "object",
    "shift": "object",
    "highlight": "highlight",
    "pointer": "pointer",
    "pointer_set": "pointer",
    "link": "connector",
    "caption": "text",
    "comparison": "object",
    "camera_pan": "camera",
}

# Cross-channel overlap: child starts this fraction into parent's main phase
OVERLAP_INTO_PARENT = 0.35
SETTLE_BLEED_RATIO = 0.50

DEFAULT_CONFIG: dict[str, float] = {
    "max_late_slack_sec": 0.08,
    "stagger_budget_sec": 0.07,
    "overlap_ratio": 0.35,
    "settle_bleed_ratio": SETTLE_BLEED_RATIO,
    "camera_anticipation_sec": 0.22,
    "pad_end_sec": 0.15,
    "duration_floor_ratio": 0.65,
}


@dataclass
class PerformanceTrack:
    track_id: str
    channel: str
    op: str
    beat_id: str | None
    anchor_sec: float
    priority: int
    lead_in: float
    main_sec: float
    settle_sec: float
    tail_sec: float
    start_sec: float = 0.0
    source_index: int = 0
    source_op: dict[str, Any] = field(default_factory=dict)
    entity_key: str = ""

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.main_sec + self.settle_sec + self.tail_sec

    @property
    def main_start(self) -> float:
        return self.start_sec

    @property
    def main_end(self) -> float:
        return self.start_sec + self.main_sec


def _perf_config(pipeline: dict[str, Any] | None) -> dict[str, float]:
    cfg = dict(DEFAULT_CONFIG)
    sece = (pipeline or {}).get("composition_engine", {})
    if isinstance(sece, dict):
        perf = sece.get("performance", {})
        if isinstance(perf, dict):
            for k, v in perf.items():
                if k in cfg and isinstance(v, (int, float)):
                    cfg[k] = float(v)
    return cfg


def _deterministic_jitter(entity_key: str, segment_id: int, op_index: int, budget: float) -> float:
    if budget <= 0:
        return 0.0
    h = hash((entity_key, segment_id, op_index)) & 0xFFFFFFFF
    return (h % 1000) / 1000.0 * budget


def _beat_map(beats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {b["beat_id"]: b for b in beats if b.get("beat_id")}


def _anchor_for_op(
    op: dict[str, Any],
    op_index: int,
    beats: list[dict[str, Any]],
    beat_by_id: dict[str, dict[str, Any]],
) -> tuple[str | None, float]:
    bid = op.get("trigger_beat_id")
    if bid and bid in beat_by_id:
        return bid, float(beat_by_id[bid]["start_sec"])
    at = float(op.get("at", 0))
    for beat in beats:
        start = float(beat.get("start_sec", 0))
        end = float(beat.get("end_sec", start))
        if start <= at < end:
            return beat.get("beat_id"), start
    if beats:
        idx = min(op_index, len(beats) - 1)
        b = beats[idx]
        return b.get("beat_id"), float(b.get("start_sec", at))
    return None, at


def _entity_key_from_op(op: dict[str, Any], op_index: int) -> str:
    for key in ("entity_id", "index", "from", "to", "a", "b", "name"):
        if key in op:
            return f"{op['op']}:{key}:{op[key]}"
    return f"{op.get('op', 'op')}:{op_index}"


def _priority_for_op(
    op: dict[str, Any],
    beat_id: str | None,
    attention: dict[str, Any],
) -> int:
    att_by_beat = {a["beat_id"]: a for a in attention.get("timeline", [])}
    att = att_by_beat.get(beat_id or "", {})
    primary = att.get("primary_entity_id")
    if not primary:
        return 1
    indices = op.get("indices") or []
    idx = op.get("index")
    if idx is not None and f"index:{idx}" in _entity_key_from_op(op, 0):
        pass
    entity_refs = {str(op.get(k, "")) for k in ("entity_id", "from", "to", "a", "b")}
    if primary in entity_refs:
        return 0
    if op.get("op") in ("caption", "comparison"):
        return 1
    if indices:
        return 1
    if op.get("op") in ("highlight", "pointer", "pointer_set"):
        return 1
    return 2


def _profile_for_op(op: str, source_op: dict[str, Any]) -> dict[str, float]:
    prof = dict(LIFECYCLE_PROFILES.get(op, {"lead": 0.0, "main": 0.4, "settle": 0.1, "tail": 0.0, "stagger": 0.0}))
    dur = source_op.get("duration")
    if isinstance(dur, (int, float)) and dur > 0:
        prof["main"] = float(dur)
    return prof


def _decompose_tracks(
    timeline: list[dict[str, Any]],
    beats: list[dict[str, Any]],
    attention: dict[str, Any],
    segment_id: int,
) -> list[PerformanceTrack]:
    beat_by_id = _beat_map(beats)
    tracks: list[PerformanceTrack] = []

    for i, op in enumerate(timeline):
        kind = str(op.get("op", ""))
        beat_id, anchor = _anchor_for_op(op, i, beats, beat_by_id)
        prof = _profile_for_op(kind, op)
        channel = CHANNEL_BY_OP.get(kind, "object")
        priority = _priority_for_op(op, beat_id, attention)
        entity_key = _entity_key_from_op(op, i)

        if kind == "appear_all":
            vals = op.get("values") or []
            stagger = float(op.get("stagger", prof.get("stagger", 0.09)))
            for j, _ in enumerate(vals):
                tracks.append(PerformanceTrack(
                    track_id=f"seg{segment_id}:{kind}:{i}:cell{j}",
                    channel="object",
                    op=kind,
                    beat_id=beat_id,
                    anchor_sec=anchor,
                    priority=priority,
                    lead_in=prof["lead"] + j * stagger,
                    main_sec=prof["main"],
                    settle_sec=prof["settle"],
                    tail_sec=prof["tail"],
                    source_index=i,
                    source_op=op,
                    entity_key=f"cell:{j}",
                ))
            continue

        tracks.append(PerformanceTrack(
            track_id=f"seg{segment_id}:{kind}:{i}",
            channel=channel,
            op=kind,
            beat_id=beat_id,
            anchor_sec=anchor,
            priority=priority,
            lead_in=prof["lead"],
            main_sec=prof["main"],
            settle_sec=prof["settle"],
            tail_sec=prof["tail"],
            source_index=i,
            source_op=op,
            entity_key=entity_key,
        ))

    return tracks


def _decompose_camera_tracks(
    camera_channel: list[dict[str, Any]],
    segment_id: int,
) -> list[PerformanceTrack]:
    prof = LIFECYCLE_PROFILES["camera_pan"]
    tracks: list[PerformanceTrack] = []
    for i, seg in enumerate(camera_channel):
        anchor = float(seg.get("at_sec", 0))
        main = float(seg.get("duration_sec", prof["main"]))
        tracks.append(PerformanceTrack(
            track_id=f"seg{segment_id}:camera:{i}",
            channel="camera",
            op="camera_pan",
            beat_id=seg.get("beat_id"),
            anchor_sec=anchor,
            priority=0,
            lead_in=prof["lead"],
            main_sec=main,
            settle_sec=prof["settle"],
            tail_sec=prof["tail"],
            source_index=i,
            source_op=seg,
            entity_key=f"camera:{i}",
        ))
    return tracks


def _assign_starts(
    tracks: list[PerformanceTrack],
    segment_id: int,
    cfg: dict[str, float],
) -> None:
    """Initial start = anchor + lead_in + jitter."""
    budget = cfg["stagger_budget_sec"]
    by_channel_anchor: dict[tuple[str, float], int] = {}

    for track in tracks:
        key = (track.channel, round(track.anchor_sec, 4))
        idx = by_channel_anchor.get(key, 0)
        by_channel_anchor[key] = idx + 1
        jitter = _deterministic_jitter(track.entity_key, segment_id, track.source_index + idx, budget)
        track.start_sec = round(max(0.0, track.anchor_sec + track.lead_in + jitter), 4)


def _inject_overlaps(tracks: list[PerformanceTrack], cfg: dict[str, float]) -> None:
    """Pull dependent channels into parent motion windows."""
    object_tracks = [t for t in tracks if t.channel == "object"]
    settle_bleed = cfg["settle_bleed_ratio"]
    overlap = cfg["overlap_ratio"]

    # Group object tracks by beat anchor
    objects_by_anchor: dict[float, list[PerformanceTrack]] = {}
    for t in object_tracks:
        objects_by_anchor.setdefault(round(t.anchor_sec, 4), []).append(t)

    for track in tracks:
        anchor = round(track.anchor_sec, 4)
        peers = objects_by_anchor.get(anchor, [])

        if track.channel == "highlight" and peers:
            parent = peers[0]
            overlap_start = parent.main_start + overlap * parent.main_sec
            track.start_sec = round(min(track.start_sec, overlap_start), 4)

        elif track.channel == "pointer" and peers:
            parent = peers[0]
            overlap_start = parent.main_start + OVERLAP_INTO_PARENT * parent.main_sec
            track.start_sec = round(min(track.start_sec, overlap_start), 4)

        elif track.channel == "text" and peers:
            parent = peers[0]
            overlap_start = max(track.anchor_sec - 0.12, parent.main_start + 0.20)
            track.start_sec = round(min(track.start_sec, overlap_start), 4)

        elif track.channel == "connector" and peers:
            parent = peers[0]
            lag_start = parent.main_start + 0.25 * parent.main_sec
            track.start_sec = round(max(track.start_sec, lag_start), 4)

        elif track.channel == "camera":
            antic = cfg["camera_anticipation_sec"]
            track.start_sec = round(max(0.0, track.anchor_sec - antic), 4)

    # Settle bleed: next-beat tracks may start during prior settle
    sorted_anchors = sorted({round(t.anchor_sec, 4) for t in tracks})
    for i in range(1, len(sorted_anchors)):
        prev_anchor = sorted_anchors[i - 1]
        next_anchor = sorted_anchors[i]
        prev_tracks = [t for t in tracks if round(t.anchor_sec, 4) == prev_anchor]
        next_tracks = [t for t in tracks if round(t.anchor_sec, 4) == next_anchor]
        if not prev_tracks or not next_tracks:
            continue
        prev_end = max(t.start_sec + t.main_sec + t.settle_sec for t in prev_tracks)
        bleed_start = prev_end - settle_bleed * max(t.settle_sec for t in prev_tracks)
        for nt in next_tracks:
            if nt.priority > 0:
                nt.start_sec = round(min(nt.start_sec, max(nt.anchor_sec + nt.lead_in, bleed_start)), 4)


def _enforce_anchor_slack(tracks: list[PerformanceTrack], cfg: dict[str, float]) -> None:
    slack = cfg["max_late_slack_sec"]
    for track in tracks:
        if track.priority > 0:
            continue
        latest = track.anchor_sec + slack
        if track.start_sec > latest:
            track.start_sec = round(latest, 4)


def _compress_to_fit(
    tracks: list[PerformanceTrack],
    duration_sec: float,
    cfg: dict[str, float],
) -> int:
    """Compress settle/tail then non-primary main. Returns pass count."""
    pad = cfg["pad_end_sec"]
    ceiling = duration_sec - pad
    passes = 0
    floor_ratio = cfg["duration_floor_ratio"]

    for _ in range(8):
        max_end = max((t.end_sec for t in tracks), default=0.0)
        if max_end <= ceiling + 0.001:
            break
        passes += 1
        overflow = max_end - ceiling

        # Pass 1: shrink tail
        for t in sorted(tracks, key=lambda x: -x.priority):
            if overflow <= 0:
                break
            if t.tail_sec > 0:
                cut = min(t.tail_sec, overflow)
                t.tail_sec = round(t.tail_sec - cut, 4)
                overflow -= cut

        # Pass 2: shrink settle
        for t in sorted(tracks, key=lambda x: -x.priority):
            if overflow <= 0:
                break
            if t.settle_sec > 0.04:
                cut = min(t.settle_sec - 0.04, overflow)
                t.settle_sec = round(t.settle_sec - cut, 4)
                overflow -= cut

        # Pass 3: shrink main for non-primary
        for t in sorted(tracks, key=lambda x: -x.priority):
            if overflow <= 0:
                break
            if t.priority > 0 and t.main_sec > 0.12:
                floor = t.main_sec * floor_ratio
                cut = min(t.main_sec - floor, overflow)
                if cut > 0:
                    t.main_sec = round(t.main_sec - cut, 4)
                    overflow -= cut

    return passes


def _synthesize_secondary(tracks: list[PerformanceTrack], segment_id: int) -> list[dict[str, Any]]:
  secondary: list[dict[str, Any]] = []
  for track in tracks:
      if track.op == "highlight":
          secondary.append({
              "op": "pulse",
              "parent_track_id": track.track_id,
              "at_sec": round(track.main_start + 0.4 * track.main_sec, 4),
              "duration_sec": round(track.settle_sec + track.tail_sec, 4),
              "target": track.entity_key,
              "intensity": 0.6,
          })
      elif track.op == "swap":
          secondary.append({
              "op": "glow",
              "parent_track_id": track.track_id,
              "at_sec": round(track.main_start + 0.2 * track.main_sec, 4),
              "duration_sec": round(track.main_sec * 0.6, 4),
              "target": track.entity_key,
              "intensity": 0.5,
          })
      elif track.op == "link":
          secondary.append({
              "op": "connector_emphasis",
              "parent_track_id": track.track_id,
              "at_sec": round(track.main_start + 0.5 * track.main_sec, 4),
              "duration_sec": round(track.main_sec * 0.5, 4),
              "target": track.entity_key,
              "intensity": 0.7,
          })
      elif track.op == "pointer":
          secondary.append({
              "op": "ripple",
              "parent_track_id": track.track_id,
              "at_sec": round(track.main_start + track.main_sec - 0.08, 4),
              "duration_sec": 0.12,
              "target": track.entity_key,
              "intensity": 0.55,
          })
  return secondary


def _emit_timeline(
    timeline: list[dict[str, Any]],
    tracks: list[PerformanceTrack],
) -> list[dict[str, Any]]:
    """Map tracks back to timeline ops (one row per source op; appear_all uses earliest cell)."""
    by_source: dict[int, list[PerformanceTrack]] = {}
    for t in tracks:
        if t.channel == "camera":
            continue
        by_source.setdefault(t.source_index, []).append(t)

    out: list[dict[str, Any]] = []
    for i, op in enumerate(timeline):
        rows = by_source.get(i, [])
        if not rows:
            out.append(dict(op))
            continue
        row = dict(op)
        start = min(r.start_sec for r in rows)
        main = max(r.main_sec for r in rows)
        settle = max(r.settle_sec for r in rows)
        row["at"] = round(start, 4)
        row["duration"] = round(main, 4)
        if "settle_sec" not in row:
            row["settle_sec"] = round(settle, 4)
        if op.get("op") == "appear_all" and len(rows) > 1:
            stagger = round(rows[1].start_sec - rows[0].start_sec, 4) if len(rows) > 1 else op.get("stagger", 0.09)
            row["stagger"] = stagger
        out.append(row)
    return out


def _emit_camera(
    camera_channel: list[dict[str, Any]],
    camera_tracks: list[PerformanceTrack],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(camera_channel):
        track = next((t for t in camera_tracks if t.source_index == i), None)
        row = dict(seg)
        if track:
            row["at_sec"] = round(track.start_sec, 4)
            row["duration_sec"] = round(track.main_sec + track.settle_sec, 4)
        out.append(row)
    return out


def _compute_metrics(
    tracks: list[PerformanceTrack],
    duration_sec: float,
    compression_passes: int,
) -> dict[str, Any]:
    if not tracks or duration_sec <= 0:
        return {
            "overlap_ratio": 0.0,
            "avg_concurrent_tracks": 0.0,
            "max_concurrent_tracks": 0,
            "track_count": 0,
            "secondary_event_count": 0,
            "compression_passes": compression_passes,
            "compression_applied": compression_passes > 0,
            "procedural_score": 1.0,
        }

    step = 0.05
    samples = max(1, int(duration_sec / step))
    concurrent_samples: list[int] = []

    for s in range(samples):
        t = s * step
        count = sum(1 for tr in tracks if tr.start_sec <= t < tr.end_sec)
        concurrent_samples.append(count)

    overlap_ratio = sum(1 for c in concurrent_samples if c >= 2) / len(concurrent_samples)
    avg_concurrent = sum(concurrent_samples) / len(concurrent_samples)
    max_concurrent = max(concurrent_samples)

    # procedural_score: 1 = fully sequential (always <=1 concurrent)
    procedural_score = 1.0 - overlap_ratio

    return {
        "overlap_ratio": round(overlap_ratio, 4),
        "avg_concurrent_tracks": round(avg_concurrent, 4),
        "max_concurrent_tracks": max_concurrent,
        "track_count": len(tracks),
        "compression_passes": compression_passes,
        "compression_applied": compression_passes > 0,
        "procedural_score": round(procedural_score, 4),
    }


def performance_enabled(pipeline: dict[str, Any] | None) -> bool:
    sece = (pipeline or {}).get("composition_engine", {})
    if not isinstance(sece, dict) or not sece.get("enabled", False):
        return False
    perf = sece.get("performance", {})
    if isinstance(perf, bool):
        return perf
    if isinstance(perf, dict):
        return perf.get("enabled", True)
    return True


def compile_segment_performance(
    segment: dict[str, Any],
    *,
    render_ir: dict[str, Any],
    attention: dict[str, Any],
    camera: dict[str, Any],
    animation_spec: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Orchestrate temporal overlap for one segment. Returns performance_spec + retimed render_ir."""
    sid = int(segment.get("segment_id", render_ir.get("segment_id", 0)))
    duration_sec = float(segment.get("duration_sec", render_ir.get("duration_sec", 0.5)))
    beats = list(segment.get("beats", []))
    cfg = _perf_config(pipeline)

    timeline = list(render_ir.get("timeline", []))
    camera_channel = list(render_ir.get("camera") or camera.get("channel", []))

    motion_tracks = _decompose_tracks(timeline, beats, attention, sid)
    camera_tracks = _decompose_camera_tracks(camera_channel, sid)
    all_tracks = motion_tracks + camera_tracks

    _assign_starts(all_tracks, sid, cfg)
    _inject_overlaps(all_tracks, cfg)
    _enforce_anchor_slack(all_tracks, cfg)
    compression_passes = _compress_to_fit(all_tracks, duration_sec, cfg)

    secondary = _synthesize_secondary(motion_tracks, sid)
    retimed_timeline = _emit_timeline(timeline, motion_tracks)
    retimed_camera = _emit_camera(camera_channel, camera_tracks)
    metrics = _compute_metrics(all_tracks, duration_sec, compression_passes)
    metrics["secondary_event_count"] = len(secondary)

    out_ir = copy.deepcopy(render_ir)
    out_ir["timeline"] = retimed_timeline
    out_ir["camera"] = retimed_camera
    out_ir["performance"] = {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "overlap_ratio": metrics["overlap_ratio"],
        "track_count": metrics["track_count"],
        "secondary_count": len(secondary),
        "secondary_timeline": secondary,
    }

    beat_clock = [
        {
            "beat_id": b.get("beat_id"),
            "start_sec": float(b.get("start_sec", 0)),
            "end_sec": float(b.get("end_sec", 0)),
            "primary_entity_id": next(
                (a.get("primary_entity_id") for a in attention.get("timeline", [])
                 if a.get("beat_id") == b.get("beat_id")),
                None,
            ),
        }
        for b in beats
    ]

    tracks_out = [
        {
            "track_id": t.track_id,
            "channel": t.channel,
            "op": t.op,
            "beat_id": t.beat_id,
            "anchor_sec": t.anchor_sec,
            "start_sec": t.start_sec,
            "end_sec": round(t.end_sec, 4),
            "priority": t.priority,
        }
        for t in all_tracks
    ]

    return {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "segment_id": sid,
        "duration_sec": duration_sec,
        "beat_clock": beat_clock,
        "tracks": tracks_out,
        "secondary_timeline": secondary,
        "retimed": {
            "timeline": retimed_timeline,
            "camera": retimed_camera,
        },
        "metrics": metrics,
        "render_ir": out_ir,
        "provenance": {
            "orchestration_profile": "default_v1",
            "animation_spec_present": bool(animation_spec),
        },
    }


def compile_performance_document(
    aligned_plan: dict[str, Any],
    compiled: dict[str, Any],
    *,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run performance compiler across all segments; update render_ir in compiled bundle."""
    if not performance_enabled(pipeline):
        return {"schema_version": PERFORMANCE_SCHEMA_VERSION, "segments": [], "enabled": False}

    segments_aligned = {int(s["segment_id"]): s for s in aligned_plan.get("segments", [])}
    attention_by_id = {
        int(a["segment_id"]): a
        for a in compiled.get("attention", {}).get("segments", [])
    }
    camera_by_id = {
        int(c["segment_id"]): c
        for c in compiled.get("camera", {}).get("segments", [])
    }

    perf_segments: list[dict[str, Any]] = []
    ir_segments = compiled.get("render_ir", {}).get("segments", [])

    for ir_row in ir_segments:
        sid = int(ir_row["segment_id"])
        segment = segments_aligned.get(sid, {})
        attention = attention_by_id.get(sid, {"timeline": []})
        camera = camera_by_id.get(sid, {"channel": []})
        perf = compile_segment_performance(
            segment,
            render_ir=ir_row.get("render_ir", {}),
            attention=attention,
            camera=camera,
            animation_spec=ir_row.get("animation_spec"),
            pipeline=pipeline,
        )
        ir_row["render_ir"] = perf["render_ir"]
        perf_segments.append({k: v for k, v in perf.items() if k != "render_ir"})

    return {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "enabled": True,
        "segments": perf_segments,
    }
