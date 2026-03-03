---
title: NovaTech Interview Simulator
sdk: docker
app_port: 7860
---

# NovaTech Interview Simulator
### An AI-Powered Spoken English Assessment Tool for University EFL Students

---

## What This Is

NovaTech Interview Simulator is a voice-only web application that places a university student inside a realistic job interview with an AI-powered HR manager named Alex Chen. The student speaks. Alex speaks back. No reading. No typing. No safety net.

The application is designed for **B1.2–B2.1 level EFL students** (4th year university) as a high-stakes speaking assessment tool that generates a detailed, CEFR-mapped evaluation report automatically at the end of each session.

It is not a chatbot. It is not a language tutor. It is a pressure-tested speaking environment that reveals what a student can actually do with English when the stakes feel real.

---

## The Problem It Solves

Traditional EFL speaking assessments at university level suffer from three structural problems:

**1. Artificiality.** Role plays between students, or between student and teacher, carry no psychological weight. Everyone knows it is a game. Students perform rather than communicate.

**2. Scale.** A teacher with 20+ students cannot conduct individual 12-minute spoken assessments in a single lesson without either rushing the assessment or sacrificing the rest of the class.

**3. Inconsistency.** When a teacher conducts 20 interviews manually, each one is slightly different. Questions vary, probing varies, assessment criteria are applied unevenly across a long, tiring session.

NovaTech Interview Simulator solves all three simultaneously. Every student gets the same interviewer, the same seven questions in the same order, the same follow-up logic, the same evaluation rubric — applied independently, in parallel, inside a 120-minute class.

---

## How It Works

### The Student Experience

A student opens the app in a browser. They enter their name and the role they are applying for (e.g. *Junior Software Developer*, *UX Designer*, *Data Analyst*). They press Begin.

Alex Chen — Senior HR Manager at NovaTech Solutions — greets them by name and begins the interview. Alex speaks through the browser's audio. The student listens. When Alex finishes speaking, a visual signal indicates it is the student's turn. The student speaks their answer. Alex listens (via OpenAI Whisper speech-to-text), processes the answer, and responds.

This continues for 7 structured questions over approximately 10–12 minutes.

The student sees almost nothing on screen during the interview. There is no transcript to read. There are no chat bubbles. There is Alex's portrait, an animated waveform showing who is speaking, seven progress dots, and a single status line. The interface exists only to orient — not to assist.

### The Interview Structure

Alex asks seven questions in a fixed order, each targeting a distinct communicative function:

| Q | Function | Focus |
|---|---|---|
| 1 | Warm-up | Self-introduction and motivation |
| 2 | Company knowledge | Research, critical thinking |
| 3 | Task under pressure | STAR-structured technical narrative |
| 4 | Teamwork | Conflict navigation, communication |
| 5 | Problem-solving | Diagnosis, process, outcome |
| 6 | Strengths | Self-awareness, evidence |
| 7 | Development areas | Growth mindset, concrete action |

Alex probes short answers with natural follow-ups. He does not read from a script out loud. He does not number questions. He sounds like a person.

### The Assessment

When the interview ends — either after the closing exchange or after the teacher clicks End — the app sends the full transcript to a language model for evaluation. The report generates in 15–30 seconds.

The report scores the student across five CEFR-mapped criteria:

| Code | Criterion | What It Measures |
|---|---|---|
| C1 | Task Completion | Did the student answer the questions fully? Did they develop their answers? |
| C2 | Fluency & Coherence | Was speech natural? Was there effective use of discourse markers? |
| C3 | Lexical Resource | Was vocabulary varied, precise, and appropriate to professional register? |
| C4 | Grammatical Range & Accuracy | Was grammar used accurately and with appropriate complexity? |
| C5 | Professional Register | Did the student maintain appropriate formal register throughout? |

Each criterion is scored 0–4. Total: 20 points. A score of 0 is valid (no assessable performance). The report maps totals 1–20 to CEFR bands and includes specific language samples from what the student said — both strengths and errors — with corrected versions.

---

## The Guardrail System

Alex Chen is an AI operating under strict role constraints. When a student attempts to use the interview session for something outside the interview — asking the AI to write code, generate essays, play games, or any other off-topic request — Alex responds as a real interviewer would: not with a system error, but with an escalating human register shift.

**Strike 1 — Warm redirect.** Alex assumes confusion or nervousness and gently steers back to the interview. Tone unchanged. No announcement.

**Strike 2 — Register cools.** Warmth drops. Sentences shorten. The message is professional but unmistakably direct: the time here is for the interview.

**Strike 3 — Professional closure.** Alex ends the interview with polished formal courtesy. The session closes. The report flags the off-topic attempts under C5 (Professional Register).

The number of strikes is never announced. The escalation is felt, not explained — exactly as it would be in a real interview room.

---

## Why Audio-Only

The decision to remove all text from the interview screen is pedagogically deliberate.

When text is visible, students read. When students read, the assessment measures reading comprehension and processing speed — not spoken communication. The moment a student can read Alex's words back off the screen, the listening component of the task collapses.

In a real job interview, the candidate does not receive a transcript. They listen. They process. They respond. NovaTech Interview Simulator replicates that condition exactly.

Text returns only on the report screen — as assessment output, not as interview input.

---

## Who Uses It and How

**The teacher** deploys the app once (one URL, shared via the course platform) and sets up their API key once in the configuration. Students access the URL during class. The teacher monitors the room while 20 students simultaneously conduct independent interviews in pairs of earphones. At the end of class, each student has a printed or emailed report with their score and specific language feedback.

**The student** needs only a browser (Chrome on desktop or Android for best voice support; iPhone with iOS dictation fallback) and earphones. No installation. No account. No app download. They enter their name, press Begin, and the interview starts.

---

## What This Is Not

- It is not a conversation partner for open-ended practice. It follows a fixed structure.
- It is not a replacement for teacher feedback. It is a first-pass spoken assessment that surfaces language data the teacher can then use in follow-up sessions.
- It is not infinitely flexible. The seven questions are fixed per session (though the role is adjustable, which changes how Alex interprets answers).
- It is not a tool for students to use unsupervised for repeated practice without pedagogical framing. The interview is assessment-grade — it should carry stakes to work.

---

## Technical Summary

- **Single browser-based application** — no installation, no mobile app, no account creation
- **Speech-to-text** — OpenAI Whisper via API (state of the art; language-agnostic; handles accented English well)
- **Conversation intelligence** — GPT-4o or Claude 3.5 Sonnet (configurable)
- **Text-to-speech** — Browser Web Speech API (no additional API cost; cross-platform)
- **Hosting** — Hugging Face Spaces (free tier; permanent HTTPS URL; embeddable in any LMS)
- **API key security** — key stored as HF Spaces secret; never exposed in browser
- **Per-session cost** — approximately €0.03–0.08 per 12-minute interview (Whisper + LLM combined)
- **Concurrent users** — each browser tab is a fully independent session; 20 students simultaneously presents no state-sharing issues

---

## Context: EFL Lesson 9

This application was originally built for use in Lesson 9 of a B1.2–B2.1 university EFL course structured around professional English communication. Lesson 9 is the spoken assessment lesson. The lesson arc:

1. Pre-lesson: Students review STAR structure and professional register (from previous lessons)
2. In-class (120 min): Students conduct the AI interview individually with earphones
3. Post-interview: Students receive their report. Teacher uses aggregated language samples from the class for a 20-minute whole-group error correction and register workshop
4. Assessment output: Report scores feed into the summative oral grade for the course unit

---

## Licence & Attribution

Built by [your name / institution]. Powered by OpenAI Whisper, OpenAI GPT-4o (or Anthropic Claude), and Hugging Face Spaces. Designed for educational use. Not for commercial distribution.

---

## Developer Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# set OPENAI_API_KEY in your shell or .env loader
uvicorn app:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

## API Endpoints

- `GET /questions` → returns parsed Q1–Q7 from `prompts/interview_system_prompt.txt`
- `GET /attempts/status` → returns attempt usage (max 3 attempts per student/role)
- `POST /transcribe` → Whisper transcription for recorded audio
- `POST /chat` → Alex reply + `is_probe` + `[INTERVIEW_COMPLETE]` detection
- `POST /evaluate` → CEFR report + structured scores + signed report package (+ final-attempt teacher email send when configured)
- `POST /verify-report` → verifies server signature for submitted report JSON
- `GET /email/status` → SMTP configuration flags + last email delivery status/error

## Signed Report Verification

Each generated report now includes a `report_package` with `payload` + `signature`.
For submission integrity (e.g., PoliformaT), ask students to upload that JSON package.

Teacher verification:

```bash
curl -X POST https://<your-space>.hf.space/verify-report \
  -H "Content-Type: application/json" \
  -d @student-report-package.json
```

The endpoint returns `{"valid": true/false, ...}`.

## Final Attempt Email Delivery (Teacher Copy)

On attempt `3/3` (final graded attempt), the server can automatically email the teacher with:
- score summary
- report excerpt
- attached signed JSON report package

Set these environment variables (HF Space Secrets):
- `TEACHER_EMAIL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_SECURITY` (`ssl`, `starttls`, or `none`)

Quick diagnostics:

```bash
curl https://<your-space>.hf.space/email/status \
  -H "X-Access-Pin: <PIN-if-enabled>"
```

Check:
- `configured: true`
- `last_status: sent` after a final attempt
- if `last_status: failed`, inspect `last_error` for the SMTP failure reason

Optional hardening:
- `LOCK_BROWSER_AFTER_FINAL=true` (default): after attempt 3, this browser session is locked from calling interview API endpoints.
- `ATTEMPT_STORE_PATH=.attempts_store.json`: server-side persistent attempt counter store path.

## Test Suite

```bash
source .venv/bin/activate
pytest -q
```

Current baseline: `27 passed`.

---

## Project Maintenance

To keep decisions and changes serialized and easy to reuse:

- **Rubric source:** [`RUBRIC.md`](./RUBRIC.md)  
  Canonical assessment rubric (v2) used to align evaluation logic and prompt behavior.

- **Good practices log:** [`MEMORY.md`](./MEMORY.md)  
  Records validated solutions and architectural choices so we don’t re‑solve the same problems.

- **Change log:** [`CHANGELOG.md`](./CHANGELOG.md)  
  A dated record of changes across backend, frontend, and prompts.
