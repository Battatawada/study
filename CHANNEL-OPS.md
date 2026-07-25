# Simply Explained — Channel Operations Guide

> How to run the channel, what it looks like, and how video automation works.

---

## 1. What this channel is

**Simply Explained** (`@simplyexplainedyt`) publishes fast, dense tech explainers in the style of [Codist](https://youtu.be/vVL6NFzr0Rg), [Just Explained](https://youtu.be/2D2Z-eqK0YM), and [Infinite Codes](https://youtu.be/Fa_V9fP2tpU).

Each video = one topic mapped completely in 12–22 minutes. No fluff. Definition → example → next concept.

**Audience:** Students, self-taught developers, curious adults who want a complete mental model fast.

**Not:** Movie recaps, vlogs, live coding, or 60-minute deep dives.

---

## 2. Channel design (visual identity)

### Video look

```
┌─────────────────────────────────────────┐
│ ▌ HTTP 404                              │  ← accent bar (blue)
│                                         │
│   Page not found                        │  ← visual_title (white, bold)
│                                         │
│   • Client-side error                   │  ← bullets (gray)
│   • Server understood the request       │
│   • Resource doesn't exist              │
│                                         │
│                          Simply Explained│  ← watermark (subtle)
└─────────────────────────────────────────┘
   Background: #0f0f1a (dark navy)
```

### Thumbnail look

```
┌─────────────────────────────────────────┐
│                              🌐         │
│                                         │
│         HTTP                            │  ← white, huge
│         CODES                           │
│                                         │
│  ┌──────────┐                           │
│  │ EXPLAINED│              ┌─────────┐  │
│  └──────────┘              │ 14 MIN  │  │
│                            └─────────┘  │
└─────────────────────────────────────────┘
```

### Accent color rotation

| Color | Hex | Use for |
|-------|-----|---------|
| Blue | `#3B82F6` | Default / networking / web |
| Green | `#10B981` | Success / databases / growth |
| Amber | `#F59E0B` | Warnings / security cautions |
| Red | `#EF4444` | Errors / attacks / danger |
| Purple | `#8B5CF6` | AI / ML / abstract concepts |
| Cyan | `#06B6D4` | Hardware / systems |

---

## 3. How to operate (weekly workflow)

### Automated (GitHub Actions)

1. **Wednesday 2pm UTC** — pipeline runs automatically
2. Picks next topic from `config/topic_queue.json` (skips completed in `topic_history.json`)
3. NotebookLM writes script + slide map
4. Azure TTS generates narration
5. VPS renders slide video + muxes audio
6. Uploads to YouTube with SEO metadata + captions

### Manual trigger

```bash
# GitHub → Actions → "Simply Explained Pipeline" → Run workflow
# Optional: topic_slug = "http-status-codes"
```

### Adding new topics

Edit `config/topic_queue.json`:

```json
{
  "slug": "docker-concepts",
  "title": "Every Docker Concept",
  "minutes": 15,
  "enabled": true,
  "topic": "Every Docker Concept Explained in 15 Minutes",
  "category": "devops",
  "hook_angle": "Open on why your app works on your laptop but breaks in production"
}
```

### After upload

- Check YouTube Studio analytics at 48h: CTR > 5%, retention @ 30s > 40%
- If CTR low → fix thumbnail text alignment with title
- If retention low → cold open or concept pacing issue

### Retiring Retro Movie Archive

- Stop scheduling on `@retromoviearchive`
- Pin a community post redirecting to Simply Explained (optional)
- Do NOT delete old videos immediately — let them decay naturally

---

## 4. Video automation — what to use (and what NOT to)

### Recommendation: FFmpeg + PIL slides (current pipeline)

**Best for this channel format.** Matches what Codist/Just Explained actually look like — text on dark backgrounds, hard cuts, no fancy animation.

| Layer | Tool | Cost | Why |
|-------|------|------|-----|
| Script | NotebookLM + Claude | Existing | Research + glossary structure |
| TTS | Azure `GuyNeural` | ~$0/video | Fast, clear, already integrated |
| Slides | PIL + Python (`slide_builder.py`) | Free | Concept cards from JSON spec |
| Assembly | FFmpeg on VPS | Free | Image → video per scene, concat, mux |
| Thumbnail | PIL compositor | Free | Dark bg + bold text |
| Upload | YouTube Data API | Free | Already integrated |

**Total marginal cost per video:** ~$0.05–0.15 (NotebookLM + Azure TTS chars only).

### Google Flow — NOT recommended for this format

| Issue | Detail |
|-------|--------|
| Clip length | 4–8 seconds per generation — unusable for 15-min explainers |
| Watermark | Free tier exports include "Made with Veo" watermark |
| Automation | No official API; third-party wrappers are fragile |
| Style mismatch | Cinematic AI video ≠ text-on-dark-slides teaching format |
| Cost at scale | 50 credits/day = ~2–3 clips — would take weeks per video |

Flow is great for B-roll clips and Shorts. **Not for automated long-form teaching.**

### Alternatives evaluated

| Tool | Verdict | Notes |
|------|---------|-------|
| **FFmpeg + PIL slides** ✅ | **Use now** | Matches competitor visual style, fully automatable, runs on existing VPS |
| **Hyperframes** (HeyGen) | Phase 2 upgrade | HTML/CSS → MP4, agent-friendly, free (Apache 2.0). Good when you want animated transitions |
| **Remotion** | Phase 2 option | React-based, great for code animations. Needs Node.js on VPS |
| **Manim** | Skip for now | 3Blue1Brown style — overkill for glossary videos, high render failure rate |
| **Chalkboard** (LangGraph+Manim) | Skip for now | Impressive but complex; Manim codegen errors are common |
| **Google Flow / Veo** | Skip | Wrong format, watermark, no batch API |
| **Canva API** | Skip | Manual design, not pipeline-friendly |
| **Pictory / InVideo** | Skip | Paid SaaS, no control, expensive at volume |

### Upgrade path (when slides feel too static)

```
Phase 1 (now):     PIL slides + FFmpeg          ← Codist-style, zero new deps
Phase 2 (later):   Hyperframes on VPS           ← animated text, transitions, code blocks
Phase 3 (optional): Remotion for code-heavy topics ← live syntax highlighting
```

**Do not skip Phase 1.** Codist's 994K-view API video uses simple visuals. Content density beats animation polish.

---

## 5. File map (what changed in the pivot)

| File | Purpose |
|------|---------|
| `config/topic_queue.json` | Topic queue (replaces `movie_queue.json`) |
| `config/niche.json` | Channel identity |
| `config/channel_playbook.md` | Brand bible for NotebookLM |
| `config/prompts/*.txt` | Script + visual + SEO prompts |
| `config/pipeline.json` | TTS tuning, slide settings, duration |
| `src/phase1_script.py` | Script + visual mapping generation |
| `src/phase2_audio.py` | Azure TTS (unchanged core) |
| `vps/slide_builder.py` | PIL slide image generation |
| `vps/phase3_render.py` | Slide render + FFmpeg assembly |
| `.github/workflows/pipeline.yml` | GHA orchestration |

---

## 6. VPS setup (unchanged infra)

Same Oracle VPS, port **8766**:

```powershell
.\scripts\deploy-vps.ps1
```

Movies directory (`/opt/movies`) is no longer needed. Render uses slide images only.

---

## 7. First 5 videos to publish (recommended order)

| # | Topic | Why first |
|---|-------|-----------|
| 1 | Every HTTP Status Code Explained in 14 Minutes | High search volume, easy slides |
| 2 | Every Data Structure Simply Explained in 22 Minutes | Codist-proven format |
| 3 | Every Essential Linux Command Explained in 16 Minutes | Broad audience |
| 4 | Every Type of API Explained in 16 Minutes | Codist's biggest hit (994K) |
| 5 | Every Cyber Attack Explained in 17 Minutes | Curiosity + shareability |

Publish one per week. Do not batch-upload — algorithm needs time per video.

---

*Operations guide for Simply Explained pivot — 2026-07-25*
