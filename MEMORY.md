# Memory (Good Practices)

This file records solutions, patterns, and decisions that proved effective so we can reuse them without rediscovery.

## How to Use
- Add a dated entry when you validate a solution in real usage.
- Keep entries short: **Context → Decision → Rationale**.
- Prefer concrete parameter values or code-level rules when possible.

---

## 2026-03-02

### Single source of truth for interview questions
**Context:** Q1–Q7 were duplicated in client and prompt, causing drift.
**Decision:** Parse Q1–Q7 from `prompts/interview_system_prompt.txt` at runtime and expose via `GET /questions`. Client fetches and uses these for TTS and progress. Fail fast if not exactly 7.
**Rationale:** Removes silent divergence between prompt edits and UI.

### Stateless backend discipline
**Context:** Backend cannot track question index in a stateless flow.
**Decision:** Client owns progression; backend does not emit `question_index_next`.
**Rationale:** Keeps the server stateless and avoids false authority.

### Structured evaluation output
**Context:** Parsing scores from free text is brittle.
**Decision:** Use JSON schema output for `/evaluate` with a null‑score fallback.
**Rationale:** Stable parsing; report text remains available even if schema fails.

### Audio-only interview UX
**Context:** On-screen text during interview biases listening.
**Decision:** Keep interview screen audio-first; show text only on report screen. Provide an on-demand audio fallback if TTS fails.
**Rationale:** Preserves authentic listening conditions for B1–B2 students.

### TTS voice selection
**Context:** Voice quality varies across engines.
**Decision:** Prefer `Google US English (en-US)` and avoid fallback voice if preferred voice actually starts speaking.
**Rationale:** Prevents double-voice playback and preserves quality.

### VAD tuning for learners
**Context:** B1–B2 learners pause more; VAD was ending too early.
**Decision:** Two-stage silence window with countdown, minimum speech span, and noise-floor capping to avoid false silence.
**Rationale:** Reduces premature cutoffs while keeping turnaround reasonable.

### Barge-in behavior
**Context:** Natural conversation requires interruption handling.
**Decision:** Add a mic-based barge‑in monitor during Alex’s prompts; cancel TTS when sustained user speech is detected.
**Rationale:** Matches real-world conversational dynamics.
