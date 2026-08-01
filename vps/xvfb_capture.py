"""Isolated Xvfb + Chrome + ffmpeg x11grab capture for study renders.

Uses a dedicated display (default :100) — NEVER touches TigerVNC on :99
or any other system display.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

# TigerVNC and other services use :99 — do not use or modify that display.
FORBIDDEN_DISPLAYS = frozenset({99})
DEFAULT_DISPLAY = int(os.environ.get("STUDY_XVFB_DISPLAY", "100"))
DEFAULT_WIDTH = int(os.environ.get("STUDY_XVFB_WIDTH", "1920"))
DEFAULT_HEIGHT = int(os.environ.get("STUDY_XVFB_HEIGHT", "1080"))
MIN_FREE_RAM_MB = int(os.environ.get("STUDY_MIN_FREE_RAM_MB", "350"))
CHROME_BIN = os.environ.get("STUDY_CHROME_BIN", "google-chrome")
FPS = int(os.environ.get("STUDY_CAPTURE_FPS", "30"))
FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "2")
X264_PRESET = os.environ.get("FFMPEG_PRESET", "ultrafast")

_MARKER_ROOT = Path(os.environ.get("RUNS_DIR", "/opt/retro-movies/runs")) / ".study-render"


def _run(cmd: list[str], *, env: dict[str, str] | None = None, timeout: int | None = None) -> None:
    if cmd[:2] == ["ffmpeg", "-y"] and "-threads" not in cmd:
        cmd = ["ffmpeg", "-y", "-threads", FFMPEG_THREADS, *cmd[2:]]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"Command failed: {' '.join(cmd)}")


def _check_ram() -> None:
    try:
        avail_kb = int(Path("/proc/meminfo").read_text().split("MemAvailable:")[1].split()[0])
    except (IndexError, ValueError, OSError) as exc:
        raise RuntimeError("Cannot read available RAM") from exc
    avail_mb = avail_kb // 1024
    if avail_mb < MIN_FREE_RAM_MB:
        raise RuntimeError(
            f"Insufficient RAM for study render: {avail_mb}MB available, need {MIN_FREE_RAM_MB}MB. "
            "Stop other heavy tasks and retry."
        )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def _normalize_clip_duration(path: Path, duration: float, *, env: dict[str, str]) -> None:
    """Pad short x11grab clips to the narration length (clone last frame)."""
    target = max(1.0, float(duration))
    actual = _probe_duration(path)
    if actual >= target * 0.98:
        return
    pad = max(0.0, target - actual)
    tmp = path.with_suffix(".norm.mp4")
    _run([
        "ffmpeg", "-y",
        "-i", str(path),
        "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
        "-t", f"{target:.3f}",
        "-an",
        "-r", str(FPS),
        "-vsync", "cfr",
        "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
        str(tmp),
    ], env=env, timeout=int(target) + 120)
    tmp.replace(path)


class StudyXvfbSession:
    """Manage an isolated Xvfb display for study (retro-movies) renders only."""

    def __init__(
        self,
        *,
        display: int = DEFAULT_DISPLAY,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        work_dir: Path | None = None,
    ) -> None:
        if display in FORBIDDEN_DISPLAYS:
            raise ValueError(
                f"Display :{display} is reserved (TigerVNC). "
                f"Use STUDY_XVFB_DISPLAY (default {DEFAULT_DISPLAY})."
            )
        self.display = display
        self.display_str = f":{display}"
        self.width = width
        self.height = height
        self.work_dir = work_dir or Path("/tmp/study-render")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._marker_dir = _MARKER_ROOT
        self._marker_dir.mkdir(parents=True, exist_ok=True)
        self._xvfb_pid: int | None = None
        self._lock_path = self._marker_dir / "render.lock"
        self._xvfb_marker = self._marker_dir / f"xvfb-{display}.pid"
        self._chrome_profile = self.work_dir / "chrome-profile"
        self._env = os.environ.copy()
        self._env["DISPLAY"] = self.display_str
        self._started_xvfb = False
        self._lock_fd: int | None = None

    def __enter__(self) -> StudyXvfbSession:
        _check_ram()
        self._acquire_lock()
        self._ensure_xvfb()
        return self

    def __exit__(self, *args: object) -> None:
        self._release_lock()
        if self._started_xvfb:
            self._stop_xvfb()

    def _acquire_lock(self) -> None:
        import fcntl

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another study render is already running") from exc
        os.write(self._lock_fd, str(os.getpid()).encode())

    def _release_lock(self) -> None:
        if self._lock_fd is not None:
            import fcntl

            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

    def _ensure_xvfb(self) -> None:
        if self._xvfb_marker.exists():
            try:
                pid = int(self._xvfb_marker.read_text().strip())
                if _pid_alive(pid):
                    self._xvfb_pid = pid
                    return
            except ValueError:
                pass

        proc = subprocess.Popen(
            [
                "Xvfb",
                self.display_str,
                "-screen", "0", f"{self.width}x{self.height}x24",
                "-ac", "+extension", "GLX", "+render", "-noreset",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(1.5)
        if proc.poll() is not None:
            raise RuntimeError(f"Xvfb failed to start on display {self.display_str}")
        self._xvfb_pid = proc.pid
        self._xvfb_marker.write_text(str(proc.pid), encoding="utf-8")
        self._started_xvfb = True

        def _cleanup() -> None:
            if self._started_xvfb:
                self._stop_xvfb()

        atexit.register(_cleanup)

    def _stop_xvfb(self) -> None:
        pid = self._xvfb_pid
        if pid and _pid_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            time.sleep(0.5)
        self._xvfb_marker.unlink(missing_ok=True)
        self._xvfb_pid = None
        self._started_xvfb = False

    def capture_scene(self, html_path: Path, duration: float, dest: Path) -> None:
        """Load HTML in Chrome on our display and record via ffmpeg x11grab."""
        if not html_path.exists():
            raise FileNotFoundError(f"HTML not found: {html_path}")
        duration = max(1.0, float(duration))
        dest.parent.mkdir(parents=True, exist_ok=True)

        self._chrome_profile.mkdir(parents=True, exist_ok=True)
        url = html_path.resolve().as_uri()

        chrome = subprocess.Popen(
            [
                CHROME_BIN,
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-sync",
                "--mute-audio",
                f"--window-size={self.width},{self.height}",
                "--window-position=0,0",
                f"--user-data-dir={self._chrome_profile}",
                f"--app={url}",
            ],
            env=self._env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        try:
            time.sleep(1.2)
            _run([
                "ffmpeg", "-y",
                "-f", "x11grab",
                "-draw_mouse", "0",
                "-video_size", f"{self.width}x{self.height}",
                "-framerate", str(FPS),
                "-thread_queue_size", "512",
                "-i", self.display_str,
                "-t", f"{duration:.3f}",
                "-r", str(FPS),
                "-vsync", "cfr",
                "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
                str(dest),
            ], env=self._env, timeout=int(duration) + 120)
            _normalize_clip_duration(dest, duration, env=self._env)
        finally:
            if chrome.poll() is None:
                try:
                    os.killpg(os.getpgid(chrome.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    chrome.terminate()
                try:
                    chrome.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    chrome.kill()

    def capture_scenes(
        self,
        scenes: list[tuple[Path, float, Path]],
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[Path]:
        """Capture multiple scenes sequentially."""
        results: list[Path] = []
        for i, (html_path, duration, dest) in enumerate(scenes):
            self.capture_scene(html_path, duration, dest)
            results.append(dest)
            if on_progress:
                on_progress(i + 1, len(scenes))
        return results
