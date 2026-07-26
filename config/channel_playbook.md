# Simply Explained — Channel Playbook

> Feed this document to NotebookLM before Phase 1 runs.
> Reference channels: `config/seed_channels.json`

## Channel identity

| Field | Value |
|-------|--------|
| Channel | Simply Explained (`@simplyexplainedyt`) |
| Host voice | Single male narrator — fast, clear, teacher energy |
| Tone | Dense encyclopedia explainer — not hype, not bro-YouTube |
| Format | 12–22 min concept maps, slide visuals + AI VO + minimal lo-fi bed |
| **Visual** | Dark slide cards with **animated diagrams** (request/response, cache, errors) + bullets |

---

## A. Title patterns (from Codist, Just Explained, Infinite Codes)

**What wins clicks in this niche:**

- **"Every X Explained in Y Minutes"** — primary formula
- **"All X Explained in Y Minutes"** — variant for glossaries
- Time promise in title: 10–22 minutes based on topic breadth
- Specific > vague: "Every HTTP Status Code" beats "Web Stuff Explained"

**Clickable shapes:**

- `Every [Topic] Explained in [N] Minutes`
- `All [Topic] Terms Explained in [N] Minutes`
- `Every Type of [X] Explained in [N] Minutes`

**Avoid:**

- ALL CAPS spam, emoji in title, fake urgency
- Vague titles: "Programming Explained" (too broad)
- Duplicate topic on channel page — **one topic = one video, ever**

**Note:** "Explained" is a **required SEO anchor** — do not ban it.

---

## B. Thumbnail patterns

- **Dark navy background** (#0f0f1a) — matches slide aesthetic
- **Bold white topic name** — 2–4 words (HTTP CODES, DATA STRUCTURES)
- **Time badge** — "14 MIN" chip in accent color
- **"EXPLAINED" subtitle chip** — blue/green accent
- **Optional emoji** — one relevant icon (🌐 🔐 💾)
- **Never:** actor faces, film stills, 6-panel collage, red arrows

---

## C. Hook / retention (first 30–45 seconds)

Reference channels open with **one concrete example**, not channel intro.

**Simply Explained cold-open formula:**

1. **0–5 sec:** Concrete noun — specific object, command, or fact
2. **5–15 sec:** Why it's surprising or important
3. **15–30 sec:** Promise — "let me explain every X" or "here's how it all connects"
4. **30–45 sec:** First concept label — "Arrays." or "HTTP 404." then definition

**Do NOT open with:** "Welcome back", "In this video", "Today we'll learn"

**Retention cadence (full video):**

- New concept every 45–90 seconds
- Spoken section labels: "Next up: Binary Trees."
- Definition → example → connect to next concept
- Recap in final 60 seconds (3–5 key takeaways)

---

## D. What NOT to copy

- Movie recap dramatic hooks ("the ending will shock you")
- 40–60 min marathons (our slot is 12–22 min)
- Sponsor reads longer than 8 seconds (add only after 10K subs)
- Dual-narrator voice switching
- Slow 145 WPM documentary pacing — we're faster (170–185 WPM)

---

## E. Audio stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Primary TTS** | Azure `en-US-GuyNeural` | Brighter, faster — matches Codist/Just Explained pace |
| **Azure style** | `narration-professional` @ **0.88** style degree | Teacher clarity without robotic documentary tone |
| **Rate** | `+2%` | ~175 WPM — faster than recap channels |
| **Pauses** | 80–200ms between concepts | Minimal dead air — encyclopedia flow |
| **Fallback** | Edge TTS (same Guy voice) | When Azure fails |
| **Bg music** | `ambient_cinematic.mp3` @ **8%** volume | Barely audible bed — voice always wins |
| **Ducking** | `duck_under_voice: true` @ 55% | Music never competes with definitions |
| **End card** | Same Guy voice, brief subscribe CTA | 5–8 sec |

**Quota math (shared Azure account, 500k chars/month):**

- ~8,000–12,000 chars per 14–20 min explainer
- **~40–60 explainers/month** if equal split across channels

---

## F. Visual stack (slide mode)

| Element | Spec |
|---------|------|
| Background | `#0f0f1a` dark navy |
| Title font | Bold white, 64px, top-left |
| Diagram panel | Animated illustration per scene (request flows, cache, redirects, errors) |
| Bullets | Gray `#A0A0B0`, 32px, max 3 — fade in after diagram animates |
| Accent bar | Left edge, concept color (blue/green/amber/purple) |
| Scene duration | Matches narration beat (from TTS) |
| Animation | Progressive diagram reveal (arrows draw, labels appear) — Codist-style teaching |
| Transitions | Hard cut between scenes |

---

## G. Metrics targets

| Signal | Healthy (new explainer channel) | Fix if bad |
|--------|--------------------------------|------------|
| CTR | 5–8%+ tech explainer niche | Title + thumbnail alignment |
| Retention @ 30 sec | 40%+ | Cold open / hook package |
| Retention @ 3 min | 25%+ | Concept pacing, section labels |
| Avg view duration | 8–12 min on 16 min video | New concept every 45–90 sec |

---

## H. Pipeline order

1. Topic pick (`topic_queue.json` + `topic_history.json` dedup)
2. Style brief (seed channels / playbook)
3. **Hook package** → locked title, cold open, thumbnail text
4. Full script (cold open verbatim, then concept sections)
5. Visual mapping → slide specs per scene
6. SEO (title **locked** from hook)
7. Thumbnail spec (dark bg + text overlay)
8. Phase 2: Azure TTS → Phase 3: VPS slide render → upload

---

*Last updated: 2026-07-25 — pivot from Retro Movie Archive to teaching explainer format.*
