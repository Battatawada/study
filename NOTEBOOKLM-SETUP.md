# NotebookLM setup — Simply Explained (separate profile)

Use a **dedicated NotebookLM Google account/profile** so crime/psychology notebooks never collide.

**Package:** pinned to [notebooklm-py main](https://github.com/teng-lin/notebooklm-py) (includes Gemini Notebook login fix, commit `6f75779`). Google rebranded NotebookLM → **Gemini Notebook** — login may redirect to `notebook.google.com` (old `notebooklm.google.com` still works).

## Local (one-time)

```powershell
cd "C:\Users\Pracheer\Music\Retro Movie Archive"

# Create isolated profile
notebooklm profile create study
notebooklm -p study login
notebooklm -p study status
```

Verify:

```powershell
$env:NOTEBOOKLM_PROFILE = "study"
notebooklm auth check --test --json
```

## Export secret for GitHub Actions

```powershell
python scripts/save_notebooklm_auth.py --profile study
# Or: scripts/export_notebooklm_secret.ps1 with profile study
```

Copy output → GitHub secret **`NOTEBOOKLM_AUTH_JSON`** on the retro repo.

## GitHub Actions

Workflow sets `NOTEBOOKLM_PROFILE: study` on Phase 1 steps.

Auth JSON is profile-specific — do not reuse crime/psychology secrets.

## What Phase 1 ingests (style)

From `config/seed_channels.json`:

| Source | Count | Purpose |
|--------|-------|---------|
| [@movierecapsofficial](https://www.youtube.com/@movierecapsofficial) | channel | Pacing + structure |
| [@HauntingTube](https://www.youtube.com/@HauntingTube) | channel | Tone + hooks |
| [@mysteryrecappedofficial](https://www.youtube.com/@mysteryrecappedofficial) | channel | SEO + thumbnails |
| [Sample video 1](https://www.youtube.com/watch?v=5ekfnZBxbJw) | video | Subtitle-level analysis |
| [Sample video 2](https://www.youtube.com/watch?v=ZD8J5FBbYIE) | video | Subtitle-level analysis |
| [Sample video 3](https://www.youtube.com/watch?v=W5ESi5qDxCY) | video | Subtitle-level analysis |
| [Music reference](https://www.youtube.com/watch?v=CDWtH8eHeEU) | audio vibe | BG music mood only |

NotebookLM analyzes **video subtitles/transcripts** per sample video, then writes `output/style_notes.txt` used by script/SEO/thumbnail prompts.

## Refresh cadence

Re-run `notebooklm -p study login` every 1–2 weeks; re-export `NOTEBOOKLM_AUTH_JSON`.

For unattended CI, consider master-token auth (`notebooklm login --master-token --account you@example.com`) — see the [notebooklm-py auth docs](https://github.com/teng-lin/notebooklm-py/blob/main/docs/auth-cookie-lifecycle.md).
