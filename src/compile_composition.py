#!/usr/bin/env python3
"""Compile SECE artifacts (beats alignment + render_ir) from phase1/phase2 outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import CONFIG, load_json
from sece.pipeline import compile_from_directory, composition_enabled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("output"))
    args = parser.parse_args()

    pipeline_path = args.input / "pipeline.json"
    if pipeline_path.exists():
        pipeline = load_json(pipeline_path)
    else:
        pipeline = load_json(CONFIG / "pipeline.json")

    if not composition_enabled(pipeline):
        print("composition_engine disabled — nothing to compile", flush=True)
        return

    compile_from_directory(args.input, pipeline)
    report_path = args.input / "validation_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": report.get("status"), "reports": len(report.get("reports", []))}), flush=True)
        if report.get("status") == "FAIL":
            sys.exit(1)


if __name__ == "__main__":
    main()
