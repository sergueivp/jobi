# Changelog
All notable changes to this project are documented here.

## 2026-03-02
### Added
- `GET /questions` endpoint to serve Q1–Q7 from the prompt file.
- Structured evaluation output with JSON schema and fallback null scores.
- Client-side barge‑in monitor for interrupting TTS when the student starts speaking.
- Countdown chip and state signalization during VAD silence windows.
- Memory log (`MEMORY.md`) to record validated good practices.

### Changed
- Client question flow: frontend is the single source of progression; backend replies are pruned to avoid next-question leakage.
- TTS selection: prefer Google US English voice and avoid double‑voice fallback when it starts successfully.
- VAD thresholds and noise floor handling to reduce premature stops.
- Interview screen remains audio-first, with only minimal status text.

### Fixed
- Double-question issue by pruning canonical question fragments from `/chat` replies.
- Missing favicon response (now returns 204).
- Cache headers for always-fresh frontend assets.
