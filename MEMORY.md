# Memory (Good Practices)

This file is **for the assistant’s use**. It captures validated solutions and the rules for when to apply them again. I will consult this before debugging or making logic changes.

---

## Debug Checklist (always run before changing logic)
1. Confirm **current state** with `?debug=1` and capture `db/noise/startThr/contThr/accepted/streak` values.
2. Verify **turn ownership**: if UI says “Alex speaking”, recording must be `false`.
3. Validate **TTS start**: ensure preferred voice starts once; no fallback double‑voice.
4. Confirm **VAD timeline**: min speech span, silence soft/hard timers, and countdown are visible.
5. Only then adjust thresholds or flow.

---

## Known Pitfalls and Fixes
- **Recording during TTS** → cancel mic + stop VAD before speaking; never start recording while `speaking=true`.
- **Double voice playback** → only fall back if preferred voice never started (`onstart` not fired).
- **Question duplication** → prune canonical questions from `/chat` replies; frontend controls question flow.
- **Score inflation on short interviews** → apply caps based on answered questions.

---

## Validated Patterns

### 2026-03-02 — Single source of truth for questions
**Context:** Q1–Q7 duplicated in prompt and client, causing drift.
**Decision:** Parse Q1–Q7 from `prompts/interview_system_prompt.txt` and serve via `GET /questions`.
**Evidence:** Prevented mismatched TTS vs. interviewer intent when prompt edits changed.
**Reuse rule:** If any content is editable by teachers, UI must fetch it from the same source.

### 2026-03-02 — Stateless backend discipline
**Context:** Backend can’t track question index.
**Decision:** Client owns progression; backend does not emit `question_index_next`.
**Evidence:** Removed inconsistent server‑side index guesses.
**Reuse rule:** Don’t add server state unless we store sessions.

### 2026-03-02 — Structured evaluation output
**Context:** Regex parsing of scores is brittle.
**Decision:** Use JSON schema outputs; fallback to text with null scores.
**Evidence:** Eliminated parse failures when model formatting drifted.
**Reuse rule:** Always request structured output for scoring.

### 2026-03-02 — Audio‑first interview UX
**Context:** Visible transcripts bias listening.
**Decision:** Keep interview screen text‑minimal; only show report text later.
**Evidence:** Preserved listening‑speaking conditions.
**Reuse rule:** No live transcripts on the interview screen.

### 2026-03-02 — Voice selection stability
**Context:** Fallback voice caused double playback.
**Decision:** Only fall back if preferred voice never started.
**Evidence:** Removed “Google voice + robotic voice” duplication.
**Reuse rule:** Use `onstart` to detect true playback before fallback.

### 2026-03-02 — VAD for learner pauses
**Context:** Learners pause; VAD cut off early.
**Decision:** Two‑stage silence window with countdown; noise‑floor capping.
**Evidence:** Reduced false cutoffs while keeping turnaround reasonable.
**Reuse rule:** Do not shorten silence windows without field tests.

### 2026-03-02 — Barge‑in during prompts
**Context:** Conversational feel requires interruption handling.
**Decision:** Monitor mic during TTS and cancel when sustained speech detected.
**Evidence:** Matches real turn‑taking behavior.
**Reuse rule:** Barge‑in only during prompts, not while processing.
