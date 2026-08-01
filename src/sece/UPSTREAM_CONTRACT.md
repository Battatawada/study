# SECE Upstream Contract — Ghost Scenes & Beat IDs

Strict validation (`fail_on_validation_error: true`) is intentional.
SECE must receive valid inputs; the compiler must not tolerate bad data.

## 1. Empty narration / ghost scenes (segments 50–60 class)

### Root cause

`split_script_for_scenes()` estimated `N = estimate_scene_count(script)` scenes,
then **padded the tail with empty strings** when sentence/word packing underfilled `N`:

```python
while len(chunks) < num_scenes:
    chunks.append("")
```

Also, when `len(sentences) <= num_scenes` historically returned
`sentences + [""] * (num_scenes - len(sentences))`.

Visual mapping still produced slide specs for those silent pads (title/diagram only),
so `scene_clips` contained empty-narration scenes. SECE V1 correctly rejected them.

These were **not** end-card placeholders — they were over-estimated scene-count pads.

### Fix (upstream only)

1. `split_script_for_scenes` never returns empty chunks; may return fewer than requested.
2. Phase 1 folds undersized tails (`min_words_per_scene`) and filters empty narration.
3. SECE `run_post_phase1` / `run_post_phase2` call `filter_narrated_scenes` before
   `segments.json` / `visual_plan.json` are built; audit in `U0_ghost_scene_cleanup`.

Validation still **FAIL**s if an empty segment somehow reaches `validate_segments`.

## 2. Invalid `trigger_beat_id` (e.g. `s7_b3`)

### Root cause

Beat IDs are invented **before** the authoritative beat graph exists:

1. `visual_mapping.txt` previously instructed the LLM to emit
   `trigger_beat_id: s{{scene_id}}_b1, s{{scene_id}}_b2, …`
2. The example JSON hardcoded `s1_b1` + `s1_b2` (two-beat allocate/highlight pattern).
3. Beats are only built after TTS from real sentence splits / word timings
   (`build_beats_for_segment`). A scene with 1–2 sentences cannot have `b3`.
4. `align.py` previously only filled **missing** IDs; invalid LLM IDs were kept.

So the LLM was:

- generating beat IDs **before narration segmentation into beats**
- often **assuming a fixed 2-beat op pattern** from the prompt example
- occasionally **estimating more phrase beats than TTS will produce**

### Fix (upstream only)

1. Prompt: `trigger_beat_id` must be `null` / omitted — advisory timing only via op order.
2. `sanitize_llm_semantic_ops()` strips any concrete `sN_bM` values to null at visual_plan ingest
   (only null accepted from the LLM; optional advisory retained for remap hints).
3. `align.py`: treat any remaining beat ID as advisory; remap onto the real beat list
   (keep if valid; else clamp beat index / op index). Never drop ops. Never invent beats.
4. Every remap is recorded in `aligned_plan.beat_id_remaps` and validation report
   stage `U1_beat_id_remap` (PASS with warnings — audit trail).
5. Regression suite: `tests/test_upstream_contract.py` (CI gate in pipeline.yml).

`validate_aligned_plan` remains strict: post-remap IDs must exist or validation FAIL.

## 3. Policy

| Layer | Responsibility |
|-------|----------------|
| Phase 1 / split | No empty narration chunks |
| Align | Remap advisory beat IDs → real beats |
| Validate | Fail on empty text / invalid beat IDs that survive remap |
| Performance Compiler | Untouched |
