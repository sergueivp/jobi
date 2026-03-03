# Changelog
All notable changes to this project are documented here.

## 2026-03-03
### Added
- 3-attempt assessment flow with server-tracked status endpoint: `GET /attempts/status`.
- Final-attempt warning before interview start (attempt 3/3), plus lockout after attempts are exhausted.
- Signed report package on evaluation responses and a verification endpoint: `POST /verify-report`.
- Report download action in UI for student submission (`Download Signed Report` JSON package).
- Canonical rubric file `RUBRIC.md` (v2).
- Optional final-attempt teacher email delivery (SMTP) with signed JSON attachment.

### Changed
- Evaluation output now includes attempt metadata and signed package payload alongside report text/scores.
- Evaluation prompt now requests richer evidence:
  - multiple strong samples when available
  - weak samples with corrected versions
  - targeted improved short replies by question
  - explicit language + concept improvement plan
- Setup UX now explicitly states the 3-attempt policy and shows a live attempt counter.
- Report actions now prioritize `Download Signed Report`; copy/print are marked optional.
- `New Interview` button now warns before the final attempt and disables after final attempt completion.
- Rubric scale updated from `1-4` to `0-4` (explicit zero-performance handling).
- Backend scoring now enforces:
  - `answered_questions = 0` -> all criteria `0`, total `0`, CEFR `Not assessable`
  - strike-based C5 caps and C1=0 at strike 3 (rubric v2 alignment)
- Server-side hard lock now blocks interview API-cost endpoints after final attempt (`SESSION_LOCKED`), reducing API credit leakage.
- `/chat` and `/transcribe` now enforce attempt availability before OpenAI calls.

### Fixed
- Resolved forward-reference typing issue in `EvaluateResponse` for Python 3.13.
- Replaced deprecated `datetime.utcnow()` usage with timezone-aware UTC timestamps.

## 2026-03-02
### Added
- `GET /questions` endpoint to serve Q1–Q7 from the prompt file.
- Structured evaluation output with JSON schema and fallback null scores.
- Client-side barge‑in monitor for interrupting TTS when the student starts speaking.
- Countdown chip and state signalization during VAD silence windows.
- Memory log (`MEMORY.md`) to record validated good practices.
- Docker deployment files for Hugging Face Spaces (`Dockerfile`, `.dockerignore`).
- Microphone check panel on the setup screen (level meter + sample recording).

### Changed
- Client question flow: frontend is the single source of progression; backend replies are pruned to avoid next-question leakage.
- TTS selection: prefer Google US English voice and avoid double‑voice fallback when it starts successfully.
- VAD thresholds and noise floor handling to reduce premature stops.
- Interview screen remains audio-first, with only minimal status text.

### Fixed
- Double-question issue by pruning canonical question fragments from `/chat` replies.
- Missing favicon response (now returns 204).
- Cache headers for always-fresh frontend assets.
