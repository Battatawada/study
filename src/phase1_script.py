#!/usr/bin/env python3
"""
Phase 1 — Teaching explainer script + visual scene map

  1. Pick next topic from queue
  2. NotebookLM: style brief → hook package → explainer script (multi-part)
  3. NotebookLM: map each narration scene → slide visual spec
  4. YouTube SEO (locked title) + thumbnail brief
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    CONFIG,
    append_topic_history,
    clean_script_for_tts,
    clips_to_scenes,
    notebooklm_style_brief,
    PLAYBOOK_STYLE_BRIEF,
    estimate_scene_count,
    extract_json_blocks,
    extract_notebook_id,
    extract_source_id,
    fallback_seo,
    filter_topics_against_history,
    format_topic_history_for_prompt,
    is_transient_notebooklm_error,
    load_json,
    load_prompt,
    load_topic_history,
    new_run_id,
    notebooklm_ask,
    notebooklm_json_with_retry,
    notebooklm_source_add,
    parse_numbered_topics,
    parse_hook_package_json,
    parse_seo_json,
    sanitize_seo_title,
    parse_total_parts,
    save_json,
    validate_scene_clips,
    split_script_for_scenes,
    strip_markdown,
    strip_total_parts_header,
    topic_overlaps_history,
)
from srt_parser import SubtitleBlock, load_srt, normalize_subtitle_range, parse_srt, resolve_line_range, srt_to_llm_index, subtitle_index_bounds


def wait_sources(
    notebook_id: str,
    source_ids: list[str],
    *,
    timeout: int = 900,
    max_attempts: int = 5,
) -> None:
    import subprocess

    for idx, sid in enumerate(source_ids, start=1):
        print(f"  Waiting for source {idx}/{len(source_ids)} ({sid[:8]}...)", flush=True)
        last_err = ""
        for attempt in range(max_attempts):
            result = subprocess.run(
                [
                    "notebooklm", "source", "wait", sid,
                    "-n", notebook_id, "--timeout", str(timeout), "--interval", "3",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                break
            last_err = (result.stderr or result.stdout or "source wait failed").strip()
            if attempt + 1 < max_attempts and is_transient_notebooklm_error(last_err):
                time.sleep(20 * (attempt + 1))
                continue
            raise RuntimeError(f"Source {sid} failed: {last_err}")


def ask(
    notebook_id: str,
    prompt: str,
    *,
    new: bool = False,
    retries: int = 6,
    request_timeout: int = 300,
    source_ids: list[str] | None = None,
) -> str:
    return notebooklm_ask(
        notebook_id,
        prompt,
        new=new,
        source_ids=source_ids,
        request_timeout=request_timeout,
        retries=retries,
    )


def _attach_playbook_source(notebook_id: str, pipeline: dict[str, Any]) -> str | None:
    """Add channel_playbook.md as a notebook source so prompts stay short."""
    if pipeline.get("ingest_youtube_style_sources", False):
        return None
    playbook = CONFIG / "channel_playbook.md"
    if not playbook.exists():
        return None
    print("  Adding channel_playbook.md to notebook...", flush=True)
    added = notebooklm_source_add(
        notebook_id,
        str(playbook.resolve()),
        request_timeout=int(pipeline.get("source_request_timeout", 180)),
        reconcile_timeout=float(pipeline.get("source_reconcile_timeout", 90)),
    )
    source_id = extract_source_id(added)
    wait_sources(notebook_id, [source_id], timeout=int(pipeline.get("source_wait_timeout", 900)))
    return source_id


def collect_multipart_text(
    notebook_id: str,
    initial_prompt: str,
    continue_word: str = "Next",
    *,
    new: bool = False,
    source_ids: list[str] | None = None,
) -> tuple[str, int]:
    first = ask(notebook_id, initial_prompt, new=new, source_ids=source_ids)
    total = parse_total_parts(first)
    chunks = [clean_script_for_tts(strip_total_parts_header(strip_markdown(first)))]
    for part_num in range(2, total + 1):
        print(f"  Story part {part_num}/{total}...", flush=True)
        cont = ask(notebook_id, continue_word, source_ids=source_ids)
        chunks.append(clean_script_for_tts(strip_total_parts_header(strip_markdown(cont))))
    return "\n\n".join(c for c in chunks if c), total


def fetch_srt_text(movie_slug: str, pipeline: dict[str, Any]) -> str:
    """Load SRT from VPS API or local movies dir."""
    local_root = Path(os.environ.get("LOCAL_MOVIES_DIR", CONFIG / "movies"))
    local_srt = local_root / movie_slug / "subtitles.srt"
    if local_srt.exists():
        print(f"  SRT from local: {local_srt}", flush=True)
        return local_srt.read_text(encoding="utf-8", errors="replace")

    base = os.environ.get("VPS_URL", "").rstrip("/")
    secret = os.environ.get("VPS_SECRET", "")
    if not base or not secret:
        raise RuntimeError(
            f"No SRT at {local_srt} and VPS_URL/VPS_SECRET not set. "
            "Place subtitles on VPS or set LOCAL_MOVIES_DIR."
        )
    from common import httpx_get_json_with_retry

    data = httpx_get_json_with_retry(
        f"{base}/movies/{movie_slug}/srt",
        headers={"Authorization": f"Bearer {secret}"},
        timeout=120.0,
    )
    content = data.get("content") or data.get("srt") or ""
    if not content:
        raise RuntimeError(f"VPS returned empty SRT for {movie_slug}")
    print(f"  SRT from VPS ({data.get('line_count', '?')} lines)", flush=True)
    return content


def pick_topic_from_queue(history: list[dict[str, Any]]) -> dict[str, Any]:
    queue = load_json(CONFIG / "topic_queue.json")
    topics = [t for t in queue.get("topics", []) if t.get("enabled", True)]
    for topic in topics:
        label = topic.get("topic") or topic.get("title", topic["slug"])
        if topic_overlaps_history(label, history) or topic_overlaps_history(topic.get("slug", ""), history):
            print(f"  Skipping queued topic (already done): {label}", flush=True)
            continue
        return topic
    raise RuntimeError("No enabled topics left in topic_queue.json (all done or disabled).")


def pick_movie_from_queue(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Legacy alias — redirects to topic queue."""
    return pick_topic_from_queue(history)


def pick_topic_from_notebook(
    notebook_id: str,
    history: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (topic_label, movie_slug) from NotebookLM topic list + queue match."""
    past_topics = format_topic_history_for_prompt(history)
    topics_prompt = load_prompt("topics_finding.txt").replace("{past_topics}", past_topics)
    topics_raw = ask(notebook_id, topics_prompt, new=True)
    parsed = parse_numbered_topics(topics_raw)
    kept, rejected = filter_topics_against_history(parsed, history)
    for t, reason in rejected:
        print(f"  Topic blocked: {t[:80]} — {reason}", flush=True)
    if not kept:
        raise RuntimeError("No fresh movie topics from NotebookLM")

    topics_list = "\n".join(f"{i}. {t}" for i, t in enumerate(kept[:10], 1))
    pick_prompt = load_prompt("pick_topic.txt").replace("{topics_list}", topics_list)
    topic = ask(notebook_id, pick_prompt, new=True).strip().splitlines()[0].strip()
    if topic_overlaps_history(topic, history):
        topic = kept[0]

    queue = load_json(CONFIG / "movie_queue.json")
    slug = _match_queue_slug(topic, queue.get("movies", []))
    if not slug:
        raise RuntimeError(
            f"Picked topic not in movie_queue.json: {topic}. "
            "Add the film to config/movie_queue.json with matching slug on VPS."
        )
    return topic, slug


def _match_queue_slug(topic: str, movies: list[dict[str, Any]]) -> str | None:
    norm = re.sub(r"[^a-z0-9]", "", topic.lower())
    for m in movies:
        title = str(m.get("title", ""))
        year = str(m.get("year", ""))
        slug = str(m.get("slug", ""))
        blob = re.sub(r"[^a-z0-9]", "", f"{title}{year}".lower())
        if blob and blob in norm:
            return slug
        if slug.replace("-", "") in norm:
            return slug
    return None


def build_visual_mapping_prompt(
    segments: list[str],
    pipeline: dict[str, Any],
    *,
    scene_id_start: int = 1,
) -> str:
    seg_chars = int(pipeline.get("scene_map_segment_chars", 80))
    scene_id_end = scene_id_start + len(segments) - 1

    def _render(seg_len: int) -> str:
        scene_lines = "\n".join(
            f"Scene {scene_id_start + i}: {seg[:seg_len]}{'...' if len(seg) > seg_len else ''}"
            for i, seg in enumerate(segments)
        )
        return (
            load_prompt("visual_mapping.txt")
            .replace("{scene_count}", str(len(segments)))
            .replace("{scene_id_start}", str(scene_id_start))
            .replace("{scene_id_end}", str(scene_id_end))
            .replace("{narration_scenes}", scene_lines)
        )

    from common import MAX_NOTEBOOKLM_ASK_CHARS

    # Leave margin for retry suffixes (e.g. "Reply with ONLY raw JSON...")
    max_prompt = MAX_NOTEBOOKLM_ASK_CHARS - 64

    prompt = _render(seg_chars)
    while len(prompt) > max_prompt and seg_chars > 20:
        seg_chars -= 10
        prompt = _render(seg_chars)
    return prompt


def collect_visual_mapping(
    notebook_id: str,
    segments: list[str],
    pipeline: dict[str, Any],
    *,
    source_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Map narration scenes to slide visual specs."""
    batch_size = max(1, int(pipeline.get("scene_map_batch_size", 12)))
    all_mapping: list[dict[str, Any]] = []
    raw_parts: list[str] = []
    scene_id_start = 1
    total_batches = (len(segments) + batch_size - 1) // batch_size

    for batch_start in range(0, len(segments), batch_size):
        batch_segments = segments[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        scene_id_end = scene_id_start + len(batch_segments) - 1

        if total_batches > 1:
            print(
                f"  Visual map batch {batch_num}/{total_batches} "
                f"(scenes {scene_id_start}-{scene_id_end})...",
                flush=True,
            )

        map_prompt = build_visual_mapping_prompt(batch_segments, pipeline, scene_id_start=scene_id_start)
        map_raw = ask(
            notebook_id,
            map_prompt,
            new=True,
            request_timeout=300,
            source_ids=source_ids,
        )
        raw_parts.append(map_raw)
        try:
            batch_mapping = parse_scene_mapping(map_raw, len(batch_segments))
        except ValueError:
            print("  Retrying visual map batch with stricter JSON prompt...", flush=True)
            retry = map_prompt + "\n\nReply with ONLY raw JSON. No markdown."
            map_raw = ask(notebook_id, retry, new=True, request_timeout=300, source_ids=source_ids)
            raw_parts[-1] = map_raw
            batch_mapping = parse_scene_mapping(map_raw, len(batch_segments))

        for i, row in enumerate(batch_mapping):
            normalized = dict(row)
            normalized["scene_id"] = scene_id_start + i
            all_mapping.append(normalized)

        scene_id_start += len(batch_segments)

    return all_mapping, "\n\n---\n\n".join(raw_parts)


VALID_DIAGRAM_TYPES = frozenset({
    "http_request",
    "http_cache",
    "http_redirect",
    "http_error_client",
    "http_error_server",
    "status_code",
    "comparison",
    "flow_steps",
    "list_items",
    "concept",
})


def _infer_diagram_type(scene: dict[str, Any]) -> str:
    """Fallback when NotebookLM omits diagram_type — uses vps diagram_renderer."""
    vps_dir = Path(__file__).resolve().parents[1] / "vps"
    if str(vps_dir) not in sys.path:
        sys.path.insert(0, str(vps_dir))
    from diagram_renderer import infer_diagram_type  # noqa: WPS433

    return infer_diagram_type(scene)


def _normalize_diagram_labels(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()][:4]


def enrich_diagram_spec(row: dict[str, Any], narration: str) -> tuple[str, str, list[str]]:
    """Resolve diagram_type, diagram_prompt, diagram_labels for one scene."""
    probe = {
        **row,
        "narration": narration,
        "visual_title": row.get("visual_title", ""),
        "visual_bullets": row.get("visual_bullets", []),
    }
    diagram_type = str(row.get("diagram_type", "")).strip().lower()
    if diagram_type not in VALID_DIAGRAM_TYPES:
        diagram_type = _infer_diagram_type(probe)

    diagram_prompt = str(row.get("diagram_prompt", "")).strip()
    diagram_labels = _normalize_diagram_labels(row.get("diagram_labels"))

    return diagram_type, diagram_prompt, diagram_labels


def resolve_scene_visuals(
    mapping: list[dict[str, Any]],
    segments: list[str],
    pipeline: dict[str, Any],
) -> list[dict[str, Any]]:
    default_accent = pipeline.get("slide_accent_default", "#3B82F6")
    out: list[dict[str, Any]] = []

    for i, row in enumerate(mapping):
        sid = int(row.get("scene_id", i + 1))
        text = segments[i] if i < len(segments) else ""
        bullets = row.get("visual_bullets", [])
        if isinstance(bullets, str):
            bullets = [bullets]
        diagram_type, diagram_prompt, diagram_labels = enrich_diagram_spec(row, text)
        out.append({
            "scene_id": sid,
            "narration": text,
            "visual_title": str(row.get("visual_title", f"Concept {sid}")).strip(),
            "visual_bullets": [str(b).strip() for b in bullets if str(b).strip()][:3],
            "visual_type": row.get("visual_type", "concept_card"),
            "diagram_type": diagram_type,
            "diagram_prompt": diagram_prompt,
            "diagram_labels": diagram_labels,
            "accent_color": row.get("accent_color", default_accent),
            "music_mood": row.get("music_mood", "calm"),
        })
    return out


def build_scene_mapping_prompt(
    segments: list[str],
    blocks: list[SubtitleBlock],
    pipeline: dict[str, Any],
    *,
    scene_id_start: int = 1,
    subtitle_hint: str = "",
    index_start_line: int = 1,
) -> str:
    seg_chars = int(pipeline.get("scene_map_segment_chars", 80))
    index_blocks = int(pipeline.get("scene_map_index_blocks", 40))
    scene_id_end = scene_id_start + len(segments) - 1
    start_idx = max(0, index_start_line - 1)
    _, max_subtitle_line = subtitle_index_bounds(blocks)

    def _render(seg_len: int, sample_count: int) -> str:
        scene_lines = "\n".join(
            f"Scene {scene_id_start + i}: {seg[:seg_len]}{'...' if len(seg) > seg_len else ''}"
            for i, seg in enumerate(segments)
        )
        return (
            load_prompt("scene_mapping.txt")
            .replace("{scene_count}", str(len(segments)))
            .replace("{scene_id_start}", str(scene_id_start))
            .replace("{scene_id_end}", str(scene_id_end))
            .replace("{max_subtitle_line}", str(max_subtitle_line))
            .replace("{narration_scenes}", scene_lines)
            .replace("{subtitle_hint}", subtitle_hint)
            .replace(
                "{subtitle_index_sample}",
                srt_to_llm_index(blocks[start_idx : start_idx + sample_count]),
            )
            .replace("{max_clip_sec}", str(pipeline.get("max_clip_source_sec", 8.0)))
        )

    prompt = _render(seg_chars, index_blocks)
    from common import MAX_NOTEBOOKLM_ASK_CHARS

    while len(prompt) > MAX_NOTEBOOKLM_ASK_CHARS and (seg_chars > 20 or index_blocks > 10):
        if seg_chars > 20:
            seg_chars -= 10
        if index_blocks > 10:
            index_blocks = max(10, index_blocks - 5)
        prompt = _render(seg_chars, index_blocks)
    return prompt


def build_story_generation_prompt(
    topic_title: str,
    duration: int,
    continue_word: str,
    target_words: int,
    locked_title: str,
    cold_open: str,
    style_notes: str,
) -> str:
    """Assemble story prompt and trim inline fields to stay under NotebookLM limits."""
    from common import MAX_NOTEBOOKLM_ASK_CHARS

    style = style_notes
    cold = cold_open or "(Write a strong cold open matching the locked title.)"

    def render() -> str:
        return (
            load_prompt("story_generation.txt")
            .replace("{topic_title}", topic_title)
            .replace("{duration_minutes}", str(duration))
            .replace("{continue_keyword}", continue_word)
            .replace("{target_words}", str(target_words))
            .replace("{style_notes}", style)
            .replace("{locked_title}", locked_title)
            .replace("{cold_open}", cold)
        )

    prompt = render()
    while len(prompt) > MAX_NOTEBOOKLM_ASK_CHARS:
        if len(style) > len(PLAYBOOK_STYLE_BRIEF):
            style = style[: max(len(PLAYBOOK_STYLE_BRIEF), len(style) - 300)]
        elif len(cold) > 400:
            cold = cold[: max(400, len(cold) - 300)].rstrip() + "…"
        else:
            raise RuntimeError(
                f"Story prompt still too long ({len(prompt)} chars > {MAX_NOTEBOOKLM_ASK_CHARS}) "
                "after trimming style and cold open."
            )
        prompt = render()
        print(f"  Trimmed story prompt to {len(prompt)} chars", flush=True)
    return prompt


def collect_scene_mapping(
    notebook_id: str,
    segments: list[str],
    blocks: list[SubtitleBlock],
    pipeline: dict[str, Any],
    *,
    source_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Map narration scenes to subtitle line ranges, batching to stay under NotebookLM limits."""
    batch_size = max(1, int(pipeline.get("scene_map_batch_size", 12)))
    all_mapping: list[dict[str, Any]] = []
    raw_parts: list[str] = []
    scene_id_start = 1
    total_batches = (len(segments) + batch_size - 1) // batch_size

    for batch_start in range(0, len(segments), batch_size):
        batch_segments = segments[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        scene_id_end = scene_id_start + len(batch_segments) - 1

        if total_batches > 1:
            print(
                f"  Scene map batch {batch_num}/{total_batches} "
                f"(scenes {scene_id_start}-{scene_id_end})...",
                flush=True,
            )

        map_prompt = build_scene_mapping_prompt(
            batch_segments,
            blocks,
            pipeline,
            scene_id_start=scene_id_start,
        )
        map_raw = ask(
            notebook_id,
            map_prompt,
            new=True,
            request_timeout=300,
            source_ids=source_ids,
        )
        raw_parts.append(map_raw)
        try:
            batch_mapping = parse_scene_mapping(map_raw, len(batch_segments))
        except ValueError:
            print("  Retrying scene map batch with stricter JSON prompt...", flush=True)
            retry = map_prompt + "\n\nReply with ONLY raw JSON. No markdown."
            map_raw = ask(
                notebook_id,
                retry,
                new=True,
                request_timeout=300,
                source_ids=source_ids,
            )
            raw_parts[-1] = map_raw
            batch_mapping = parse_scene_mapping(map_raw, len(batch_segments))

        for i, row in enumerate(batch_mapping):
            normalized = dict(row)
            normalized["scene_id"] = scene_id_start + i
            all_mapping.append(normalized)

        scene_id_start += len(batch_segments)

    return all_mapping, "\n\n---\n\n".join(raw_parts)


def parse_scene_mapping(raw: str, scene_count: int) -> list[dict[str, Any]]:
    blocks = extract_json_blocks(raw)
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("scenes"), list):
            scenes = block["scenes"]
            if len(scenes) >= scene_count:
                return scenes[:scene_count]
    raise ValueError("No valid scene mapping JSON in NotebookLM response")


def resolve_scene_clips(
    mapping: list[dict[str, Any]],
    segments: list[str],
    blocks: list[SubtitleBlock],
    pipeline: dict[str, Any],
) -> list[dict[str, Any]]:
    pad_start = float(pipeline.get("clip_pad_start_sec", 0.0))
    pad_end = float(pipeline.get("clip_pad_end_sec", 0.3))
    max_dur = float(pipeline.get("max_clip_source_sec", 8.0))
    out: list[dict[str, Any]] = []

    for i, row in enumerate(mapping):
        sid = int(row.get("scene_id", i + 1))
        start_line = int(row["subtitle_start"])
        end_line = int(row["subtitle_end"])
        norm_start, norm_end = normalize_subtitle_range(blocks, start_line, end_line)
        if (norm_start, norm_end) != (start_line, end_line):
            print(
                f"  WARN scene {sid}: clamped subtitle {start_line}-{end_line} -> {norm_start}-{norm_end}",
                flush=True,
            )
        start_line, end_line = norm_start, norm_end
        start_sec, end_sec = resolve_line_range(
            blocks, start_line, end_line,
            pad_start=pad_start, pad_end=pad_end, max_duration=max_dur,
        )
        text = segments[i] if i < len(segments) else ""
        out.append({
            "scene_id": sid,
            "narration": text,
            "subtitle_start": start_line,
            "subtitle_end": end_line,
            "start": start_sec,
            "end": end_sec,
            "start_ffmpeg": _sec_to_ffmpeg(start_sec),
            "end_ffmpeg": _sec_to_ffmpeg(end_sec),
            "music_mood": row.get("music_mood"),
        })
    return out


def _load_seed_config() -> dict[str, Any]:
    path = CONFIG / "seed_channels.json"
    if not path.exists():
        return {}
    return load_json(path)


def _collect_style_source_urls() -> tuple[list[str], list[str], list[str]]:
    """Return (channel_urls, video_urls, music_urls)."""
    data = _load_seed_config()
    channels: list[str] = []
    for ch in data.get("channels", []):
        u = str(ch.get("url", "")).strip()
        if u and "REPLACE" not in u:
            channels.append(u)
    videos: list[str] = []
    for item in data.get("sample_videos", []):
        if isinstance(item, dict):
            u = str(item.get("url", "")).strip()
        else:
            u = str(item).strip()
        if u and "REPLACE" not in u:
            videos.append(u)
    music: list[str] = []
    for item in data.get("music_references", []):
        u = str(item.get("url", "")).strip()
        if u and "REPLACE" not in u:
            music.append(u)
    return (
        list(dict.fromkeys(channels)),
        list(dict.fromkeys(videos)),
        list(dict.fromkeys(music)),
    )


def _collect_seed_urls() -> list[str]:
    ch, vid, mus = _collect_style_source_urls()
    return list(dict.fromkeys(ch + vid + mus))


def _default_style_notes() -> str:
    playbook = CONFIG / "channel_playbook.md"
    if playbook.exists():
        return playbook.read_text(encoding="utf-8")[:8000]
    return (
        "- Hook in first 10s with concrete example + promise\n"
        "- Fast teacher narrator; 170–185 WPM glossary style\n"
        "- Thumbnail: dark bg, topic name, EXPLAINED chip, time badge\n"
        "- Subtle lo-fi bed under voice (~8% volume)\n"
        "- SEO title: Every X Explained in Y Minutes"
    )


def _ingest_style_sources(notebook_id: str, pipeline: dict[str, Any]) -> str:
    if not pipeline.get("ingest_style_channels", True):
        return _default_style_notes()

    if not pipeline.get("ingest_youtube_style_sources", False):
        print("  Style from channel_playbook.md (YouTube refs disabled for CI reliability)", flush=True)
        return _default_style_notes()

    channels, videos, music_urls = _collect_style_source_urls()
    all_urls = list(dict.fromkeys(channels + videos + music_urls))
    if not all_urls:
        print("  No seed channels configured — using default style brief", flush=True)
        return _default_style_notes()

    source_ids: list[str] = []
    delay = float(pipeline.get("source_add_delay_sec", 5))
    timeout = int(pipeline.get("source_request_timeout", 180))
    max_sources = int(pipeline.get("max_style_sources", 12))
    reconcile_timeout = float(pipeline.get("source_reconcile_timeout", 90))

    for i, url in enumerate(all_urls[:max_sources]):
        if i:
            time.sleep(delay)
        label = "channel" if url in channels else ("music" if url in music_urls else "video")
        print(f"  Adding style source ({label}) {i + 1}/{min(len(all_urls), max_sources)}...", flush=True)
        try:
            added = notebooklm_source_add(
                notebook_id,
                url,
                request_timeout=timeout,
                reconcile_timeout=reconcile_timeout,
            )
            source_ids.append(extract_source_id(added))
        except RuntimeError as exc:
            print(f"  WARN: skipped style source ({label}): {exc}", flush=True)

    if not source_ids:
        print("  No style sources landed — falling back to channel_playbook.md", flush=True)
        return _default_style_notes()

    if source_ids:
        wait_sources(
            notebook_id,
            source_ids,
            timeout=int(pipeline.get("style_source_wait_timeout", pipeline.get("source_wait_timeout", 1200))),
        )

    notes_parts: list[str] = []

    print("[Style] Master brief (channels + subtitles)...", flush=True)
    master = ask(notebook_id, load_prompt("style_analysis.txt"), new=True, request_timeout=300)
    if master.strip():
        notes_parts.append("## Master style brief\n" + master.strip())

    for idx, url in enumerate(videos[:6], start=1):
        print(f"[Style] Per-video analysis {idx}/{len(videos[:6])}...", flush=True)
        vprompt = load_prompt("video_style_analysis.txt").replace("{video_url}", url)
        chunk = ask(notebook_id, vprompt, new=True, request_timeout=240)
        if chunk.strip():
            notes_parts.append(f"## Video {idx}\n{url}\n{chunk.strip()}")
        time.sleep(8)

    if music_urls:
        print("[Style] Music reference analysis...", flush=True)
        mus = ask(notebook_id, load_prompt("music_style_analysis.txt"), new=True, request_timeout=180)
        if mus.strip():
            notes_parts.append("## Music bed reference\n" + mus.strip())

    notes = "\n\n".join(notes_parts).strip() or _default_style_notes()
    return notes[:12000]


def _sec_to_ffmpeg(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1: teaching explainer script + visual map")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--pipeline", type=Path, default=CONFIG / "pipeline.json")
    parser.add_argument("--topic-slug", default=None, help="Override queue pick")
    parser.add_argument("--movie-slug", default=None, help="Legacy alias for --topic-slug")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    topic_slug_arg = args.topic_slug or args.movie_slug

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id()
    pipeline = load_json(args.pipeline) if args.pipeline.exists() else {}
    niche = load_json(CONFIG / "niche.json") if (CONFIG / "niche.json").exists() else {}
    duration = int(pipeline.get("duration_minutes", 14))
    wpm = int(pipeline.get("words_per_minute", 175))
    continue_word = pipeline.get("continue_keyword", "Next")
    render_mode = pipeline.get("render_mode", niche.get("render_mode", "slides"))
    target_words = duration * wpm
    history = load_topic_history()
    thumbnail_meta = None

    if args.dry_run:
        topic_slug = "http-status-codes"
        topic = "Every HTTP Status Code Explained in 14 Minutes"
        script = (
            "HTTP 404. This is the status code you see when a page doesn't exist. "
            "It means the server understood your request, but the resource simply isn't there."
        )
        segments = split_script_for_scenes(clean_script_for_tts(script), 2)
        mapping = [
            {
                "scene_id": 1,
                "visual_title": "HTTP 404",
                "visual_bullets": ["Page not found", "Client error"],
                "visual_type": "concept_card",
                "diagram_type": "http_error_client",
                "diagram_prompt": "Client requests a missing page; server returns 404",
                "diagram_labels": ["GET /missing-page", "404 Not Found"],
                "accent_color": "#EF4444",
                "music_mood": "calm",
            },
            {
                "scene_id": 2,
                "visual_title": "Status Codes",
                "visual_bullets": ["Server response", "3-digit number"],
                "visual_type": "concept_card",
                "diagram_type": "http_request",
                "diagram_prompt": "Browser sends HTTP request; server responds with status code",
                "diagram_labels": ["HTTP Request", "Status Code Response"],
                "accent_color": "#3B82F6",
                "music_mood": "focus",
            },
        ]
        scene_clips = resolve_scene_visuals(mapping, segments, pipeline)
        seo = fallback_seo(topic)
        style_notes = _default_style_notes()
        hook_pkg = {
            "title": topic,
            "cold_open": script[:400],
            "thumbnail_text": "HTTP CODES",
            "overlay_subtitle": "EXPLAINED",
            "icon_emoji": "🌐",
        }
        locked_title = hook_pkg["title"]
        story_parts = 1
        notebook_id = ""
    else:
        if topic_slug_arg:
            queue = load_json(CONFIG / "topic_queue.json")
            entry = next((t for t in queue.get("topics", []) if t["slug"] == topic_slug_arg), None)
            if not entry:
                sys.exit(f"Unknown --topic-slug: {topic_slug_arg}")
            topic_slug = entry["slug"]
            topic = entry.get("topic") or entry.get("title", topic_slug)
            duration = int(entry.get("minutes", duration))
            target_words = duration * wpm
        else:
            entry = pick_topic_from_queue(history)
            topic_slug = entry["slug"]
            topic = entry.get("topic") or entry.get("title", topic_slug)
            duration = int(entry.get("minutes", duration))
            target_words = duration * wpm

        print(f"[Topic] {topic} (slug={topic_slug})", flush=True)

        created = notebooklm_json_with_retry(
            "create", f"{niche.get('name', 'Simply Explained')} {run_id}", "--use"
        )
        notebook_id = extract_notebook_id(created)

        style_notes = _ingest_style_sources(notebook_id, pipeline)
        (out / "style_notes.txt").write_text(style_notes, encoding="utf-8")
        playbook_source_id = _attach_playbook_source(notebook_id, pipeline)
        style_for_prompt = notebooklm_style_brief(
            style_notes, playbook_in_notebook=bool(playbook_source_id)
        )
        chat_source_ids = []
        if playbook_source_id:
            chat_source_ids.append(playbook_source_id)

        pre_chat_delay = float(pipeline.get("pre_chat_delay_sec", 15))
        if pre_chat_delay > 0:
            print(f"  Waiting {pre_chat_delay:.0f}s before NotebookLM chat...", flush=True)
            time.sleep(pre_chat_delay)

        topic_title = topic.split("—")[0].strip() if "—" in topic else topic
        hook_angle = entry.get("hook_angle", "")

        print("[Hook] Title + cold open + thumbnail package...", flush=True)
        hook_prompt = (
            load_prompt("story_hook_package.txt")
            .replace("{topic_title}", topic_title)
            .replace("{duration_minutes}", str(duration))
            .replace("{style_notes}", style_for_prompt)
        )
        if hook_angle:
            hook_prompt += f"\n\nSuggested hook angle: {hook_angle}"
        hook_raw = ask(
            notebook_id,
            hook_prompt,
            new=True,
            request_timeout=300,
            source_ids=chat_source_ids or None,
        )
        (out / "hook_package_raw.txt").write_text(hook_raw, encoding="utf-8")
        try:
            hook_pkg = parse_hook_package_json(hook_raw)
        except ValueError:
            hook_pkg = {
                "title": sanitize_seo_title(topic),
                "cold_open": "",
                "thumbnail_text": topic_title.split("(")[0].strip()[:20].upper(),
                "overlay_subtitle": "EXPLAINED",
                "icon_emoji": "📚",
            }
        locked_title = sanitize_seo_title(str(hook_pkg.get("title", topic)))
        cold_open = clean_script_for_tts(str(hook_pkg.get("cold_open", "")))
        save_json(out / "hook_package.json", {**hook_pkg, "title": locked_title, "cold_open": cold_open})
        print(f"  -> locked title: {locked_title}", flush=True)

        print("[Script] Multi-part explainer (hook-first)...", flush=True)
        story_prompt = build_story_generation_prompt(
            topic_title=topic_title,
            duration=duration,
            continue_word=continue_word,
            target_words=target_words,
            locked_title=locked_title,
            cold_open=cold_open,
            style_notes=style_for_prompt,
        )
        script, story_parts = collect_multipart_text(
            notebook_id,
            story_prompt,
            continue_word,
            new=True,
            source_ids=chat_source_ids or None,
        )
        script = clean_script_for_tts(script)
        word_count = len(script.split())
        print(f"  -> {word_count} words (target ~{target_words})", flush=True)

        scene_count = estimate_scene_count(script, pipeline)
        segments = split_script_for_scenes(script, scene_count)
        print(f"  -> {scene_count} narration scenes", flush=True)

        print("[Visual map] Slide specs per scene...", flush=True)
        mapping, map_raw = collect_visual_mapping(
            notebook_id,
            segments,
            pipeline,
            source_ids=chat_source_ids or None,
        )
        (out / "scene_mapping_raw.txt").write_text(map_raw, encoding="utf-8")

        scene_clips = resolve_scene_visuals(mapping, segments, pipeline)
        validate_scene_clips(scene_clips, render_mode=render_mode)
        diagram_types = [c.get("diagram_type", "?") for c in scene_clips[:5]]
        print(f"  -> {len(scene_clips)} slide scenes mapped (diagrams: {diagram_types}...)", flush=True)

        past_topics = format_topic_history_for_prompt(history)
        print("[SEO] YouTube metadata (locked title)...", flush=True)
        seo_prompt = (
            load_prompt("youtube_seo.txt")
            .replace("{topic}", topic)
            .replace("{locked_title}", locked_title)
            .replace("{past_topics}", past_topics)
            .replace("{style_notes}", style_for_prompt)
        )
        seo_raw = ask(notebook_id, seo_prompt, new=True, source_ids=chat_source_ids or None)
        try:
            seo = parse_seo_json(seo_raw)
        except ValueError:
            seo = fallback_seo(topic)
        seo["title"] = locked_title

        thumbnail_meta = None
        if pipeline.get("generate_thumbnail", True):
            from thumbnail_builder import parse_thumbnail_json

            thumb_prompt = (
                load_prompt("thumbnail.txt")
                .replace("{topic}", topic)
                .replace("{title}", locked_title)
                .replace("{thumbnail_text}", str(hook_pkg.get("thumbnail_text", "")))
                .replace("{icon_emoji}", str(hook_pkg.get("icon_emoji", "📚")))
                .replace("{style_notes}", style_for_prompt)
            )
            thumb_raw = ask(notebook_id, thumb_prompt, new=True, source_ids=chat_source_ids or None)
            (out / "thumbnail_raw.txt").write_text(thumb_raw, encoding="utf-8")
            try:
                thumb_spec = parse_thumbnail_json(thumb_raw)
            except ValueError:
                thumb_spec = {
                    "overlay_title": hook_pkg.get("thumbnail_text") or topic_title.split("(")[0].strip()[:20],
                    "overlay_subtitle": hook_pkg.get("overlay_subtitle") or "EXPLAINED",
                    "time_badge": f"{duration} MIN",
                    "icon_emoji": hook_pkg.get("icon_emoji", "📚"),
                }
            thumbnail_meta = {
                **thumb_spec,
                "topic": topic,
                "title": locked_title,
                "thumbnail_text": hook_pkg.get("thumbnail_text"),
                "bg_color": thumb_spec.get("bg_color", "#0f0f1a"),
                "time_badge": thumb_spec.get("time_badge", f"{duration} MIN"),
                "render_mode": render_mode,
            }
            print(f"  -> thumbnail spec: {thumbnail_meta.get('overlay_title')}", flush=True)

    scenes = clips_to_scenes(scene_clips)
    (out / "script.txt").write_text(script, encoding="utf-8")
    (out / "topics.txt").write_text(topic, encoding="utf-8")
    save_json(
        out / "scene_clips.json",
        {"topic_slug": topic_slug, "render_mode": render_mode, "scenes": scene_clips},
    )
    save_json(out / "scenes.json", scenes)
    save_json(
        out / "script_segments.json",
        [{"scene_id": c["scene_id"], "text": c.get("narration", "")} for c in scene_clips],
    )
    save_json(out / "youtube_seo.json", seo)
    if thumbnail_meta:
        save_json(out / "thumbnail.json", thumbnail_meta)

    if not args.dry_run:
        append_topic_history(
            CONFIG / "topic_history.json",
            run_id=run_id,
            topic=topic,
            title=str(seo.get("title", topic)),
        )

    meta: dict[str, Any] = {
        "run_id": run_id,
        "notebook_id": notebook_id,
        "niche": niche.get("name"),
        "topic_slug": topic_slug,
        "movie_slug": topic_slug,
        "render_mode": render_mode,
        "topic": topic,
        "duration_minutes": duration,
        "word_count": len(script.split()),
        "target_word_count": target_words,
        "scene_count": len(scene_clips),
        "title": seo.get("title"),
        "locked_title": locked_title if not args.dry_run else seo.get("title"),
    }
    if not args.dry_run:
        meta["story_parts"] = story_parts
    save_json(out / "metadata.json", meta)

    print(f"run_id={run_id}")
    print(f"topic_slug={topic_slug}")
    print(f"Done: script + {len(scene_clips)} slide scenes + SEO -> {out}")


if __name__ == "__main__":
    main()
