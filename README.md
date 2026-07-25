# Simply Explained

Automated **tech explainer** pipeline: NotebookLM script → Azure TTS narration → Oracle VPS ffmpeg slide render → YouTube upload.

Style reference: [Codist](https://youtu.be/vVL6NFzr0Rg), [Just Explained](https://youtu.be/2D2Z-eqK0YM), [Infinite Codes](https://youtu.be/Fa_V9fP2tpU).

**See [CHANNEL-OPS.md](CHANNEL-OPS.md) for channel design, operations, and video automation decisions.**

## Architecture

```
GitHub Actions                         Oracle VPS (:8766)
────────────────                       ──────────────────
Phase 1  NotebookLM → script           PIL slide images
         + scene_clips.json              per concept
Phase 2  Azure TTS → narration.mp3
         trigger VPS ─────────────────►  ffmpeg slide + mux
Poll + download ◄────────────────────  final_video.mp4
Phase 5  YouTube upload
```

**Slide visuals** — dark concept cards with title + bullets. No film clips, no AI video generation.

## Quick start (local)

```powershell
cd "C:\Users\Pracheer\Music\Retro Movie Archive"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
notebooklm login

# Dry-run Phase 1 (no NotebookLM):
python src/phase1_script.py --dry-run --output output

# Full run with a specific topic:
python src/phase1_script.py --topic-slug http-status-codes --output output
```

Add topics in `config/topic_queue.json`. See `CHANNEL-OPS.md` for the full topic list and publishing order.

## Pipeline phases

| Phase | Where | Output |
|-------|--------|--------|
| 1 | GHA | `scene_clips.json`, `script.txt`, SEO |
| 2 | GHA | `narration.mp3`, `captions.srt` |
| 3–4 | VPS | `final_video.mp4` |
| 5 | GHA | YouTube upload |

## Secrets

Same as before — see `.env.example` for `NOTEBOOKLM_AUTH_JSON`, `AZURE_SPEECH_KEY`, `VPS_WEBHOOK_URL`, YouTube OAuth.

## Pivot note

This repo was **Retro Movie Archive** (film recaps). The movie/SRT pipeline code remains in `vps/phase3_render.py` as `_run_film_clip_render_sync` for legacy runs. New videos use `render_mode: slides`.
