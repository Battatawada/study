"""Tests for SECE composition engine."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sece.align import align_visual_plan_to_beats
from sece.beats import build_beats_for_segment, build_beats_document
from sece.compile import compile_full_document, compile_segment_full
from sece.composition import build_composition_spec
from sece.layout import build_layout_spec, layout_entity_center
from sece.motion_compiler import compile_render_ir_document, lock_timeline_to_beats
from sece.segments import build_segments_from_scene_clips
from sece.validate import run_all_pre_render, validate_segments
from sece.visual_plan import build_visual_plan_from_scene_clips


class SeceTests(unittest.TestCase):
    def test_segments_from_scene_clips(self) -> None:
        clips = [
            {
                "scene_id": 1,
                "narration": "Arrays. They use contiguous memory.",
                "visual_title": "Arrays",
                "diagram_type": "memory_layout",
                "music_mood": "focus",
            }
        ]
        doc = build_segments_from_scene_clips(clips, topic_slug="data-structures")
        self.assertEqual(len(doc["segments"]), 1)
        report = validate_segments(doc)
        self.assertEqual(report["status"], "PASS")

    def test_beats_proportional(self) -> None:
        beats = build_beats_for_segment(1, "Arrays. They use contiguous memory.", 4.0)
        self.assertGreaterEqual(len(beats), 2)
        self.assertEqual(beats[-1]["end_sec"], 4.0)

    def test_full_compile_pipeline(self) -> None:
        clips = [
            {
                "scene_id": 1,
                "narration": "HTTP 404. The page was not found.",
                "visual_title": "HTTP 404",
                "visual_bullets": ["Not found"],
                "diagram_type": "http_error_client",
                "diagram_labels": ["GET /x", "404"],
                "accent_color": "#EF4444",
            }
        ]
        segments_doc = build_segments_from_scene_clips(clips, topic_slug="http")
        visual_plan = build_visual_plan_from_scene_clips(clips, segments_doc)
        beats_doc = build_beats_document(
            segments_doc["segments"],
            [{"scene_id": 1, "duration_sec": 3.5}],
        )
        aligned = align_visual_plan_to_beats(visual_plan, beats_doc)
        compiled = compile_full_document(aligned, pipeline={"composition_engine": {"enabled": True}})
        render_ir = compiled["render_ir"]
        report = run_all_pre_render(
            segments_doc,
            visual_plan,
            beats_doc,
            aligned,
            render_ir,
            composition=compiled["composition"],
            layout=compiled["layout"],
            attention=compiled["attention"],
            camera=compiled["camera"],
        )
        self.assertEqual(report["status"], "PASS")
        seg_ir = render_ir["segments"][0]["render_ir"]
        self.assertTrue(seg_ir.get("camera"))
        self.assertTrue(seg_ir.get("layout"))

    def test_lock_timeline_to_beats(self) -> None:
        spec = {
            "kind": "memory",
            "timeline": [
                {"op": "appear_all", "at": 0, "duration": 0.4},
                {"op": "highlight", "at": 1, "duration": 0.2},
            ],
        }
        beats = [
            {"beat_id": "s1_b1", "start_sec": 0.0, "end_sec": 2.0, "text": "A.", "kind": "concept_label"},
            {"beat_id": "s1_b2", "start_sec": 2.0, "end_sec": 4.0, "text": "B.", "kind": "explanation"},
        ]
        locked = lock_timeline_to_beats(spec, beats)
        self.assertEqual(locked["timeline"][0]["at"], 0.0)
        self.assertEqual(locked["timeline"][1]["at"], 2.0)

    def test_layout_and_camera(self) -> None:
        segment = {
            "segment_id": 1,
            "duration_sec": 5.0,
            "layout_recipe": "memory_row",
            "entities": [
                {"entity_id": "s1_ram", "type": "region", "label": "RAM"},
                {"entity_id": "s1_cell_0", "type": "memory_cell", "label": "0"},
                {"entity_id": "s1_cell_1", "type": "memory_cell", "label": "1"},
            ],
            "beats": [
                {"beat_id": "s1_b1", "start_sec": 0, "end_sec": 2.5, "text": "RAM.", "kind": "concept_label"},
                {"beat_id": "s1_b2", "start_sec": 2.5, "end_sec": 5.0, "text": "Cells.", "kind": "explanation"},
            ],
            "attention_plan": [
                {"beat_id": "s1_b1", "primary_entity_id": "s1_ram", "secondary": []},
                {"beat_id": "s1_b2", "primary_entity_id": "s1_cell_1", "secondary": []},
            ],
            "visual_title": "Memory",
            "diagram_type": "memory_layout",
        }
        row = compile_segment_full(segment, pipeline={"composition_engine": {}})
        ir = row["render_ir"]
        self.assertEqual(len(ir["camera"]), 2)
        cx, cy = layout_entity_center(ir["layout"], "s1_cell_1")
        self.assertGreater(cx, 0)

    def test_semantic_ops_trigger_beat(self) -> None:
        from composition_motion.semantic_ops import compile_semantic_ops

        segment = {
            "segment_id": 1,
            "entities": [
                {"entity_id": "s1_cell_0", "type": "memory_cell", "label": "A"},
                {"entity_id": "s1_cell_1", "type": "memory_cell", "label": "B"},
            ],
            "beats": [
                {"beat_id": "s1_b1", "start_sec": 0.0, "end_sec": 2.0, "text": "First.", "kind": "explanation"},
                {"beat_id": "s1_b2", "start_sec": 2.0, "end_sec": 4.0, "text": "Second.", "kind": "explanation"},
            ],
            "semantic_ops": [
                {"op": "allocate", "entity_ids": ["s1_cell_0", "s1_cell_1"], "trigger_beat_id": "s1_b1"},
                {"op": "highlight", "entity_id": "s1_cell_1", "trigger_beat_id": "s1_b2"},
            ],
        }
        spec = compile_semantic_ops(segment)
        self.assertEqual(spec["timeline"][0]["at"], 0.0)
        self.assertEqual(spec["timeline"][1]["at"], 2.0)

    def test_validate_composition(self) -> None:
        from sece.composition import build_composition_spec
        from sece.validate import validate_composition

        segment = {
            "segment_id": 1,
            "layout_recipe": "memory_row",
            "entities": [{"entity_id": "s1_cell_0", "type": "memory_cell", "label": "0"}],
            "beats": [{"beat_id": "s1_b1", "start_sec": 0, "end_sec": 2, "text": "RAM.", "kind": "concept_label"}],
            "attention_plan": [{"beat_id": "s1_b1", "primary_entity_id": "s1_cell_0", "secondary": []}],
            "teaching_intent": {"build_policy": "construct_only"},
        }
        comp = build_composition_spec(segment)
        report = validate_composition({"segments": [comp]})
        self.assertEqual(report["status"], "PASS")

    def test_performance_overlap(self) -> None:
        segment = {
            "segment_id": 1,
            "duration_sec": 5.0,
            "entities": [
                {"entity_id": "s1_cell_0", "type": "memory_cell", "label": "A"},
                {"entity_id": "s1_cell_1", "type": "memory_cell", "label": "B"},
            ],
            "beats": [
                {"beat_id": "s1_b1", "start_sec": 0.0, "end_sec": 2.5, "text": "First.", "kind": "explanation"},
                {"beat_id": "s1_b2", "start_sec": 2.5, "end_sec": 5.0, "text": "Second.", "kind": "explanation"},
            ],
            "semantic_ops": [
                {"op": "allocate", "entity_ids": ["s1_cell_0", "s1_cell_1"], "trigger_beat_id": "s1_b1"},
                {"op": "highlight", "entity_id": "s1_cell_1", "trigger_beat_id": "s1_b2"},
            ],
            "attention_plan": [
                {"beat_id": "s1_b1", "primary_entity_id": "s1_cell_0", "secondary": []},
                {"beat_id": "s1_b2", "primary_entity_id": "s1_cell_1", "secondary": []},
            ],
            "visual_title": "Memory",
            "diagram_type": "memory_layout",
        }
        row = compile_segment_full(
            segment,
            pipeline={"composition_engine": {"enabled": True, "performance": {"enabled": True}}},
        )
        ir = row["render_ir"]
        perf = row.get("performance_spec")
        self.assertIsNotNone(perf)
        self.assertIn("performance", ir)
        self.assertGreater(perf["metrics"]["track_count"], 2)
        highlight = next(e for e in ir["timeline"] if e["op"] == "highlight")
        self.assertLess(highlight["at"], 2.5)
        self.assertGreater(perf["metrics"]["overlap_ratio"], 0.0)
        if ir.get("camera"):
            self.assertLess(ir["camera"][1]["at_sec"], 2.5)

    def test_performance_deterministic(self) -> None:
        from sece.performance import compile_segment_performance

        segment = {
            "segment_id": 1,
            "duration_sec": 4.0,
            "beats": [{"beat_id": "s1_b1", "start_sec": 0, "end_sec": 4, "text": "A.", "kind": "concept_label"}],
            "semantic_ops": [{"op": "allocate", "entity_ids": ["s1_cell_0"], "trigger_beat_id": "s1_b1"}],
            "entities": [{"entity_id": "s1_cell_0", "type": "memory_cell", "label": "0"}],
        }
        render_ir = {
            "segment_id": 1,
            "duration_sec": 4.0,
            "timeline": [{"op": "appear_all", "at": 0, "duration": 0.32, "values": ["0"], "addresses": ["0x000"]}],
            "camera": [],
        }
        attention = {"timeline": [{"beat_id": "s1_b1", "start_sec": 0, "end_sec": 4, "primary_entity_id": "s1_cell_0"}]}
        camera = {"channel": []}
        a = compile_segment_performance(segment, render_ir=render_ir, attention=attention, camera=camera)
        b = compile_segment_performance(segment, render_ir=render_ir, attention=attention, camera=camera)
        self.assertEqual(a["retimed"]["timeline"], b["retimed"]["timeline"])

    def test_filter_empty_narration_scenes(self) -> None:
        from common import filter_narrated_scenes, split_script_for_scenes

        clips = [
            {"scene_id": 1, "narration": "Arrays store values."},
            {"scene_id": 2, "narration": ""},
            {"scene_id": 3, "narration": "   "},
            {"scene_id": 4, "narration": "Pointers follow."},
        ]
        kept, dropped = filter_narrated_scenes(clips)
        self.assertEqual([c["scene_id"] for c in kept], [1, 4])
        self.assertEqual(dropped, [2, 3])

        chunks = split_script_for_scenes("One. Two. Three.", 10)
        self.assertTrue(all(c.strip() for c in chunks))
        self.assertLessEqual(len(chunks), 10)

    def test_beat_id_remap_clamps_invalid(self) -> None:
        from sece.align import align_visual_plan_to_beats, resolve_trigger_beat_id

        beats = [
            {"beat_id": "s7_b1", "start_sec": 0.0, "end_sec": 1.0, "text": "A.", "kind": "explanation"},
            {"beat_id": "s7_b2", "start_sec": 1.0, "end_sec": 2.0, "text": "B.", "kind": "explanation"},
        ]
        resolved, remap = resolve_trigger_beat_id("s7_b3", beats, op_index=1)
        self.assertEqual(resolved, "s7_b2")
        self.assertIsNotNone(remap)
        self.assertEqual(remap["reason"], "advisory_beat_index_clamped")

        visual_plan = {
            "schema_version": "1.0",
            "segments": [{
                "segment_id": 7,
                "entities": [{"entity_id": "s7_cell_0", "type": "memory_cell", "label": "A"}],
                "semantic_ops": [
                    {"op": "allocate", "entity_ids": ["s7_cell_0"], "trigger_beat_id": "s7_b1"},
                    {"op": "highlight", "entity_id": "s7_cell_0", "trigger_beat_id": "s7_b3"},
                ],
            }],
        }
        beats_doc = {
            "segments": [{"segment_id": 7, "duration_sec": 2.0, "beats": beats}],
        }
        aligned = align_visual_plan_to_beats(visual_plan, beats_doc)
        self.assertEqual(aligned["segments"][0]["semantic_ops"][1]["trigger_beat_id"], "s7_b2")
        self.assertTrue(any(r["from"] == "s7_b3" for r in aligned["beat_id_remaps"]))
        from sece.validate import validate_aligned_plan, validate_beat_id_remaps

        self.assertEqual(validate_aligned_plan(aligned)["status"], "PASS")
        remap_report = validate_beat_id_remaps(aligned["beat_id_remaps"])
        self.assertEqual(remap_report["status"], "PASS")
        self.assertGreater(remap_report["remap_count"], 0)

    def test_pipeline_hooks(self) -> None:
        from sece.pipeline import run_post_phase1, run_post_phase2

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips = [
                {
                    "scene_id": 1,
                    "narration": "Arrays store values.",
                    "visual_title": "Arrays",
                    "diagram_type": "array_access",
                    "diagram_labels": ["base", "index"],
                }
            ]
            pipeline = {
                "composition_engine": {"enabled": True, "fail_on_validation_error": False},
            }
            (work / "metadata.json").write_text(
                json.dumps({"topic_slug": "arrays", "topic": "Arrays"}),
                encoding="utf-8",
            )
            (work / "scene_clips.json").write_text(
                json.dumps({"scenes": clips, "render_mode": "slides"}),
                encoding="utf-8",
            )
            (work / "scene_durations.json").write_text(
                json.dumps([{"scene_id": 1, "duration_sec": 2.5}]),
                encoding="utf-8",
            )
            run_post_phase1(work, clips, topic_slug="arrays", topic_title="Arrays", pipeline=pipeline)
            self.assertTrue((work / "visual_plan.json").exists())
            run_post_phase2(work, pipeline=pipeline)
            self.assertTrue((work / "camera_channel.json").exists())
            self.assertTrue((work / "layout_spec.json").exists())
            self.assertTrue((work / "performance_spec.json").exists())
            merged = json.loads((work / "scene_clips.json").read_text(encoding="utf-8"))
            self.assertIn("camera", merged["scenes"][0]["render_ir"])
            self.assertIn("performance", merged["scenes"][0]["render_ir"])


if __name__ == "__main__":
    unittest.main()
