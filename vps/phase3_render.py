"""ffmpeg slide rendering + final explainer video assembly on VPS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow importing slide_builder from same package
sys.path.insert(0, str(Path(__file__).resolve().parent))
from slide_builder import render_slide, render_slide_frames  # noqa: E402
from diagram_renderer import infer_diagram_type  # noqa: E402
from html_slide import write_slide_html  # noqa: E402
from animation_presets import uses_semantic_animation  # noqa: E402
from semantic_slide import build_semantic_slide_html  # noqa: E402
from html_capture import HtmlSlideCaptureSession  # noqa: E402


FPS = 30
BG_COLOR = "0x000000"
FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "2")
X264_PRESET = os.environ.get("FFMPEG_PRESET", "ultrafast")
CLIP_EXTRACT_TIMEOUT_SEC = int(os.environ.get("CLIP_EXTRACT_TIMEOUT_SEC", "1200"))
FFMPEG_LONG_TIMEOUT_SEC = int(os.environ.get("FFMPEG_LONG_TIMEOUT_SEC", "7200"))


def _run(cmd: list[str], *, timeout: int | None = None) -> None:
    if cmd[:2] == ["ffmpeg", "-y"] and "-threads" not in cmd:
        cmd = ["ffmpeg", "-y", "-threads", FFMPEG_THREADS, *cmd[2:]]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout or CLIP_EXTRACT_TIMEOUT_SEC,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"Command failed: {' '.join(cmd)}")


def _expected_video_duration(
    dur_by_id: dict[int, float],
    *,
    end_dur: float = 0.0,
) -> float:
    return sum(dur_by_id.values()) + max(0.0, end_dur)


def _assert_duration(path: Path, expected: float, label: str, *, tolerance: float = 0.95) -> float:
    actual = _probe_duration(path)
    if expected > 0 and actual < expected * tolerance:
        raise RuntimeError(
            f"{label} duration {actual:.1f}s is much shorter than expected {expected:.1f}s"
        )
    return actual


def _concat_video_segments(list_file: Path, dest: Path) -> None:
    """Re-encode concat so MP4 segment timestamps cannot truncate the output."""
    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-an", "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
        str(dest),
    ], timeout=FFMPEG_LONG_TIMEOUT_SEC)


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return max(0.5, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def _sec_to_ffmpeg(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _write_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def extract_clip(
    movie: Path,
    start_sec: float,
    end_sec: float,
    dest: Path,
    *,
    output_duration: float,
    fps: int = FPS,
) -> None:
    """Extract muted subclip; extend/trim to match narration duration."""
    source_dur = max(0.5, end_sec - start_sec)
    vf = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={BG_COLOR},"
        f"fps={fps}"
    )
    start = _sec_to_ffmpeg(start_sec)
    end = _sec_to_ffmpeg(end_sec)

    encode_tail = [
        "-an",
        "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
        "-video_track_timescale", "30000",
        "-t", str(output_duration),
        str(dest),
    ]
    if source_dur >= output_duration:
        _run([
            "ffmpeg", "-y",
            "-ss", start, "-to", end,
            "-i", str(movie),
            "-vf", vf,
            *encode_tail,
        ])
        return

    # Source shorter than narration — encode scaled segment, then loop via stream copy.
    seg = dest.with_suffix(".seg.mp4")
    try:
        _run([
            "ffmpeg", "-y",
            "-ss", start,
            "-i", str(movie),
            "-t", str(source_dur),
            "-an", "-vf", vf,
            "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(seg),
        ])
        _run([
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(seg),
            "-an",
            "-t", str(output_duration),
            "-c", "copy",
            str(dest),
        ])
    finally:
        seg.unlink(missing_ok=True)


def extract_thumbnail(movie: Path, at_sec: float, dest: Path) -> None:
    _run([
        "ffmpeg", "-y",
        "-ss", _sec_to_ffmpeg(at_sec),
        "-i", str(movie),
        "-frames:v", "1",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease",
        str(dest),
    ])


def _load_bg_music_config(inputs: Path) -> dict[str, Any]:
    for name in ("pipeline.json", "bg_music.json"):
        p = inputs / name
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if "bg_music" in data:
                return data["bg_music"]
            return data
    return {}


def _resolve_bg_track(cfg: dict[str, Any], inputs: Path) -> Path | None:
    if not cfg.get("enabled", False):
        return None
    track = str(cfg.get("track", "")).strip()
    candidates = [
        inputs / "bg_music.mp3",
        inputs / Path(track).name if track else Path(),
    ]
    app_root = Path(os.environ.get("APP_ROOT", "/opt/retro-movies"))
    if track:
        candidates.append(app_root / track)
        if not track.startswith("/"):
            candidates.append(app_root / "config" / Path(track).name)
    for c in candidates:
        try:
            if c.exists() and c.stat().st_size > 1000:
                return c
        except OSError:
            continue
    return None


def _mix_bg_music(
    voice_mp3: Path,
    inputs: Path,
    work: Path,
    duration: float,
    scene_durations: list[dict[str, Any]] | None = None,
) -> Path:
    cfg = _load_bg_music_config(inputs)
    track = _resolve_bg_track(cfg, inputs)
    if not track:
        return voice_mp3

    base_volume = float(cfg.get("volume", 0.12))
    fade_in = float(cfg.get("fade_in_sec", 2.0))
    fade_out = float(cfg.get("fade_out_sec", 3.0))
    crossfade = float(cfg.get("scene_crossfade_sec", 0.5))
    dynamic = bool(cfg.get("scene_dynamic_volume", True))
    duck = bool(cfg.get("duck_under_voice", False))
    duck_amount = float(cfg.get("duck_amount", 0.65))
    out = work / "mixed_audio.mp3"

    if dynamic and scene_durations and len(scene_durations) > 1:
        bg_track = _build_scene_dynamic_bg(track, scene_durations, work, crossfade=crossfade)
    else:
        bg_track = _build_flat_bg(track, duration, base_volume, fade_in, fade_out, work)

    if duck:
        # Sidechain-style: voice-forward mix; bg stays under narration
        _run([
            "ffmpeg", "-y",
            "-i", str(voice_mp3),
            "-i", str(bg_track),
            "-filter_complex",
            (
                f"[1:a]volume={duck_amount}[bgduck];"
                f"[0:a][bgduck]amix=inputs=2:duration=first:weights=1 0.85:dropout_transition=2[aout]"
            ),
            "-map", "[aout]", "-t", str(duration),
            "-c:a", "libmp3lame", "-q:a", "4", str(out),
        ])
    else:
        _run([
            "ffmpeg", "-y",
            "-i", str(voice_mp3),
            "-i", str(bg_track),
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "[aout]", "-t", str(duration),
            "-c:a", "libmp3lame", "-q:a", "4", str(out),
        ])
    return out


def _build_flat_bg(
    track: Path, duration: float, volume: float, fade_in: float, fade_out: float, work: Path,
) -> Path:
    out = work / "bg_flat.mp3"
    fade_out_start = max(0.0, duration - fade_out)
    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(track),
        "-af",
        f"volume={volume},afade=t=in:st=0:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-q:a", "4", str(out),
    ])
    return out


def _build_scene_dynamic_bg(
    track: Path,
    scene_durations: list[dict[str, Any]],
    work: Path,
    *,
    crossfade: float = 0.5,
) -> Path:
    """Build bg bed with per-scene volume + crossfades between moods."""
    segments: list[Path] = []
    for i, scene in enumerate(scene_durations):
        dur = max(0.5, float(scene.get("duration_sec", 5.0)))
        vol = float(scene.get("music_volume", 0.12))
        seg = work / f"bg_seg_{i:02d}.mp3"
        # Offset into track so loops don't sound identical every scene
        seek = (i * 17.5) % 120.0
        _run([
            "ffmpeg", "-y",
            "-ss", _sec_to_ffmpeg(seek),
            "-stream_loop", "-1", "-i", str(track),
            "-t", str(dur),
            "-af", f"volume={vol}",
            "-c:a", "libmp3lame", "-q:a", "4", str(seg),
        ])
        segments.append(seg)

    if len(segments) == 1:
        return segments[0]

    # Chain acrossfade for smooth volume/mood transitions
    out = work / "bg_dynamic.mp3"
    d = min(crossfade, 0.8)
    if len(segments) == 2:
        _run([
            "ffmpeg", "-y",
            "-i", str(segments[0]), "-i", str(segments[1]),
            "-filter_complex", f"[0][1]acrossfade=d={d}:c1=tri:c2=tri[aout]",
            "-map", "[aout]", "-c:a", "libmp3lame", "-q:a", "4", str(out),
        ])
        return out

    # Build filter graph for N segments
    inputs: list[str] = []
    for seg in segments:
        inputs.extend(["-i", str(seg)])
    n = len(segments)
    fc_parts: list[str] = [f"[0][1]acrossfade=d={d}:c1=tri:c2=tri[cf1]"]
    for j in range(2, n):
        prev = f"cf{j - 1}"
        nxt = f"cf{j}" if j < n - 1 else "aout"
        fc_parts.append(f"[{prev}][{j}]acrossfade=d={d}:c1=tri:c2=tri[{nxt}]")
    _run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(fc_parts),
        "-map", "[aout]", "-c:a", "libmp3lame", "-q:a", "4", str(out),
    ])
    return out


def _slide_to_video(slide: Path, duration: float, dest: Path, *, fps: int = FPS) -> None:
    """Convert a static slide PNG to a silent video segment matching narration duration."""
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(slide),
        "-t", str(duration),
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={BG_COLOR},fps={fps}",
        "-an",
        "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
        str(dest),
    ])


def _animated_slide_to_video(
    scene: dict[str, Any],
    duration: float,
    dest: Path,
    work: Path,
    *,
    fps: int = FPS,
    bg_color: str = "#0f0f1a",
    channel_name: str = "Byte Glossary",
    min_frames: int = 24,
) -> None:
    """Render progressive diagram reveal frames, then encode to video."""
    sid = int(scene.get("scene_id", 0))
    frames_dir = work / f"frames_{sid:02d}"
    n_frames = max(min_frames, int(duration * fps))
    render_slide_frames(
        scene,
        frames_dir,
        n_frames=n_frames,
        bg_color=bg_color,
        channel_name=channel_name,
    )
    _run([
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-t", str(duration),
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={BG_COLOR},fps={fps}",
        "-an",
        "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
        str(dest),
    ])


def _run_html_slide_render_sync(
    run_id: str,
    *,
    runs_dir: Path,
) -> None:
    """Render teaching video via HTML/CSS + Playwright frame capture at 1080p."""
    run_path = runs_dir / run_id
    state_path = run_path / "state.json"
    inputs = run_path / "inputs"
    work = run_path / "work"
    out_dir = run_path / "output"
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "running"
    state["phase"] = "html_slides"
    state["render_engine"] = "html"
    _write_state(state_path, state)

    meta = json.loads((inputs / "metadata.json").read_text(encoding="utf-8"))
    pipeline_path = inputs / "pipeline.json"
    pipeline: dict[str, Any] = {}
    if pipeline_path.exists():
        pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))

    scene_clips = json.loads((inputs / "scene_clips.json").read_text(encoding="utf-8"))
    scenes = scene_clips.get("scenes", scene_clips if isinstance(scene_clips, list) else [])
    durations = json.loads((inputs / "scene_durations.json").read_text(encoding="utf-8"))
    dur_by_id = {int(d["scene_id"]): float(d["duration_sec"]) for d in durations}

    bg_color = pipeline.get("slide_bg_color", "#0f0f1a")
    channel_name = meta.get("niche", "Simply Explained")
    slide_width = int(pipeline.get("slide_width", 1920))
    slide_height = int(pipeline.get("slide_height", 1080))
    capture_fps = int(pipeline.get("slide_capture_fps", os.environ.get("STUDY_CAPTURE_FPS", "24")))

    clip_paths: list[Path] = []
    total = len(scenes)
    state["total_scenes"] = total

    with HtmlSlideCaptureSession(
        width=slide_width,
        height=slide_height,
        fps=capture_fps,
        work_dir=work / "html_capture",
    ) as session:
        for i, scene in enumerate(scenes):
            sid = int(scene["scene_id"])
            narr_dur = dur_by_id.get(sid, 5.0)
            clip_path = work / f"clip_{sid:02d}.mp4"
            html_path = work / f"scene_{sid:02d}.html"

            if clip_path.exists():
                try:
                    _assert_duration(clip_path, narr_dur, f"html clip {sid}")
                    clip_paths.append(clip_path)
                    continue
                except RuntimeError:
                    clip_path.unlink(missing_ok=True)

            state["current_scene"] = sid
            state["clips_ready"] = len(clip_paths)
            state["current_diagram"] = scene.get("diagram_type") or infer_diagram_type(scene)
            _write_state(state_path, state)

            use_semantic = uses_semantic_animation(scene)
            if use_semantic:
                html_path.write_text(
                    build_semantic_slide_html(
                        scene,
                        bg_color=bg_color,
                        channel_name=channel_name,
                        duration_sec=narr_dur,
                    ),
                    encoding="utf-8",
                )
            else:
                write_slide_html(scene, html_path, bg_color=bg_color, channel_name=channel_name)
            session.capture_scene(html_path, narr_dur, clip_path, semantic=use_semantic)
            _assert_duration(clip_path, narr_dur, f"html clip {sid}")
            clip_paths.append(clip_path)
            state["clips_ready"] = len(clip_paths)
            state["completed"] = [int(s["scene_id"]) for s in scenes[: i + 1]]
            _write_state(state_path, state)

    _finalize_slide_video(run_id, runs_dir=runs_dir, scenes=scenes, clip_paths=clip_paths, dur_by_id=dur_by_id, state=state, state_path=state_path)


def _finalize_slide_video(
    run_id: str,
    *,
    runs_dir: Path,
    scenes: list[dict[str, Any]],
    clip_paths: list[Path],
    dur_by_id: dict[int, float],
    state: dict[str, Any],
    state_path: Path,
) -> None:
    """Concat slide clips, mix audio, mux final video (shared by PIL and Xvfb paths)."""
    run_path = runs_dir / run_id
    inputs = run_path / "inputs"
    work = run_path / "work"
    out_dir = run_path / "output"

    state["phase"] = "concat"
    _write_state(state_path, state)

    list_file = work / "concat.txt"
    with list_file.open("w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    video_only = work / "video_only.mp4"
    expected_video = _expected_video_duration(dur_by_id)
    if not (video_only.exists() and _probe_duration(video_only) >= expected_video * 0.95):
        video_only.unlink(missing_ok=True)
        _concat_video_segments(list_file, video_only)
    _assert_duration(video_only, expected_video, "slide concat")

    narration = inputs / "narration.mp3"
    end_audio = inputs / "end_card.mp3"
    audio_paths = [narration]
    end_dur = 0.0
    if end_audio.exists():
        end_meta_path = inputs / "end_card.json"
        if end_meta_path.exists():
            end_meta = json.loads(end_meta_path.read_text(encoding="utf-8"))
            if end_meta.get("enabled", True):
                end_dur = float(end_meta.get("duration_sec", _probe_duration(end_audio)))
                end_clip = work / "end_card.mp4"
                _run([
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"color=c={BG_COLOR}:s=1920x1080:d={end_dur}",
                    "-pix_fmt", "yuv420p", str(end_clip),
                ])
                with (work / "concat_end.txt").open("w", encoding="utf-8") as f:
                    f.write(f"file '{video_only.resolve().as_posix()}'\n")
                    f.write(f"file '{end_clip.resolve().as_posix()}'\n")
                combined = work / "video_with_end.mp4"
                _concat_video_segments(work / "concat_end.txt", combined)
                video_only = combined
                audio_paths.append(end_audio)

    if len(audio_paths) == 1:
        voice_audio = narration
    else:
        full_audio = work / "full_narration.mp3"
        with (work / "audio_concat.txt").open("w", encoding="utf-8") as f:
            for p in audio_paths:
                f.write(f"file '{p.resolve().as_posix()}'\n")
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(work / "audio_concat.txt"), "-c", "copy", str(full_audio),
        ])
        voice_audio = full_audio

    durations = json.loads((inputs / "scene_durations.json").read_text(encoding="utf-8"))
    video_dur = _probe_duration(video_only)
    audio_in = str(_mix_bg_music(voice_audio, inputs, work, video_dur, scene_durations=durations))

    state["phase"] = "mux"
    _write_state(state_path, state)

    final = out_dir / "final_video.mp4"
    expected_final = _probe_duration(voice_audio)
    _run([
        "ffmpeg", "-y", "-i", str(video_only), "-i", audio_in,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", X264_PRESET, "-c:a", "aac", "-pix_fmt", "yuv420p",
        str(final),
    ], timeout=FFMPEG_LONG_TIMEOUT_SEC)
    _assert_duration(final, expected_final, "final mux")

    thumb_path = out_dir / "thumbnail.png"
    uploaded_thumb = inputs / "thumbnail.png"
    if uploaded_thumb.exists() and uploaded_thumb.stat().st_size > 5000:
        thumb_path.write_bytes(uploaded_thumb.read_bytes())
    elif scenes:
        first_slide = work / "slide_01.png"
        if first_slide.exists():
            thumb_path.write_bytes(first_slide.read_bytes())

    state["status"] = "complete"
    state["phase"] = "done"
    state["clips_ready"] = len(scenes)
    state["error"] = None
    _write_state(state_path, state)


def _run_slide_render_sync(
    run_id: str,
    *,
    runs_dir: Path,
) -> None:
    """Render teaching video via HTML/CSS frame capture (no PIL fallback)."""
    run_path = runs_dir / run_id
    inputs = run_path / "inputs"
    pipeline_path = inputs / "pipeline.json"
    pipeline: dict[str, Any] = {}
    if pipeline_path.exists():
        pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))

    render_engine = str(pipeline.get("render_engine", "html")).lower()
    if render_engine in ("html", "xvfb"):
        _run_html_slide_render_sync(run_id, runs_dir=runs_dir)
        return
    if render_engine == "pil":
        raise RuntimeError("PIL render engine is disabled; use render_engine=html")
    raise RuntimeError(f"Unsupported render_engine={render_engine!r}")


def _run_pil_slide_render_sync(
    run_id: str,
    *,
    runs_dir: Path,
) -> None:
    """Render teaching video from PIL slide frames (legacy/fallback engine)."""
    run_path = runs_dir / run_id
    state_path = run_path / "state.json"
    inputs = run_path / "inputs"
    work = run_path / "work"
    out_dir = run_path / "output"
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "running"
    state["phase"] = "slides"
    state["render_engine"] = "pil"
    _write_state(state_path, state)

    meta = json.loads((inputs / "metadata.json").read_text(encoding="utf-8"))
    pipeline_path = inputs / "pipeline.json"
    pipeline: dict[str, Any] = {}
    if pipeline_path.exists():
        pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))

    scene_clips = json.loads((inputs / "scene_clips.json").read_text(encoding="utf-8"))
    scenes = scene_clips.get("scenes", scene_clips if isinstance(scene_clips, list) else [])
    durations = json.loads((inputs / "scene_durations.json").read_text(encoding="utf-8"))
    dur_by_id = {int(d["scene_id"]): float(d["duration_sec"]) for d in durations}

    bg_color = pipeline.get("slide_bg_color", "#0f0f1a")
    channel_name = meta.get("niche", "Simply Explained")
    slide_animation = bool(pipeline.get("slide_animation", True))
    animation_min_frames = int(pipeline.get("slide_animation_min_frames", 24))

    clip_paths: list[Path] = []
    state["total_scenes"] = len(scenes)

    for i, scene in enumerate(scenes):
        sid = int(scene["scene_id"])
        narr_dur = dur_by_id.get(sid, 5.0)
        clip_path = work / f"clip_{sid:02d}.mp4"
        slide_path = work / f"slide_{sid:02d}.png"

        if not slide_path.exists():
            render_slide(scene, slide_path, bg_color=bg_color, channel_name=channel_name)

        if clip_path.exists():
            try:
                _assert_duration(clip_path, narr_dur, f"slide clip {sid}")
                clip_paths.append(clip_path)
                continue
            except RuntimeError:
                clip_path.unlink(missing_ok=True)

        state["current_scene"] = sid
        state["clips_ready"] = len(clip_paths)
        state["current_diagram"] = scene.get("diagram_type") or infer_diagram_type(scene)
        _write_state(state_path, state)

        if slide_animation:
            _animated_slide_to_video(
                scene,
                narr_dur,
                clip_path,
                work,
                bg_color=bg_color,
                channel_name=channel_name,
                min_frames=animation_min_frames,
            )
        else:
            _slide_to_video(slide_path, narr_dur, clip_path)
        _assert_duration(clip_path, narr_dur, f"slide clip {sid}")
        clip_paths.append(clip_path)
        state["clips_ready"] = len(clip_paths)
        state["completed"] = [int(s["scene_id"]) for s in scenes[: i + 1]]
        _write_state(state_path, state)

    _finalize_slide_video(
        run_id,
        runs_dir=runs_dir,
        scenes=scenes,
        clip_paths=clip_paths,
        dur_by_id=dur_by_id,
        state=state,
        state_path=state_path,
    )


async def run_render_async(
    run_id: str,
    *,
    runs_dir: Path,
    movies_dir: Path,
) -> None:
    import asyncio

    await asyncio.to_thread(_run_render_sync, run_id, runs_dir=runs_dir, movies_dir=movies_dir)


def _run_render_sync(
    run_id: str,
    *,
    runs_dir: Path,
    movies_dir: Path,
) -> None:
    inputs = runs_dir / run_id / "inputs"
    meta_path = inputs / "metadata.json"
    render_mode = "slides"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        render_mode = meta.get("render_mode", "slides")
        clips_path = inputs / "scene_clips.json"
        if clips_path.exists():
            clips_data = json.loads(clips_path.read_text(encoding="utf-8"))
            render_mode = clips_data.get("render_mode", render_mode)

    if render_mode == "slides":
        _run_slide_render_sync(run_id, runs_dir=runs_dir)
        return

    _run_film_clip_render_sync(run_id, runs_dir=runs_dir, movies_dir=movies_dir)


def _run_film_clip_render_sync(
    run_id: str,
    *,
    runs_dir: Path,
    movies_dir: Path,
) -> None:
    run_path = runs_dir / run_id
    state_path = run_path / "state.json"
    inputs = run_path / "inputs"
    work = run_path / "work"
    out_dir = run_path / "output"
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "running"
    state["phase"] = "clips"
    _write_state(state_path, state)

    meta = json.loads((inputs / "metadata.json").read_text(encoding="utf-8"))
    movie_slug = meta["movie_slug"]
    movie = movies_dir / movie_slug / "movie.mp4"
    if not movie.exists():
        raise FileNotFoundError(f"Movie not found: {movie}")

    scene_clips = json.loads((inputs / "scene_clips.json").read_text(encoding="utf-8"))
    scenes = scene_clips.get("scenes", scene_clips if isinstance(scene_clips, list) else [])
    durations = json.loads((inputs / "scene_durations.json").read_text(encoding="utf-8"))
    dur_by_id = {int(d["scene_id"]): float(d["duration_sec"]) for d in durations}

    clip_paths: list[Path] = []
    total = len(scenes)
    state["total_scenes"] = total

    for i, scene in enumerate(scenes):
        sid = int(scene["scene_id"])
        narr_dur = dur_by_id.get(sid, 5.0)
        clip_path = work / f"clip_{sid:02d}.mp4"

        if clip_path.exists():
            try:
                _assert_duration(clip_path, narr_dur, f"clip {sid}")
                clip_paths.append(clip_path)
                state["current_scene"] = sid
                state["clips_ready"] = len(clip_paths)
                state["completed"] = [int(s["scene_id"]) for s in scenes[: i + 1]]
                _write_state(state_path, state)
                continue
            except RuntimeError:
                clip_path.unlink(missing_ok=True)

        state["current_scene"] = sid
        state["clips_ready"] = len(clip_paths)
        _write_state(state_path, state)

        start = float(scene["start"])
        end = float(scene["end"])
        extract_clip(movie, start, end, clip_path, output_duration=narr_dur)
        _assert_duration(clip_path, narr_dur, f"clip {sid}")
        clip_paths.append(clip_path)
        state["clips_ready"] = len(clip_paths)
        state["completed"] = [int(s["scene_id"]) for s in scenes[: i + 1]]
        _write_state(state_path, state)

    state["phase"] = "concat"
    _write_state(state_path, state)

    list_file = work / "concat.txt"
    with list_file.open("w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    video_only = work / "video_only.mp4"
    expected_video = _expected_video_duration(dur_by_id)
    if not (video_only.exists() and _probe_duration(video_only) >= expected_video * 0.95):
        video_only.unlink(missing_ok=True)
        _concat_video_segments(list_file, video_only)
    _assert_duration(video_only, expected_video, "clip concat")

    narration = inputs / "narration.mp3"
    end_audio = inputs / "end_card.mp3"
    audio_paths = [narration]
    end_dur = 0.0
    if end_audio.exists():
        end_meta_path = inputs / "end_card.json"
        if end_meta_path.exists():
            end_meta = json.loads(end_meta_path.read_text(encoding="utf-8"))
            if end_meta.get("enabled", True):
                end_dur = float(end_meta.get("duration_sec", _probe_duration(end_audio)))
                end_clip = work / "end_card.mp4"
                _run([
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"color=c={BG_COLOR}:s=1920x1080:d={end_dur}",
                    "-pix_fmt", "yuv420p", str(end_clip),
                ])
                with (work / "concat_end.txt").open("w", encoding="utf-8") as f:
                    f.write(f"file '{video_only.resolve().as_posix()}'\n")
                    f.write(f"file '{end_clip.resolve().as_posix()}'\n")
                combined = work / "video_with_end.mp4"
                _concat_video_segments(work / "concat_end.txt", combined)
                video_only = combined
                audio_paths.append(end_audio)
                _assert_duration(
                    video_only,
                    _expected_video_duration(dur_by_id, end_dur=end_dur),
                    "video with end card",
                )

    if len(audio_paths) == 1:
        voice_audio = narration
    else:
        full_audio = work / "full_narration.mp3"
        with (work / "audio_concat.txt").open("w", encoding="utf-8") as f:
            for p in audio_paths:
                f.write(f"file '{p.resolve().as_posix()}'\n")
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(work / "audio_concat.txt"), "-c", "copy", str(full_audio),
        ])
        voice_audio = full_audio

    video_dur = _probe_duration(video_only)
    audio_in = str(_mix_bg_music(voice_audio, inputs, work, video_dur, scene_durations=durations))

    state["phase"] = "mux"
    _write_state(state_path, state)

    final = out_dir / "final_video.mp4"
    expected_final = _probe_duration(voice_audio)
    _run([
        "ffmpeg", "-y", "-i", str(video_only), "-i", audio_in,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", X264_PRESET, "-c:a", "aac", "-pix_fmt", "yuv420p",
        str(final),
    ], timeout=FFMPEG_LONG_TIMEOUT_SEC)
    _assert_duration(final, expected_final, "final mux")

    thumb_path = out_dir / "thumbnail.png"
    uploaded_thumb = inputs / "thumbnail.png"
    if uploaded_thumb.exists() and uploaded_thumb.stat().st_size > 5000:
        thumb_path.write_bytes(uploaded_thumb.read_bytes())
    else:
        hook_scene = scenes[0] if scenes else {"start": 60.0}
        extract_thumbnail(movie, float(hook_scene.get("start", 60.0)), thumb_path)

    state["status"] = "complete"
    state["phase"] = "done"
    state["clips_ready"] = total
    state["error"] = None
    _write_state(state_path, state)


def main() -> None:
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m phase3_render <run_id>", file=sys.stderr)
        raise SystemExit(2)
    run_id = sys.argv[1]
    runs_dir = Path(os.environ.get("RUNS_DIR", "./runs")).resolve()
    movies_dir = Path(os.environ.get("MOVIES_DIR", "/opt/movies")).resolve()
    state_path = runs_dir / run_id / "state.json"
    try:
        _run_render_sync(run_id, runs_dir=runs_dir, movies_dir=movies_dir)
    except Exception as exc:  # noqa: BLE001
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {"run_id": run_id}
        state["status"] = "failed"
        state["error"] = str(exc)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_state(state_path, state)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
