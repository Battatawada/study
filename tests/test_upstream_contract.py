"""Regression tests for SECE upstream contract.

These must fail loudly if ghost scenes, invented beat IDs, or weak validation
silently return. See src/sece/UPSTREAM_CONTRACT.md.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from common import filter_narrated_scenes, split_script_for_scenes
from sece.align import align_visual_plan_to_beats, resolve_trigger_beat_id
from sece.pipeline import run_post_phase1, run_post_phase2
from sece.validate import (
    run_all_pre_render,
    validate_aligned_plan,
    validate_beat_id_remaps,
    validate_render_ir,
    validate_segments,
)
from sece.visual_plan import (
    build_visual_plan_from_scene_clips,
    is_concrete_trigger_beat_id,
    sanitize_llm_semantic_ops,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
VISUAL_MAPPING_PROMPT = REPO_ROOT / "config" / "prompts" / "visual_mapping.txt"


class GhostSceneRegression(unittest.TestCase):
    def test_split_script_never_emits_empty_chunks(self) -> None:
        cases = [
            ("One. Two. Three.", 10),
            ("word " * 20, 60),
            ("Short.", 15),
            ("A. B. C. D. E. F. G. H. I. J.", 50),
            ("", 5),
        ]
        for script, n in cases:
            with self.subTest(n=n, script=script[:20]):
                chunks = split_script_for_scenes(script, n)
                self.assertTrue(all(isinstance(c, str) and c.strip() for c in chunks) or chunks == [])
                self.assertNotIn("", chunks)
                self.assertTrue(all(c.strip() for c in chunks))

    def test_filter_removes_empty_before_sece(self) -> None:
        clips = [
            {"scene_id": 1, "narration": "HTTP 404 means not found."},
            {"scene_id": 2, "narration": ""},
            {"scene_id": 3, "narration": "   \n\t  "},
            {"scene_id": 4, "narration": "Servers return 500 on failure."},
        ]
        kept, dropped = filter_narrated_scenes(clips)
        self.assertEqual(dropped, [2, 3])
        self.assertEqual([c["scene_id"] for c in kept], [1, 4])
        self.assertTrue(all(str(c["narration"]).strip() for c in kept))

    def test_phase1_sece_never_writes_empty_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips = [
                {
                    "scene_id": 1,
                    "narration": "Arrays store contiguous values.",
                    "visual_title": "Arrays",
                    "diagram_type": "memory_layout",
                    "diagram_labels": ["0", "1"],
                },
                {
                    "scene_id": 2,
                    "narration": "",
                    "visual_title": "Ghost",
                    "diagram_type": "concept",
                },
                {
                    "scene_id": 3,
                    "narration": "Pointers follow links.",
                    "visual_title": "Pointers",
                    "diagram_type": "linked_nodes",
                    "diagram_labels": ["Head", "A"],
                },
            ]
            (work / "scene_clips.json").write_text(
                json.dumps({"scenes": clips, "render_mode": "slides"}),
                encoding="utf-8",
            )
            pipeline = {"composition_engine": {"enabled": True, "fail_on_validation_error": True}}
            run_post_phase1(
                work,
                clips,
                topic_slug="contract",
                topic_title="Contract",
                pipeline=pipeline,
            )
            segments = json.loads((work / "segments.json").read_text(encoding="utf-8"))["segments"]
            self.assertEqual(len(segments), 2)
            self.assertTrue(all(str(s.get("text", "")).strip() for s in segments))
            report = json.loads((work / "validation_report_phase1.json").read_text(encoding="utf-8"))
            self.assertEqual(report["ghost_scenes_dropped"], [2])


class BeatRemapRegression(unittest.TestCase):
    def test_align_remaps_invalid_ids_deterministically(self) -> None:
        visual_plan = {
            "schema_version": "1.0",
            "segments": [{
                "segment_id": 7,
                "entities": [
                    {"entity_id": "s7_cell_0", "type": "memory_cell", "label": "A"},
                    {"entity_id": "s7_cell_1", "type": "memory_cell", "label": "B"},
                ],
                "semantic_ops": [
                    {"op": "allocate", "entity_ids": ["s7_cell_0", "s7_cell_1"], "trigger_beat_id": "s7_b1"},
                    {"op": "highlight", "entity_id": "s7_cell_1", "trigger_beat_id": "s7_b3"},
                    {"op": "caption", "text": "note", "trigger_beat_id": "s7_b99"},
                ],
            }],
        }
        beats = [
            {"beat_id": "s7_b1", "start_sec": 0.0, "end_sec": 1.0, "text": "First.", "kind": "explanation"},
            {"beat_id": "s7_b2", "start_sec": 1.0, "end_sec": 2.0, "text": "Second.", "kind": "explanation"},
        ]
        beats_doc = {"segments": [{"segment_id": 7, "duration_sec": 2.0, "beats": beats}]}

        a = align_visual_plan_to_beats(visual_plan, beats_doc)
        b = align_visual_plan_to_beats(visual_plan, beats_doc)
        self.assertEqual(a["beat_id_remaps"], b["beat_id_remaps"])
        self.assertEqual(a["segments"][0]["semantic_ops"], b["segments"][0]["semantic_ops"])

        ops = a["segments"][0]["semantic_ops"]
        self.assertEqual(ops[0]["trigger_beat_id"], "s7_b1")
        self.assertEqual(ops[1]["trigger_beat_id"], "s7_b2")
        self.assertEqual(ops[2]["trigger_beat_id"], "s7_b2")
        self.assertGreaterEqual(len(a["beat_id_remaps"]), 2)
        self.assertTrue(any(r["from"] == "s7_b3" and r["to"] == "s7_b2" for r in a["beat_id_remaps"]))
        self.assertEqual(validate_aligned_plan(a)["status"], "PASS")

    def test_remaps_recorded_in_validation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips = [{
                "scene_id": 1,
                "narration": "First sentence. Second sentence.",
                "visual_title": "Beats",
                "diagram_type": "memory_layout",
                "diagram_labels": ["0", "1"],
                "entities": [
                    {"entity_id": "s1_cell_0", "type": "memory_cell", "label": "0"},
                    {"entity_id": "s1_cell_1", "type": "memory_cell", "label": "1"},
                ],
                # Intentionally invalid advisory IDs (bypass sanitize via align input path)
                "semantic_ops": [
                    {"op": "allocate", "entity_ids": ["s1_cell_0", "s1_cell_1"], "trigger_beat_id": "s1_b1"},
                    {"op": "highlight", "entity_id": "s1_cell_1", "trigger_beat_id": "s1_b9"},
                ],
            }]
            (work / "metadata.json").write_text(
                json.dumps({"topic_slug": "beats", "topic": "Beats"}),
                encoding="utf-8",
            )
            (work / "scene_clips.json").write_text(
                json.dumps({"scenes": clips, "render_mode": "slides"}),
                encoding="utf-8",
            )
            (work / "scene_durations.json").write_text(
                json.dumps([{"scene_id": 1, "duration_sec": 3.0}]),
                encoding="utf-8",
            )
            pipeline = {
                "composition_engine": {
                    "enabled": True,
                    "fail_on_validation_error": True,
                    "performance": {"enabled": True},
                }
            }
            # Inject invalid IDs into visual_plan after phase1 sanitize by writing plan directly.
            run_post_phase1(work, clips, topic_slug="beats", topic_title="Beats", pipeline=pipeline)
            plan = json.loads((work / "visual_plan.json").read_text(encoding="utf-8"))
            plan["segments"][0]["semantic_ops"] = [
                {"op": "allocate", "entity_ids": ["s1_cell_0", "s1_cell_1"], "trigger_beat_id": "s1_b1"},
                {"op": "highlight", "entity_id": "s1_cell_1", "trigger_beat_id": "s1_b9"},
            ]
            (work / "visual_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

            run_post_phase2(work, pipeline=pipeline)
            report = json.loads((work / "validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            remap_stages = [r for r in report["reports"] if r["stage"] == "U1_beat_id_remap"]
            self.assertEqual(len(remap_stages), 1)
            self.assertGreater(remap_stages[0]["remap_count"], 0)
            self.assertTrue(any("s1_b9" in w for w in remap_stages[0]["warnings"]))
            aligned = json.loads((work / "aligned_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(any(r.get("from") == "s1_b9" for r in aligned["beat_id_remaps"]))


class StrictValidationRegression(unittest.TestCase):
    """Feed malformed artifacts directly into SECE validators (bypass Phase 1)."""

    def test_empty_narration_fails(self) -> None:
        report = validate_segments({
            "schema_version": "1.0",
            "segments": [{"segment_id": 50, "text": ""}],
        })
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("empty text" in e for e in report["errors"]))

    def test_unresolved_beat_ids_fail(self) -> None:
        report = validate_aligned_plan({
            "segments": [{
                "segment_id": 7,
                "beats": [{"beat_id": "s7_b1"}],
                "entities": [{"entity_id": "s7_cell_0"}],
                "semantic_ops": [{"op": "highlight", "entity_id": "s7_cell_0", "trigger_beat_id": "s7_b3"}],
            }],
        })
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("invalid trigger_beat_id" in e for e in report["errors"]))

    def test_invalid_entity_references_fail(self) -> None:
        report = validate_aligned_plan({
            "segments": [{
                "segment_id": 1,
                "beats": [{"beat_id": "s1_b1"}],
                "entities": [{"entity_id": "s1_cell_0"}],
                "semantic_ops": [
                    {"op": "highlight", "entity_id": "missing_cell", "trigger_beat_id": "s1_b1"},
                ],
            }],
        })
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("invalid entity_id" in e for e in report["errors"]))

    def test_malformed_render_ir_fails(self) -> None:
        report = validate_render_ir({
            "schema_version": "1.2",
            "segments": [{
                "segment_id": 1,
                "duration_sec": 2.0,
                "render_ir": {
                    "duration_sec": 2.0,
                    "timeline": [{"op": "appear_all", "at": 9.5, "duration": 0.3}],
                    "camera": [{"at_sec": 5.0, "duration_sec": 0.5}],
                    "layout": {"stage": {"width": 100, "height": 100}, "entities": []},
                },
            }],
        })
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("outside duration" in e for e in report["errors"]))

    def test_run_all_pre_render_fails_on_empty_segment(self) -> None:
        report = run_all_pre_render(
            {"schema_version": "1.0", "segments": [{"segment_id": 1, "text": ""}]},
            {"segments": []},
            {"segments": []},
            {"segments": []},
            {"segments": []},
        )
        self.assertEqual(report["status"], "FAIL")


class ContractRegression(unittest.TestCase):
    def test_visual_mapping_prompt_requires_null_beat_ids(self) -> None:
        text = VISUAL_MAPPING_PROMPT.read_text(encoding="utf-8")
        self.assertIn("trigger_beat_id", text)
        self.assertRegex(text, r"trigger_beat_id:\s*ALWAYS null")
        self.assertIn("do NOT invent", text)
        # Example JSON must use null, not concrete sN_bM.
        self.assertIn('"trigger_beat_id":null', text.replace(" ", ""))
        concrete_in_example = re.findall(r'"trigger_beat_id"\s*:\s*"s\d+_b\d+"', text)
        self.assertEqual(
            concrete_in_example,
            [],
            f"visual_mapping.txt must not exemplify concrete beat IDs: {concrete_in_example}",
        )

    def test_llm_concrete_beat_ids_stripped_to_null(self) -> None:
        ops = sanitize_llm_semantic_ops([
            {"op": "allocate", "entity_ids": ["s1_cell_0"], "trigger_beat_id": "s1_b1"},
            {"op": "highlight", "entity_id": "s1_cell_0", "trigger_beat_id": "s1_b2"},
            {"op": "caption", "text": "ok", "trigger_beat_id": None},
        ])
        self.assertTrue(is_concrete_trigger_beat_id("s1_b1"))
        self.assertFalse(is_concrete_trigger_beat_id(None))
        self.assertIsNone(ops[0]["trigger_beat_id"])
        self.assertIsNone(ops[1]["trigger_beat_id"])
        self.assertEqual(ops[0]["llm_trigger_beat_id_advisory"], "s1_b1")
        self.assertIsNone(ops[2]["trigger_beat_id"])

        clips = [{
            "scene_id": 1,
            "narration": "RAM is contiguous.",
            "visual_title": "RAM",
            "diagram_type": "memory_layout",
            "entities": [{"entity_id": "s1_cell_0", "type": "memory_cell", "label": "0"}],
            "semantic_ops": [
                {"op": "allocate", "entity_ids": ["s1_cell_0"], "trigger_beat_id": "s1_b1"},
                {"op": "highlight", "entity_id": "s1_cell_0", "trigger_beat_id": "s1_b2"},
            ],
        }]
        plan = build_visual_plan_from_scene_clips(clips)
        for op in plan["segments"][0]["semantic_ops"]:
            self.assertIsNone(op.get("trigger_beat_id"))

    def test_beat_assignment_happens_only_after_beat_generation(self) -> None:
        """visual_plan has null IDs; align assigns from beats_doc after generation."""
        clips = [{
            "scene_id": 3,
            "narration": "One. Two.",
            "visual_title": "Order",
            "diagram_type": "memory_layout",
            "entities": [
                {"entity_id": "s3_cell_0", "type": "memory_cell", "label": "0"},
                {"entity_id": "s3_cell_1", "type": "memory_cell", "label": "1"},
            ],
            "semantic_ops": [
                {"op": "allocate", "entity_ids": ["s3_cell_0", "s3_cell_1"], "trigger_beat_id": "s3_b1"},
                {"op": "highlight", "entity_id": "s3_cell_1", "trigger_beat_id": "s3_b2"},
            ],
        }]
        plan = build_visual_plan_from_scene_clips(clips)
        for op in plan["segments"][0]["semantic_ops"]:
            self.assertIsNone(
                op.get("trigger_beat_id"),
                "Beat IDs must not be concrete before beat generation",
            )

        beats_doc = {
            "segments": [{
                "segment_id": 3,
                "duration_sec": 2.0,
                "beats": [
                    {"beat_id": "s3_b1", "start_sec": 0.0, "end_sec": 1.0, "text": "One.", "kind": "explanation"},
                    {"beat_id": "s3_b2", "start_sec": 1.0, "end_sec": 2.0, "text": "Two.", "kind": "explanation"},
                ],
            }],
        }
        aligned = align_visual_plan_to_beats(plan, beats_doc)
        ops = aligned["segments"][0]["semantic_ops"]
        self.assertEqual(ops[0]["trigger_beat_id"], "s3_b1")
        self.assertEqual(ops[1]["trigger_beat_id"], "s3_b2")
        # Assignment recorded as missing_advisory → real beat
        self.assertTrue(all(op["trigger_beat_id"] in {"s3_b1", "s3_b2"} for op in ops))
        remap_report = validate_beat_id_remaps(aligned.get("beat_id_remaps"))
        self.assertEqual(remap_report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
