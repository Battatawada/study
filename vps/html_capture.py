"""Capture HTML/CSS slides as 1080p video via timed Playwright screenshots.

Uses the browser layout engine (not PIL) so typography, spacing, and CSS
animations stay pixel-aligned at 1920x1080.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

_MARKER_ROOT = Path(os.environ.get("RUNS_DIR", "/opt/retro-movies/runs")) / ".study-render"
DEFAULT_WIDTH = int(os.environ.get("STUDY_CAPTURE_WIDTH", "1920"))
DEFAULT_HEIGHT = int(os.environ.get("STUDY_CAPTURE_HEIGHT", "1080"))
DEFAULT_FPS = int(os.environ.get("STUDY_CAPTURE_FPS", "24"))
MIN_FREE_RAM_MB = int(os.environ.get("STUDY_MIN_FREE_RAM_MB", "250"))
CHROME_CHANNEL = os.environ.get("STUDY_CHROME_CHANNEL", "chrome")
FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "2")
X264_PRESET = os.environ.get("FFMPEG_PRESET", "ultrafast")


def _run(cmd: list[str], *, timeout: int | None = None) -> None:
    if cmd[:2] == ["ffmpeg", "-y"] and "-threads" not in cmd:
        cmd = ["ffmpeg", "-y", "-threads", FFMPEG_THREADS, *cmd[2:]]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


def _encode_frames(frames_dir: Path, dest: Path, *, duration: float, fps: int, width: int, height: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-t", f"{duration:.3f}",
        "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p,fps={fps}",
        "-an",
        "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
        str(dest),
    ], timeout=int(duration) + 300)


class HtmlSlideCaptureSession:
    """Reusable headless Chrome session for HTML slide frame capture."""

    def __init__(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        work_dir: Path | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = max(12, int(fps))
        self.work_dir = work_dir or Path("/tmp/study-html-capture")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = _MARKER_ROOT / "render.lock"
        self._lock_fd: int | None = None
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> HtmlSlideCaptureSession:
        _check_ram()
        self._acquire_lock()
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_kwargs: dict = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-remote-fonts",
            ],
        }
        if CHROME_CHANNEL:
            launch_kwargs["channel"] = CHROME_CHANNEL
        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        self._context = self._browser.new_context(
            viewport={"width": self.width, "height": self.height},
            device_scale_factor=1,
            color_scheme="dark",
        )
        return self

    def __exit__(self, *args: object) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._release_lock()

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

    def capture_scene(self, html_path: Path, duration: float, dest: Path, *, semantic: bool = False) -> None:
        """Screenshot HTML slide frames, then encode to a scene clip."""
        if self._context is None:
            raise RuntimeError("HtmlSlideCaptureSession is not active")
        if not html_path.exists():
            raise FileNotFoundError(f"HTML not found: {html_path}")

        duration = max(1.0, float(duration))
        n_frames = max(2, int(round(duration * self.fps)))
        interval = duration / n_frames
        frames_dir = self.work_dir / f"frames_{dest.stem}"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        frames_dir.mkdir(parents=True)

        page = self._context.new_page()
        page.set_default_timeout(120_000)
        try:
            page.goto(html_path.resolve().as_uri(), wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(120)

            has_driver = False
            if semantic:
                has_driver = page.evaluate("() => typeof window.__renderAt === 'function'")

            started = time.perf_counter()
            for i in range(n_frames):
                if has_driver:
                    t = (i / max(1, n_frames - 1)) * duration
                    page.evaluate("(t) => window.__renderAt(t)", t)
                page.screenshot(
                    path=str(frames_dir / f"frame_{i:04d}.png"),
                    full_page=False,
                    type="png",
                    timeout=120_000,
                )
                if i < n_frames - 1:
                    target = started + (i + 1) * interval
                    delay = target - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
        finally:
            page.close()

        try:
            _encode_frames(
                frames_dir,
                dest,
                duration=duration,
                fps=self.fps,
                width=self.width,
                height=self.height,
            )
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)
