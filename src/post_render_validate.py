#!/usr/bin/env python3
"""Post-render validation — video duration and artifact presence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import load_json
from sece.pipeline import composition_enabled


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def validate_post_render(work_dir: Path, pipeline: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    video = work_dir / "final_video.mp4"
    if not video.exists():
        video = work_dir / "video.mp4"
    if not video.exists():
        errors.append("final video missing")
        return {"status": "FAIL", "errors": errors, "warnings": warnings}

    durations = load_json(work_dir / "scene_durations.json")
    expected = sum(float(d.get("duration_sec", 0)) for d in durations)
    actual = probe_duration(video)
    if expected > 0 and actual < expected * 0.9:
        errors.append(f"video duration {actual:.1f}s < expected {expected:.1f}s")

    if composition_enabled(pipeline):
        required = [
            "render_ir.json",
            "beats.json",
            "aligned_plan.json",
            "validation_report.json",
        ]
        for name in required:
            if not (work_dir / name).exists():
                errors.append(f"missing SECE artifact {name}")

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "video_duration_sec": actual,
        "expected_audio_sec": expected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("output"))
    args = parser.parse_args()

    pipeline_path = args.input / "pipeline.json"
    pipeline = load_json(pipeline_path) if pipeline_path.exists() else {}
    report = validate_post_render(args.input, pipeline)
    out_path = args.input / "post_render_validation.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    if report["status"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
