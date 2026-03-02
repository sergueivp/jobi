from __future__ import annotations

import io
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("novatech-interview")

MAX_HISTORY_TURNS = 60
MAX_AUDIO_BYTES = 10 * 1024 * 1024
DEFAULT_CHAT_MODEL = os.getenv("MODEL_CHAT", "gpt-4o")
DEFAULT_EVAL_MODEL = os.getenv("MODEL_EVAL", "gpt-4o")
DEFAULT_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

PROBE_PHRASES = (
    "tell me more",
    "could you",
    "can you",
    "elaborate",
    "give me an example",
    "walk me through",
    "what specifically",
    "what was",
    "how did",
)

ECHO_OPENERS = (
    "thank you for sharing",
    "i appreciate your",
    "that's useful context",
    "that's helpful context",
)


@dataclass(frozen=True)
class Paths:
    base_dir: Path
    prompts_dir: Path
    interview_prompt: Path
    evaluation_prompt: Path
    index_html: Path


BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", BASE_DIR / "prompts"))
PATHS = Paths(
    base_dir=BASE_DIR,
    prompts_dir=PROMPTS_DIR,
    interview_prompt=PROMPTS_DIR / "interview_system_prompt.txt",
    evaluation_prompt=PROMPTS_DIR / "evaluation_prompt.txt",
    index_html=BASE_DIR / "index.html",
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# Load local .env so running uvicorn directly picks up keys.
load_env_file(BASE_DIR / ".env")


class HistoryTurn(BaseModel):
    role: Literal["assistant", "user"]
    content: str = Field(min_length=1)
    timestamp: str | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    student_name: str = Field(min_length=1, max_length=120)
    role_name: str = Field(min_length=1, max_length=160)
    question_index: int = Field(ge=1, le=7)
    phase: Literal["main_answer", "probe_answer", "closing_question"]
    probe_used_current_question: bool
    strike_count: int = Field(ge=0, le=3)
    history: list[HistoryTurn] = Field(default_factory=list)
    student_text: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    is_probe: bool
    contains_complete_tag: bool


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    student_name: str = Field(min_length=1, max_length=120)
    role_name: str = Field(min_length=1, max_length=160)
    transcript: list[HistoryTurn] = Field(default_factory=list)
    duration_seconds: int = Field(ge=0, le=7200)
    off_topic_strikes: int = Field(ge=0, le=3)
    answered_questions: int = Field(default=0, ge=0, le=7)
    total_questions: int = Field(default=7, ge=1, le=7)
    interview_completed: bool = False


class ScorePayload(BaseModel):
    c1: int | None = Field(default=None, ge=1, le=4)
    c2: int | None = Field(default=None, ge=1, le=4)
    c3: int | None = Field(default=None, ge=1, le=4)
    c4: int | None = Field(default=None, ge=1, le=4)
    c5: int | None = Field(default=None, ge=1, le=4)
    total: int | None = Field(default=None, ge=0, le=20)
    percent: int | None = Field(default=None, ge=0, le=100)
    grade: str | None = None
    cefr: str | None = None


class EvaluateResponse(BaseModel):
    report_text: str
    scores: ScorePayload


class QuestionResponse(BaseModel):
    questions: list[str]


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Prompt file not found: {path}") from exc


def inject_vars(template: str, **values: str) -> str:
    result = template
    for key, value in values.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def parse_questions_from_prompt(prompt_text: str) -> list[str]:
    heading_re = re.compile(r"^\s*#{1,6}\s*Q([1-7])\b")
    quoted_re = re.compile(r'^\s*"(.+?)"\s*$')

    lines = prompt_text.splitlines()
    headings: list[tuple[int, int]] = []

    for idx, line in enumerate(lines):
        match = heading_re.match(line)
        if match:
            headings.append((int(match.group(1)), idx))

    if len(headings) != 7:
        raise ValueError(f"Expected 7 question headings, found {len(headings)}")

    for expected, (value, _) in enumerate(headings, start=1):
        if value != expected:
            raise ValueError("Question headings must be sequential from Q1 to Q7")

    questions: list[str] = []
    for index, (_, start_line) in enumerate(headings):
        end_line = headings[index + 1][1] if index + 1 < len(headings) else len(lines)
        question: str | None = None
        for cursor in range(start_line + 1, end_line):
            quote_match = quoted_re.match(lines[cursor])
            if quote_match:
                candidate = quote_match.group(1).strip()
                if candidate:
                    question = candidate
                    break
        if not question:
            raise ValueError(f"Could not extract quoted question after Q{index + 1}")
        questions.append(question)

    if len(questions) != 7:
        raise ValueError("Parsed questions count is not 7")

    return questions


def detect_probe(reply_text: str) -> bool:
    normalized = reply_text.strip().lower()
    if not normalized.endswith("?"):
        return False
    return any(phrase in normalized for phrase in PROBE_PHRASES)


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def reply_contains_canonical_question(reply: str, question: str) -> bool:
    reply_norm = normalize_for_match(reply)
    question_norm = normalize_for_match(question)
    if not reply_norm or not question_norm:
        return False
    if question_norm in reply_norm:
        return True
    # Fall back to first phrase match for mild paraphrases.
    prefix = " ".join(question_norm.split()[:8]).strip()
    return bool(prefix and prefix in reply_norm)


def _normalize_text_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def prune_canonical_questions(reply: str, questions: list[str]) -> str:
    # Remove any fragment that matches a canonical interview question or ends with a question mark.
    fragments = re.split(r"(?<=[.!?])\s+", reply.strip())
    kept: list[str] = []
    normalized_questions = [_normalize_text_for_match(q) for q in questions if q.strip()]
    normalized_prefixes = [
        " ".join(q.split()[:8]).strip() for q in normalized_questions if q.split()
    ]

    for frag in fragments:
        if not frag:
            continue
        normalized_frag = _normalize_text_for_match(frag)
        contains_canonical = any(
            (q and q in normalized_frag) or (p and p in normalized_frag)
            for q, p in zip(normalized_questions, normalized_prefixes)
        )
        if frag.strip().endswith("?") or contains_canonical:
            continue
        kept.append(frag)

    if kept:
        return " ".join(kept).strip()
    return "Right."


def prune_questions_from_reply(reply: str) -> str:
    # Keep only non-question sentences to avoid double-question handoff in deterministic client flow.
    fragments = re.split(r"(?<=[.!?])\s+", reply.strip())
    kept = [frag for frag in fragments if frag and not frag.strip().endswith("?")]
    if kept:
        return " ".join(kept).strip()
    return "Right."


def de_echo_opening(reply: str) -> str:
    lower = reply.strip().lower()
    if any(lower.startswith(prefix) for prefix in ECHO_OPENERS):
        fragments = re.split(r"(?<=[.!?])\s+", reply.strip())
        if fragments:
            first = fragments[0]
            if len(fragments) > 1:
                return f"Right. {' '.join(fragments[1:]).strip()}".strip()
            return "Right."
    return reply.strip()


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    return f"{minutes:02d}:{sec:02d}"


def format_transcript(turns: list[HistoryTurn], student_name: str) -> str:
    lines: list[str] = []
    speaker_name = student_name.upper()
    for turn in turns:
        speaker = "ALEX CHEN" if turn.role == "assistant" else speaker_name
        stamp = turn.timestamp or "--:--:--"
        lines.append(f"[{stamp}] {speaker}: {turn.content}")
    return "\n".join(lines)


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "OPENAI_KEY_MISSING",
                "message": "OPENAI_API_KEY is not configured on the server.",
                "retryable": False,
            },
        )
    return OpenAI(api_key=api_key)


def null_scores() -> ScorePayload:
    return ScorePayload()


def grade_from_total(total: int) -> tuple[str, str]:
    if total >= 17:
        return ("A", "B2+")
    if total >= 13:
        return ("B", "B2.1")
    if total >= 9:
        return ("C", "B1.2")
    if total >= 5:
        return ("D", "B1.1")
    return ("F", "Below B1.1")


def all_criteria_present(scores: ScorePayload) -> bool:
    fields = (scores.c1, scores.c2, scores.c3, scores.c4, scores.c5)
    return all(value is not None for value in fields)


def cap_total(scores: list[int], total_cap: int) -> list[int]:
    # Reduce less reliable criteria first until total is within cap.
    order = [4, 3, 2, 1, 0]  # c5 -> c1
    while sum(scores) > total_cap:
        changed = False
        for idx in order:
            if scores[idx] > 1 and sum(scores) > total_cap:
                scores[idx] -= 1
                changed = True
        if not changed:
            break
    return scores


def apply_incomplete_interview_caps(
    scores: ScorePayload,
    answered_questions: int,
    total_questions: int,
    interview_completed: bool,
) -> tuple[ScorePayload, bool]:
    if not all_criteria_present(scores):
        return scores, False

    if interview_completed and answered_questions >= total_questions:
        criteria = [scores.c1, scores.c2, scores.c3, scores.c4, scores.c5]  # type: ignore[list-item]
        total = sum(criteria)
        percent = int(round((total / 20) * 100))
        grade, cefr = grade_from_total(total)
        return (
            ScorePayload(
                c1=criteria[0],
                c2=criteria[1],
                c3=criteria[2],
                c4=criteria[3],
                c5=criteria[4],
                total=total,
                percent=percent,
                grade=grade,
                cefr=cefr,
            ),
            False,
        )

    criteria = [scores.c1, scores.c2, scores.c3, scores.c4, scores.c5]  # type: ignore[list-item]
    caps_applied = True

    if answered_questions <= 1:
        criteria[0] = min(criteria[0], 1)
        criteria[1] = min(criteria[1], 2)
        criteria[2] = min(criteria[2], 2)
        criteria[3] = min(criteria[3], 2)
        criteria[4] = min(criteria[4], 3)
        total_cap = 8
    elif answered_questions <= 3:
        criteria[0] = min(criteria[0], 2)
        criteria[1] = min(criteria[1], 3)
        criteria[2] = min(criteria[2], 3)
        criteria[3] = min(criteria[3], 3)
        criteria[4] = min(criteria[4], 3)
        total_cap = 12
    elif answered_questions <= 5:
        criteria[0] = min(criteria[0], 2)
        total_cap = 16
    else:
        criteria[0] = min(criteria[0], 3)
        total_cap = 18

    criteria = cap_total(criteria, total_cap)
    total = sum(criteria)
    percent = int(round((total / 20) * 100))
    grade, cefr = grade_from_total(total)

    adjusted = ScorePayload(
        c1=criteria[0],
        c2=criteria[1],
        c3=criteria[2],
        c4=criteria[3],
        c5=criteria[4],
        total=total,
        percent=percent,
        grade=grade,
        cefr=cefr,
    )
    return adjusted, caps_applied


def create_app() -> FastAPI:
    app = FastAPI(title="NovaTech Interview Simulator", version="1.0.0")
    questions_cache: list[str] = []

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    app.mount("/static", StaticFiles(directory=PATHS.base_dir / "static"), name="static")

    @app.on_event("startup")
    async def startup_validation() -> None:
        interview_text = _load_text(PATHS.interview_prompt)
        parsed_questions = parse_questions_from_prompt(interview_text)
        questions_cache.clear()
        questions_cache.extend(parsed_questions)
        _ = _load_text(PATHS.evaluation_prompt)
        logger.info("Prompt validation completed.")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(PATHS.index_html)

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/questions", response_model=QuestionResponse)
    async def get_questions() -> QuestionResponse:
        try:
            if questions_cache:
                questions = list(questions_cache)
            else:
                prompt_text = _load_text(PATHS.interview_prompt)
                questions = parse_questions_from_prompt(prompt_text)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "QUESTION_PARSE_ERROR",
                    "message": str(exc),
                    "retryable": False,
                },
            ) from exc
        return QuestionResponse(questions=questions)

    @app.post("/transcribe")
    async def transcribe_audio(
        audio: UploadFile = File(...),
        duration_ms: int = Form(default=0),
    ) -> dict[str, str | int]:
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(
                status_code=415,
                detail={
                    "code": "UNSUPPORTED_AUDIO_TYPE",
                    "message": "Audio file content-type is required.",
                    "retryable": False,
                },
            )

        raw = await audio.read()
        if not raw:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "EMPTY_AUDIO",
                    "message": "Audio payload is empty.",
                    "retryable": False,
                },
            )

        if len(raw) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "AUDIO_TOO_LARGE",
                    "message": "Audio payload exceeds 10MB limit.",
                    "retryable": False,
                },
            )

        client = get_openai_client()
        audio_buffer = io.BytesIO(raw)
        audio_buffer.name = audio.filename or "response.webm"

        try:
            transcription = client.audio.transcriptions.create(
                model=DEFAULT_WHISPER_MODEL,
                file=audio_buffer,
                response_format="text",
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "TRANSCRIPTION_FAILED",
                    "message": f"Transcription service failed: {exc}",
                    "retryable": True,
                },
            ) from exc

        text = str(transcription).strip()
        return {"text": text, "duration_ms": max(duration_ms, 0)}

    @app.post("/chat", response_model=ChatResponse)
    async def chat_reply(payload: ChatRequest) -> ChatResponse:
        if len(payload.history) > MAX_HISTORY_TURNS:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "HISTORY_TOO_LONG",
                    "message": f"History exceeds limit of {MAX_HISTORY_TURNS} turns.",
                    "retryable": False,
                },
            )

        interview_template = _load_text(PATHS.interview_prompt)
        system_prompt = inject_vars(
            interview_template,
            STUDENT_NAME=payload.student_name,
            ROLE_NAME=payload.role_name,
        )

        context_note = (
            "Session metadata:\n"
            f"- Current question index: {payload.question_index} / 7\n"
            f"- Phase: {payload.phase}\n"
            f"- Probe already used this question: {payload.probe_used_current_question}\n"
            f"- Strike count from client: {payload.strike_count}\n"
            "Reply in 1-3 sentences. Stay in character.\n"
            "Do not ask any canonical main interview questions (Q1-Q7) because the frontend controls question sequencing.\n"
            "Do not repeat or paraphrase the candidate's answer back to them.\n"
            "Use natural short acknowledgments (for example: Right. Okay. I see.) and then either a probe or a concise transition.\n"
            "Never include or restate the next canonical question in this reply.\n"
            "At this step, provide only one of: concise acknowledgment, single probe follow-up, guardrail redirect, or final closure."
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_note},
        ]

        for turn in payload.history:
            messages.append({"role": turn.role, "content": turn.content})

        messages.append({"role": "user", "content": payload.student_text})

        client = get_openai_client()
        try:
            completion = client.chat.completions.create(
                model=DEFAULT_CHAT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=200,
                timeout=45,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "CHAT_FAILED",
                    "message": f"Chat service failed: {exc}",
                    "retryable": True,
                },
            ) from exc

        reply = (completion.choices[0].message.content or "").strip()
        contains_complete_tag = "[INTERVIEW_COMPLETE]" in reply
        is_probe = detect_probe(reply)

        # Keep deterministic question flow on the client by removing accidental next-question spillover.
        if payload.phase in {"main_answer", "probe_answer"} and not contains_complete_tag:
            next_question_index = payload.question_index
            next_question = (
                questions_cache[next_question_index]
                if 0 <= next_question_index < len(questions_cache)
                else None
            )
            if next_question and reply_contains_canonical_question(reply, next_question):
                reply = prune_questions_from_reply(reply)
                is_probe = False
            if not is_probe:
                reply = prune_canonical_questions(reply, questions_cache)

        if not is_probe and not contains_complete_tag:
            reply = de_echo_opening(reply)
            # In non-probe turns, avoid ending with a question to prevent unintended double prompts.
            if payload.phase in {"main_answer", "probe_answer"} and reply.strip().endswith("?"):
                reply = prune_questions_from_reply(reply)

        return ChatResponse(
            reply=reply,
            is_probe=is_probe,
            contains_complete_tag=contains_complete_tag,
        )

    @app.post("/evaluate", response_model=EvaluateResponse)
    async def evaluate_interview(payload: EvaluateRequest) -> EvaluateResponse:
        if not payload.transcript:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "EMPTY_TRANSCRIPT",
                    "message": "Transcript must contain at least one turn.",
                    "retryable": False,
                },
            )

        eval_template = _load_text(PATHS.evaluation_prompt)
        formatted_transcript = format_transcript(payload.transcript, payload.student_name)
        eval_prompt = inject_vars(
            eval_template,
            STUDENT_NAME=payload.student_name,
            ROLE_NAME=payload.role_name,
            DATE=datetime.now().strftime("%d/%m/%Y"),
            DURATION=format_duration(payload.duration_seconds),
            OFF_TOPIC_STRIKES=str(payload.off_topic_strikes),
            ANSWERED_QUESTIONS=str(payload.answered_questions),
            TOTAL_QUESTIONS=str(payload.total_questions),
            INTERVIEW_COMPLETED="YES" if payload.interview_completed else "NO",
            TRANSCRIPT=formatted_transcript,
        )

        schema = {
            "name": "evaluation_report",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "report_text": {"type": "string"},
                    "scores": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "c1": {"type": "integer", "minimum": 1, "maximum": 4},
                            "c2": {"type": "integer", "minimum": 1, "maximum": 4},
                            "c3": {"type": "integer", "minimum": 1, "maximum": 4},
                            "c4": {"type": "integer", "minimum": 1, "maximum": 4},
                            "c5": {"type": "integer", "minimum": 1, "maximum": 4},
                            "total": {"type": "integer", "minimum": 0, "maximum": 20},
                            "percent": {"type": "integer", "minimum": 0, "maximum": 100},
                            "grade": {"type": "string"},
                            "cefr": {"type": "string"},
                        },
                        "required": ["c1", "c2", "c3", "c4", "c5", "total", "percent", "grade", "cefr"],
                    },
                },
                "required": ["report_text", "scores"],
            },
        }

        client = get_openai_client()

        try:
            structured = client.chat.completions.create(
                model=DEFAULT_EVAL_MODEL,
                messages=[{"role": "system", "content": eval_prompt}],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_schema", "json_schema": schema},
                timeout=45,
            )
            raw_json = structured.choices[0].message.content or "{}"
            parsed = json.loads(raw_json)
            validated = EvaluateResponse.model_validate(parsed)
            adjusted_scores, caps_applied = apply_incomplete_interview_caps(
                validated.scores,
                payload.answered_questions,
                payload.total_questions,
                payload.interview_completed,
            )
            report_text = validated.report_text
            if caps_applied:
                note = (
                    f"Note: Interview incomplete ({payload.answered_questions}/{payload.total_questions} "
                    "main questions answered). Rubric caps were applied to prevent over-scoring.\n\n"
                )
                report_text = f"{note}{report_text}"
            return EvaluateResponse(report_text=report_text, scores=adjusted_scores)
        except Exception as structured_exc:  # noqa: BLE001
            logger.warning("Structured evaluation failed, using fallback: %s", structured_exc)
            try:
                fallback = client.chat.completions.create(
                    model=DEFAULT_EVAL_MODEL,
                    messages=[
                        {"role": "system", "content": eval_prompt},
                        {
                            "role": "user",
                            "content": "Return only the complete plain-text report. Do not return JSON.",
                        },
                    ],
                    temperature=0.3,
                    max_tokens=1500,
                    timeout=45,
                )
                report_text = (fallback.choices[0].message.content or "").strip()
                if not report_text:
                    raise ValueError("Empty fallback report")
                if not payload.interview_completed:
                    note = (
                        f"Note: Interview incomplete ({payload.answered_questions}/{payload.total_questions} "
                        "main questions answered). Scores unavailable in fallback mode.\n\n"
                    )
                    report_text = f"{note}{report_text}"
                return EvaluateResponse(report_text=report_text, scores=null_scores())
            except Exception as fallback_exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "EVALUATION_FAILED",
                        "message": f"Evaluation service failed: {fallback_exc}",
                        "retryable": True,
                    },
                ) from fallback_exc

    return app


app = create_app()
