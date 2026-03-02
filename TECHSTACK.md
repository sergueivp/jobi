# Tech Stack — NovaTech Interview Simulator
### Hybrid Architecture: Best of Both Proposals

---

## Design Principle

This stack was built by combining two competing proposals. Each had one decisive advantage the other lacked. The hybrid takes both advantages and eliminates both sets of weaknesses.

| Origin | What It Contributes |
|---|---|
| Proposal A (OpenAI / Gradio / HF) | Whisper STT, Hugging Face hosting, API key security |
| Proposal B (Claude / Single HTML) | Working TTS, audio-only UI, CEFR rubric, 3-strike guardrails, session isolation |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      STUDENT BROWSER                         │
│                                                              │
│  ┌──────────────┐    ┌────────────────┐    ┌─────────────┐  │
│  │ Mic capture  │    │  Web Speech    │    │  Interview  │  │
│  │ (MediaRecorder│→  │  Synthesis API │←   │  UI (HTML)  │  │
│  │  getUserMedia)│    │  (TTS / Alex   │    │  Audio-only │  │
│  └──────┬───────┘    │  speaks aloud) │    │  portrait   │  │
│         │            └────────────────┘    │  stage      │  │
│         │                    ↑             └─────────────┘  │
└─────────┼────────────────────┼────────────────────────────┘
          │ audio blob         │ text response
          ↓                    │
┌─────────────────────────────────────────────────────────────┐
│                  FASTAPI BACKEND                              │
│            (Hugging Face Spaces — Python)                    │
│                                                              │
│  POST /transcribe                POST /chat                  │
│  ↓                               ↓                          │
│  OpenAI Whisper API              OpenAI GPT-4o               │
│  (speech → text)                 (Alex Chen persona)        │
│                                                              │
│  POST /evaluate                                              │
│  ↓                                                          │
│  OpenAI GPT-4o                                              │
│  (CEFR C1–C5 rubric evaluation)                             │
│                                                              │
│  API keys stored as HF Spaces secrets — never in browser    │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Frontend — Single HTML File

**Technology:** Vanilla HTML + CSS + JavaScript. No framework. No build step.

**Why vanilla:** The app has exactly three screens (setup, interview, report) and zero shared state between users. A framework adds complexity without benefit. The current app is already under 1,600 lines in a single file — readable, debuggable, deployable.

**Key frontend responsibilities:**
- Capture microphone audio using `MediaRecorder` API
- POST audio blob to `/transcribe` endpoint, receive text
- Maintain conversation history in memory (JavaScript array)
- POST conversation history + new student text to `/chat`, receive Alex's reply as text
- Speak Alex's reply using `window.speechSynthesis` (Web Speech API, built into browser)
- Track 7-question progress, timer, Q dots, state label
- POST full transcript to `/evaluate` at end, render report

**iOS support:** iPhone/iPad users get a textarea with iOS native dictation instead of the MediaRecorder flow. Same backend; different input path.

---

### 2. Speech-to-Text — OpenAI Whisper

**API:** `POST https://api.openai.com/v1/audio/transcriptions`
**Model:** `whisper-1`
**Format:** Audio sent as `.webm` blob (MediaRecorder default) or `.mp3`

**Why Whisper over browser Web Speech API:**

| | Browser Web Speech API | OpenAI Whisper |
|---|---|---|
| Chrome desktop | ✅ Works | ✅ Works |
| Chrome Android | ✅ Works | ✅ Works |
| Safari iOS | ⚠️ Unreliable (continuous mode broken) | ✅ Works |
| Firefox | ❌ Not supported | ✅ Works |
| Accented English | ⚠️ Degrades significantly | ✅ Handles well |
| Offline | ⚠️ Needs Google servers anyway | ❌ Requires API |
| Cost | Free | ~€0.006/min |

For a class of non-native English speakers, accented speech handling is not optional. Whisper was trained on multilingual audio including accented English and consistently outperforms browser STT on this use case.

**Implementation note:** Audio is captured in 2–3 second chunks after the student stops speaking (silence detection via Web Audio API volume threshold). Each chunk is sent as a separate request and transcriptions are concatenated. This avoids file size limits and gives interim "typing" feedback.

---

### 3. Conversation Intelligence — OpenAI GPT-4o

**API:** `POST https://api.openai.com/v1/chat/completions`
**Model:** `gpt-4o` (or `gpt-4o-mini` for cost reduction — see Cost section)

**Why GPT-4o:**
- On-model with Whisper (same vendor, same API key, single billing account)
- Instruction-following quality sufficient for the persona + guardrail system
- Context window large enough to hold a full 12-minute interview transcript

**What it handles:**
- Alex Chen persona maintenance across 7 questions
- Natural follow-up probing when answers are too short
- 3-strike off-topic guardrail system (see Guardrails in README)
- Closing exchange and `[INTERVIEW_COMPLETE]` signal

**Alternative:** Claude 3.5 Sonnet (Anthropic) is equally capable and can be substituted. The guardrail system and persona prompt were developed and tested on Claude. If using Claude: replace `/chat` endpoint logic with Anthropic API call; all other components unchanged.

---

### 4. Text-to-Speech — Browser Web Speech Synthesis

**API:** `window.speechSynthesis.speak()` — built into every modern browser.

**Why browser TTS instead of OpenAI TTS:**

| | Browser Speech Synthesis | OpenAI TTS API |
|---|---|---|
| Cost | Free | ~€0.015 per 1K characters |
| Latency | Instant (local) | 200–800ms round trip |
| Voice quality | Varies by OS/browser | Consistently natural |
| Cross-platform | ✅ All modern browsers | ✅ All modern browsers |

For a 12-minute interview, OpenAI TTS would cost approximately €0.08–0.12 per student — tolerable. But browser TTS is instant, free, and removes an extra API call from the critical path. Alex's voice is slightly more robotic than OpenAI TTS, but for an EFL assessment context, this is acceptable and may even benefit comprehension (clearer articulation).

**Voice selection:** On load, the app selects the best available English voice using `speechSynthesis.getVoices()`. Preference order: `en-GB` → `en-US` → any `en-*`. Rate is set to 0.88 for slightly slower delivery (optimised for EFL listeners).

---

### 5. Evaluation Engine — GPT-4o with CEFR Rubric

**API:** Same OpenAI completions endpoint; separate call after interview ends.
**Input:** Full timestamped transcript of the interview.
**Output:** Structured plain-text report (see format below).

**Rubric:**

| Code | Criterion | Scale |
|---|---|---|
| C1 | Task Completion | 1–4 |
| C2 | Fluency & Coherence | 1–4 |
| C3 | Lexical Resource | 1–4 |
| C4 | Grammatical Range & Accuracy | 1–4 |
| C5 | Professional Register | 1–4 |

Total: 20 points. CEFR mapping: 17–20 = B2+ / 13–16 = B2 / 9–12 = B1.2 / ≤8 = B1.1 or below.

The evaluation prompt instructs the model to: score each criterion with a justification of 1–2 sentences, flag specific quoted utterances from the transcript (both strengths and errors), provide corrected versions of errors, and note the number of off-topic attempts (feeds C5).

---

### 6. Hosting — Hugging Face Spaces

**Type:** Gradio app (Python backend only; frontend is served as static file)  
**Plan:** Free tier (permanent HTTPS URL, no sleep on free plan for apps with consistent traffic)  
**URL pattern:** `https://huggingface.co/spaces/[username]/novatech-interview`

**Why Hugging Face Spaces:**
- Free permanent HTTPS URL — shareable with students immediately
- Secrets management: `OPENAI_API_KEY` stored as HF Space secret, never sent to browser
- No DevOps: deploy by pushing files to a GitHub repo linked to the Space
- Embeddable: the URL can be dropped directly into PoliFormat (Moodle) or any LMS via iframe
- Zero sleep: unlike Render free tier, HF Spaces with a public URL stays live

**Deployment model:**
```
GitHub repo
  └── app.py           ← FastAPI backend (3 routes: /transcribe, /chat, /evaluate)
  └── index.html       ← Frontend (full audio-only interview app)
  └── requirements.txt ← fastapi, uvicorn, openai, python-multipart
  └── README.md

→ Push to GitHub → HF Space rebuilds automatically → Live in 90 seconds
```

**API key flow:**
```
Teacher sets OPENAI_API_KEY in HF Space Secrets (one time, never again)
↓
Backend uses os.environ["OPENAI_API_KEY"] for all API calls
↓
Browser never sees the key — only sees text responses from /transcribe and /chat
```

---

### 7. Backend — FastAPI (Python)

**Why FastAPI over Flask/Django:** Async support by default (important for concurrent Whisper + GPT calls from 20 students), automatic OpenAPI docs, minimal boilerplate.

**Routes:**

```python
POST /transcribe
  → accepts: audio/webm blob
  → calls: openai.Audio.transcriptions.create(model="whisper-1", file=audio)
  → returns: { "text": "I worked on a machine learning pipeline..." }

POST /chat
  → accepts: { history: [...], student_name, role_name, question_count, strike_count }
  → calls: openai.chat.completions.create(model="gpt-4o", messages=[...])
  → returns: { "reply": "That's interesting. Tell me more about...", "complete": false }

POST /evaluate
  → accepts: { transcript: [...], student_name, role_name, off_topic_strikes }
  → calls: openai.chat.completions.create(model="gpt-4o", messages=[eval_prompt])
  → returns: { "report": "═══ INTERVIEW EVALUATION REPORT ═══\n..." }
```

**Session isolation:** Each browser tab is its own session. State (conversation history, question count, strike count) lives entirely in the browser's JavaScript memory. The backend is stateless. 20 students running simultaneously = 20 parallel stateless requests. No shared state bugs.

---

## Cost Model

| Component | Unit cost | Per interview (12 min) | Per class (20 students) |
|---|---|---|---|
| Whisper STT | $0.006/min | ~$0.07 | ~$1.40 |
| GPT-4o (conversation) | $2.50/1M input + $10/1M output tokens | ~$0.04 | ~$0.80 |
| GPT-4o (evaluation) | same | ~$0.02 | ~$0.40 |
| Browser TTS | Free | $0 | $0 |
| HF Spaces | Free | $0 | $0 |
| **Total** | | **~€0.12** | **~€2.50** |

**Using `gpt-4o-mini` instead of `gpt-4o`:** Reduces LLM cost by ~85%. Quality is slightly lower for the evaluation rubric but acceptable for classroom use. Recommended for budget-conscious deployment.

---

## What Was Deliberately Excluded

| Rejected option | Reason |
|---|---|
| Gradio UI framework | Browser mic through Gradio on HF Spaces is notoriously unreliable on mobile. Replaced with direct MediaRecorder → FastAPI. |
| Cloudflare Worker for API proxy | Adds a second system to configure. HF Spaces secrets solve the same problem with zero extra setup. |
| Shared global state (`InterviewState()` singleton) | Critical concurrency bug — all students overwrite each other. Solved by keeping all state in browser. |
| Text chat bubbles during interview | Turns a listening/speaking assessment into a reading task. Removed entirely. |
| localStorage / sessionStorage | Not needed — session state lives in JS variables per tab. |
| Database | No persistence needed. Assessment is synchronous and self-contained per session. |

---

## Browser Compatibility

| Browser | STT | TTS | Overall |
|---|---|---|---|
| Chrome desktop | ✅ | ✅ | ✅ Full support |
| Chrome Android | ✅ | ✅ | ✅ Full support |
| Safari desktop (macOS) | ✅ | ✅ | ✅ Full support |
| Safari iOS (iPhone/iPad) | ⚠️ Fallback textarea | ✅ | ✅ With dictation fallback |
| Firefox | ⚠️ Fallback textarea | ✅ | ✅ With dictation fallback |
| Edge | ✅ | ✅ | ✅ Full support |

---

## Repository Structure

```
novatech-interview/
├── app.py                  ← FastAPI backend
├── index.html              ← Full frontend (audio-only interview app)
├── requirements.txt        ← fastapi uvicorn openai python-multipart
├── README.md               ← Concept documentation
├── TECHSTACK.md            ← This file
├── PERSONA.md              ← Alex Chen character document
├── PROMPT.md               ← Full system prompt with guardrails
└── .env.example            ← Template for local development
```

---

## Local Development

```bash
# Clone and install
git clone https://github.com/[you]/novatech-interview
cd novatech-interview
pip install -r requirements.txt

# Set key
export OPENAI_API_KEY=sk-...

# Run
uvicorn app:app --reload --port 8000

# Open browser
open http://localhost:8000
```

For local dev, the frontend (`index.html`) is served as a static file by FastAPI. In production (HF Spaces), the same index.html is served automatically.
