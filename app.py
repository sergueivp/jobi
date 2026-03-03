from __future__ import annotations

import io
import json
import logging
import os
import re
import hashlib
import hmac
import base64
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("terratech-interview")

MAX_HISTORY_TURNS = 60
MAX_AUDIO_BYTES = 10 * 1024 * 1024
DEFAULT_CHAT_MODEL = os.getenv("MODEL_CHAT", "gpt-4o")
DEFAULT_EVAL_MODEL = os.getenv("MODEL_EVAL", "gpt-4o")
DEFAULT_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
ACCESS_PIN = os.getenv("ACCESS_PIN", "").strip()
ACCESS_PIN_TTL_HOURS = int(os.getenv("ACCESS_PIN_TTL_HOURS", "168"))
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
MAX_ATTEMPTS = 3
ATTEMPTS_COOKIE_NAME = "tt_attempts"
ATTEMPTS_COOKIE_TTL_HOURS = int(os.getenv("ATTEMPTS_COOKIE_TTL_HOURS", "720"))
BROWSER_LOCK_COOKIE_NAME = "tt_final_lock"
LOCK_BROWSER_AFTER_FINAL = os.getenv("LOCK_BROWSER_AFTER_FINAL", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ATTEMPT_STORE_PATH_RAW = os.getenv("ATTEMPT_STORE_PATH", "").strip()
TEACHER_EMAIL = os.getenv("TEACHER_EMAIL", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USERNAME
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "ssl").strip().lower()  # ssl | starttls | none

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

POOLED_QUESTIONS: list[dict[str, object]] = [
    {
        "id": "A1",
        "category": "A",
        "text": "Tell me about a surveying or data collection task you have done - in a project, placement, or university exercise. What instruments or methods did you use, and what was technically challenging about it?",
        "keywords": ("survey", "instrument", "gnss", "total station", "field", "method"),
    },
    {
        "id": "A2",
        "category": "A",
        "text": "Describe a time when you had to process or analyse spatial data under time pressure. What was the dataset, what did you need to produce, and how did you manage it?",
        "keywords": ("process", "analyse", "data", "qgis", "arcgis", "deadline"),
    },
    {
        "id": "A3",
        "category": "A",
        "text": "Have you ever worked with satellite imagery or remote sensing data - in any context, including university work? Tell me what you did with it and what you learned.",
        "keywords": ("satellite", "remote sensing", "imagery", "sentinel", "landsat", "drone"),
    },
    {
        "id": "A4",
        "category": "A",
        "text": "Give me an example of a project where the accuracy of your measurements really mattered. How did you ensure quality control?",
        "keywords": ("accuracy", "quality", "control", "error", "verification", "precision"),
    },
    {
        "id": "A5",
        "category": "A",
        "text": "Tell me about your experience with GIS software. What have you used, for what purpose, and what would you say you can do confidently versus what you are still learning?",
        "keywords": ("gis", "qgis", "arcgis", "postgis", "software", "mapping"),
    },
    {
        "id": "B1",
        "category": "B",
        "text": "Describe a time when you worked on a field survey or project with a team. What was your specific role, and was there a moment when the team had to adapt to something unexpected?",
        "keywords": ("team", "field", "role", "adapt", "collaboration", "project"),
    },
    {
        "id": "B2",
        "category": "B",
        "text": "Tell me about a time you worked with people who had a very different approach to a task than you did - in terms of method, pace, or priorities. How did you handle that?",
        "keywords": ("different", "style", "conflict", "method", "priority", "handle"),
    },
    {
        "id": "B3",
        "category": "B",
        "text": "Give me an example of a situation where you had to explain a technical result - a map, a survey report, or an analysis - to someone who was not a specialist. How did you approach that?",
        "keywords": ("explain", "technical", "non specialist", "communication", "report", "client"),
    },
    {
        "id": "B4",
        "category": "B",
        "text": "Describe a project where coordination between team members was difficult - different schedules, different locations, or different working styles. What did you do to keep things moving?",
        "keywords": ("coordination", "schedule", "location", "team", "organize", "communication"),
    },
    {
        "id": "C1",
        "category": "C",
        "text": "Give me a specific example of something going wrong in a project or field exercise - equipment failure, data quality issue, weather, or unexpected conditions. How did you identify the problem and what did you do?",
        "keywords": ("problem", "failure", "issue", "weather", "identify", "fix"),
    },
    {
        "id": "C2",
        "category": "C",
        "text": "Tell me about a time when you had to complete a task with incomplete information or data. What did you do, and how did you decide when you had enough to move forward?",
        "keywords": ("incomplete", "uncertain", "decision", "data", "enough", "move forward"),
    },
    {
        "id": "C3",
        "category": "C",
        "text": "Describe a situation where you made a mistake in your work - in the field, in data processing, or in a report. What happened, and what did you do about it?",
        "keywords": ("mistake", "error", "learned", "corrected", "responsibility", "improve"),
    },
    {
        "id": "C4",
        "category": "C",
        "text": "Have you ever been in a situation where you disagreed with how a project or task was being done? What did you do - did you say something, and if so, how?",
        "keywords": ("disagree", "push back", "project", "escalate", "professional", "handle"),
    },
    {
        "id": "D1",
        "category": "D",
        "text": "What would you say is your biggest professional strength - and can you give me a concrete example of it in action, from a project or academic work?",
        "keywords": ("strength", "example", "professional", "evidence", "project", "action"),
    },
    {
        "id": "D2",
        "category": "D",
        "text": "Where do you see your career in five years - and how does a role at TerraTech fit into that picture?",
        "keywords": ("career", "five years", "future", "goal", "trajectory", "fit"),
    },
    {
        "id": "D3",
        "category": "D",
        "text": "What is the most interesting geospatial project or development you have followed recently - not from your own work, but from the field in general?",
        "keywords": ("geospatial", "industry", "recent", "development", "project", "read"),
    },
    {
        "id": "D4",
        "category": "D",
        "text": "Tell me about the most technically demanding task you have completed - in university, a placement, or personal work. What made it demanding, and what did you take away from it?",
        "keywords": ("demanding", "challenge", "technical", "task", "takeaway", "learning"),
    },
]

POOL_BY_CATEGORY: dict[str, list[dict[str, object]]] = {"A": [], "B": [], "C": [], "D": []}
for item in POOLED_QUESTIONS:
    POOL_BY_CATEGORY[str(item["category"])].append(item)

QUESTION_TEXT_TO_ID: dict[str, str] = {
    str(item["text"]).strip(): str(item["id"]) for item in POOLED_QUESTIONS
}
SLOT_CATEGORY_MAP: dict[int, str] = {3: "A", 4: "B", 5: "C", 6: "D"}

ROLE_PREFERRED_IDS: dict[str, tuple[str, ...]] = {
    "junior geodetic surveyor": ("A1", "A4", "B1", "B2"),
    "gis analyst": ("A5", "A2", "C2", "B3"),
    "remote sensing analyst": ("A3", "A2", "C2", "D3"),
    "photogrammetry technician": ("A1", "A4", "C1", "B1"),
    "environmental monitoring specialist": ("A3", "D3", "C2", "B3"),
    "project geodesist": ("B2", "B4", "D2", "C4"),
    "spatial data engineer": ("A2", "A5", "C2", "D4"),
}


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
ATTEMPT_STORE_PATH = Path(ATTEMPT_STORE_PATH_RAW) if ATTEMPT_STORE_PATH_RAW else BASE_DIR / ".attempts_store.json"
ATTEMPT_STORE_LOCK = Lock()
ATTEMPT_STORE_CACHE: dict[str, int] = {}
ATTEMPT_STORE_LOADED = False


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
    next_question: str | None = None


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
    c1: int | None = Field(default=None, ge=0, le=4)
    c2: int | None = Field(default=None, ge=0, le=4)
    c3: int | None = Field(default=None, ge=0, le=4)
    c4: int | None = Field(default=None, ge=0, le=4)
    c5: int | None = Field(default=None, ge=0, le=4)
    total: int | None = Field(default=None, ge=0, le=20)
    percent: int | None = Field(default=None, ge=0, le=100)
    grade: str | None = None
    cefr: str | None = None


class QuestionResponse(BaseModel):
    questions: list[str]


class AttemptStatusResponse(BaseModel):
    attempts_used: int = Field(ge=0, le=MAX_ATTEMPTS)
    attempts_remaining: int = Field(ge=0, le=MAX_ATTEMPTS)
    next_attempt_number: int = Field(ge=1, le=MAX_ATTEMPTS + 1)
    max_attempts: int = MAX_ATTEMPTS
    is_final_attempt: bool
    is_locked: bool
    warning: str | None = None


class AttemptResult(BaseModel):
    attempt_number: int = Field(ge=1, le=MAX_ATTEMPTS)
    max_attempts: int = MAX_ATTEMPTS
    is_final_attempt: bool
    is_assessment_attempt: bool


class SignedReportPackage(BaseModel):
    report_id: str
    issued_at: str
    payload: dict[str, object]
    signature: str


class VerifyReportResponse(BaseModel):
    valid: bool
    report_id: str
    reason: str | None = None
    verified_at: str


class EvaluateResponse(BaseModel):
    report_text: str
    scores: ScorePayload
    attempt: AttemptResult | None = None
    report_package: SignedReportPackage | None = None
    final_report_email_status: str | None = None


class PinRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=32)


class PinStatus(BaseModel):
    required: bool


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TtsStatus(BaseModel):
    enabled: bool


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


def _stable_hash_int(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _extract_used_pool_ids(history: list[HistoryTurn]) -> set[str]:
    used: set[str] = set()
    for turn in history:
        if turn.role != "assistant":
            continue
        question_id = QUESTION_TEXT_TO_ID.get(turn.content.strip())
        if question_id:
            used.add(question_id)
    return used


def _role_preference_ids(role_name: str) -> set[str]:
    normalized = role_name.lower().strip()
    preferred: set[str] = set()
    for role_key, ids in ROLE_PREFERRED_IDS.items():
        if role_key in normalized:
            preferred.update(ids)
    return preferred


def select_next_pooled_question(
    next_question_index: int,
    role_name: str,
    student_text: str,
    history: list[HistoryTurn],
) -> str | None:
    target_category = SLOT_CATEGORY_MAP.get(next_question_index)
    if not target_category:
        return None

    used_ids = _extract_used_pool_ids(history)
    candidates = [
        item
        for item in POOL_BY_CATEGORY.get(target_category, [])
        if str(item["id"]) not in used_ids
    ]
    if not candidates:
        candidates = list(POOL_BY_CATEGORY.get(target_category, []))
    if not candidates:
        return None

    preferred_ids = _role_preference_ids(role_name)
    student_lower = student_text.lower()
    base_seed = f"{role_name}|{student_text}|{next_question_index}"

    best_item: dict[str, object] | None = None
    best_tuple: tuple[int, int] | None = None
    for item in candidates:
        item_id = str(item["id"])
        item_keywords = tuple(str(value).lower() for value in item["keywords"])  # type: ignore[index]
        keyword_hits = sum(1 for keyword in item_keywords if keyword and keyword in student_lower)
        score = min(keyword_hits, 3)
        if item_id in preferred_ids:
            score += 2
        tie = _stable_hash_int(f"{base_seed}|{item_id}")
        rank = (score, tie)
        if best_tuple is None or rank > best_tuple:
            best_tuple = rank
            best_item = item

    return str(best_item["text"]) if best_item else None


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


def pin_required() -> bool:
    return bool(ACCESS_PIN)


def tts_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_signing_secret() -> str:
    secret = os.getenv("REPORT_SIGNING_SECRET", "").strip()
    if secret:
        return secret
    if ACCESS_PIN:
        return ACCESS_PIN
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key
    return "terratech-dev-signing-secret"


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_text(value: str) -> str:
    digest = hmac.new(get_signing_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return b64url_encode(digest)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_attempt_key(student_name: str, role_name: str) -> str:
    material = f"{student_name.strip().lower()}|{role_name.strip().lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def parse_attempt_cookie(cookie_value: str | None) -> dict[str, int]:
    if not cookie_value:
        return {}
    try:
        payload_b64, signature = cookie_value.split(".", 1)
    except ValueError:
        return {}

    expected = sign_text(payload_b64)
    if not hmac.compare_digest(signature, expected):
        logger.warning("Attempt cookie signature mismatch; resetting.")
        return {}

    try:
        decoded = b64url_decode(payload_b64).decode("utf-8")
        parsed = json.loads(decoded)
    except Exception:  # noqa: BLE001
        return {}

    if not isinstance(parsed, dict):
        return {}

    sanitized: dict[str, int] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, int):
            sanitized[key] = max(0, min(MAX_ATTEMPTS, value))
    return sanitized


def serialize_attempt_cookie(store: dict[str, int]) -> str:
    serialized = canonical_json(store)
    payload_b64 = b64url_encode(serialized.encode("utf-8"))
    signature = sign_text(payload_b64)
    return f"{payload_b64}.{signature}"


def _sanitize_attempt_store(store: object) -> dict[str, int]:
    if not isinstance(store, dict):
        return {}
    sanitized: dict[str, int] = {}
    for key, value in store.items():
        if isinstance(key, str) and isinstance(value, int):
            sanitized[key] = max(0, min(MAX_ATTEMPTS, value))
    return sanitized


def load_attempt_store_if_needed() -> None:
    global ATTEMPT_STORE_LOADED
    if ATTEMPT_STORE_LOADED:
        return
    with ATTEMPT_STORE_LOCK:
        if ATTEMPT_STORE_LOADED:
            return
        try:
            if ATTEMPT_STORE_PATH.exists():
                parsed = json.loads(ATTEMPT_STORE_PATH.read_text(encoding="utf-8"))
                ATTEMPT_STORE_CACHE.clear()
                ATTEMPT_STORE_CACHE.update(_sanitize_attempt_store(parsed))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load attempt store: %s", exc)
            ATTEMPT_STORE_CACHE.clear()
        ATTEMPT_STORE_LOADED = True


def persist_attempt_store() -> None:
    try:
        ATTEMPT_STORE_PATH.write_text(canonical_json(ATTEMPT_STORE_CACHE), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist attempt store: %s", exc)


def get_server_attempts(key: str) -> int:
    load_attempt_store_if_needed()
    with ATTEMPT_STORE_LOCK:
        return max(0, min(MAX_ATTEMPTS, ATTEMPT_STORE_CACHE.get(key, 0)))


def set_server_attempts(key: str, attempts_used: int) -> None:
    load_attempt_store_if_needed()
    with ATTEMPT_STORE_LOCK:
        ATTEMPT_STORE_CACHE[key] = max(0, min(MAX_ATTEMPTS, attempts_used))
        persist_attempt_store()


def build_attempt_status(attempts_used: int) -> AttemptStatusResponse:
    used = max(0, min(MAX_ATTEMPTS, attempts_used))
    is_locked = used >= MAX_ATTEMPTS
    next_attempt_number = min(used + 1, MAX_ATTEMPTS + 1)
    is_final_attempt = not is_locked and next_attempt_number == MAX_ATTEMPTS
    warning: str | None = None
    if is_locked:
        warning = f"All {MAX_ATTEMPTS} attempts are already used."
    elif is_final_attempt:
        warning = (
            f"Warning: this is your final attempt ({MAX_ATTEMPTS}/{MAX_ATTEMPTS}). "
            "This result is the one for assessment."
        )
    return AttemptStatusResponse(
        attempts_used=used,
        attempts_remaining=max(0, MAX_ATTEMPTS - used),
        next_attempt_number=next_attempt_number,
        max_attempts=MAX_ATTEMPTS,
        is_final_attempt=is_final_attempt,
        is_locked=is_locked,
        warning=warning,
    )


def attempts_used_for_identity(request: Request, student_name: str, role_name: str) -> int:
    key = normalize_attempt_key(student_name, role_name)
    store = parse_attempt_cookie(request.cookies.get(ATTEMPTS_COOKIE_NAME))
    cookie_used = store.get(key, 0)
    server_used = get_server_attempts(key)
    if cookie_used > server_used:
        set_server_attempts(key, cookie_used)
        return cookie_used
    return server_used


def ensure_attempts_available(request: Request, student_name: str, role_name: str) -> None:
    used = attempts_used_for_identity(request, student_name, role_name)
    status = build_attempt_status(used)
    if status.is_locked:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ATTEMPTS_EXHAUSTED",
                "message": (
                    f"All {MAX_ATTEMPTS} attempts are already used for this student/role. "
                    "No additional interview calls are allowed."
                ),
                "retryable": False,
            },
        )


def sign_report_payload(payload: dict[str, object]) -> str:
    return sign_text(canonical_json(payload))


def build_report_id(payload: dict[str, object], signature: str) -> str:
    digest = hashlib.sha256(f"{canonical_json(payload)}.{signature}".encode("utf-8")).hexdigest()
    return f"rep_{digest[:16]}"


def create_signed_report_package(payload: dict[str, object]) -> SignedReportPackage:
    signature = sign_report_payload(payload)
    report_id = build_report_id(payload, signature)
    issued_at = str(payload.get("issued_at") or now_iso_utc())
    return SignedReportPackage(
        report_id=report_id,
        issued_at=issued_at,
        payload=payload,
        signature=signature,
    )


def verify_signed_report_package(report_package: SignedReportPackage) -> tuple[bool, str | None]:
    expected_signature = sign_report_payload(report_package.payload)
    if not hmac.compare_digest(report_package.signature, expected_signature):
        return False, "Signature mismatch."

    expected_report_id = build_report_id(report_package.payload, report_package.signature)
    if report_package.report_id != expected_report_id:
        return False, "Report ID mismatch."

    if str(report_package.payload.get("issued_at", "")) != report_package.issued_at:
        return False, "Issued-at mismatch."

    return True, None


def email_delivery_configured() -> bool:
    return bool(TEACHER_EMAIL and SMTP_HOST and SMTP_FROM and (SMTP_PASSWORD or not SMTP_USERNAME))


def send_final_report_email(
    student_name: str,
    role_name: str,
    report_text: str,
    scores: ScorePayload,
    report_package: SignedReportPackage,
) -> tuple[bool, str | None]:
    if not email_delivery_configured():
        logger.warning("Final report email skipped: SMTP not configured.")
        return False, "not_configured"

    subject = f"TerraTech Final Attempt Report | {student_name} | {report_package.report_id}"
    body_lines = [
        "Final attempt report generated.",
        "",
        f"Student: {student_name}",
        f"Role: {role_name}",
        f"Report ID: {report_package.report_id}",
        f"Issued at: {report_package.issued_at}",
        f"Total: {scores.total if scores.total is not None else '-'} / 20",
        f"Grade: {scores.grade or '-'}",
        f"CEFR: {scores.cefr or '-'}",
        "",
        "Signed report package is attached as JSON.",
        "",
        "Report excerpt:",
        report_text[:5000],
    ]

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = TEACHER_EMAIL
    message["Subject"] = subject
    message.set_content("\n".join(body_lines))

    package_bytes = json.dumps(
        report_package.model_dump(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    message.add_attachment(
        package_bytes,
        maintype="application",
        subtype="json",
        filename=f"{report_package.report_id}.json",
    )

    try:
        if SMTP_SECURITY == "starttls":
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                if SMTP_USERNAME:
                    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        elif SMTP_SECURITY == "none":
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as smtp:
                if SMTP_USERNAME:
                    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=25) as smtp:
                if SMTP_USERNAME:
                    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        logger.info("Final report email sent for report_id=%s", report_package.report_id)
        return True, None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send final report email: %s", exc)
        return False, str(exc)


def read_audio_bytes(result: object) -> bytes:
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if hasattr(result, "read"):
        return result.read()
    if hasattr(result, "content"):
        return result.content
    return bytes(result)


def grade_from_total(total: int) -> tuple[str, str]:
    if total == 0:
        return ("F (No performance)", "Not assessable")
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
            if scores[idx] > 0 and sum(scores) > total_cap:
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
    off_topic_strikes: int = 0,
) -> tuple[ScorePayload, bool]:
    if not all_criteria_present(scores):
        return scores, False

    if answered_questions <= 0:
        zeroed = ScorePayload(
            c1=0,
            c2=0,
            c3=0,
            c4=0,
            c5=0,
            total=0,
            percent=0,
            grade="F (No performance)",
            cefr="Not assessable",
        )
        return zeroed, True

    if interview_completed and answered_questions >= total_questions:
        criteria = [scores.c1, scores.c2, scores.c3, scores.c4, scores.c5]  # type: ignore[list-item]
        if off_topic_strikes >= 1:
            criteria[4] = min(criteria[4], 3)
        if off_topic_strikes >= 2:
            criteria[4] = min(criteria[4], 2)
        if off_topic_strikes >= 3:
            criteria[4] = min(criteria[4], 1)
            criteria[0] = 0
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

    if off_topic_strikes >= 1:
        criteria[4] = min(criteria[4], 3)
    if off_topic_strikes >= 2:
        criteria[4] = min(criteria[4], 2)
    if off_topic_strikes >= 3:
        criteria[4] = min(criteria[4], 1)
        criteria[0] = 0

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
    app = FastAPI(title="TerraTech Geospatial Interview Simulator", version="1.0.0")
    questions_cache: list[str] = []

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        if LOCK_BROWSER_AFTER_FINAL:
            locked_paths = {"/questions", "/transcribe", "/tts", "/chat", "/evaluate"}
            if request.method != "OPTIONS" and request.url.path in locked_paths:
                if request.cookies.get(BROWSER_LOCK_COOKIE_NAME) == "1":
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": {
                                "code": "SESSION_LOCKED",
                                "message": "Final attempt already completed on this browser session.",
                                "retryable": False,
                            }
                        },
                    )
        if pin_required():
            allowed = {"/", "/health", "/auth", "/auth/status", "/tts/status", "/verify-report"}
            if request.url.path.startswith("/static"):
                allowed.add(request.url.path)
            if request.method != "OPTIONS" and request.url.path not in allowed:
                header_pin = request.headers.get("x-access-pin", "").strip()
                pin_ok = request.cookies.get("nt_pin") == "ok" or (header_pin and header_pin == ACCESS_PIN)
                if not pin_ok:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": {
                                "code": "PIN_REQUIRED",
                                "message": "PIN required to access this application.",
                                "retryable": False,
                            }
                        },
                    )
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
        load_attempt_store_if_needed()
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

    @app.get("/auth/status", response_model=PinStatus)
    async def auth_status() -> PinStatus:
        return PinStatus(required=pin_required())

    @app.get("/tts/status", response_model=TtsStatus)
    async def tts_status() -> TtsStatus:
        return TtsStatus(enabled=tts_enabled())

    @app.post("/auth")
    async def auth_pin(payload: PinRequest) -> Response:
        if not pin_required():
            return Response(status_code=204)
        if payload.pin.strip() != ACCESS_PIN:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PIN_INVALID",
                    "message": "Incorrect PIN.",
                    "retryable": False,
                },
            )
        max_age = max(1, ACCESS_PIN_TTL_HOURS) * 3600
        response = Response(status_code=204)
        response.set_cookie(
            "nt_pin",
            "ok",
            max_age=max_age,
            httponly=True,
            samesite="lax",
        )
        return response

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

    @app.get("/attempts/status", response_model=AttemptStatusResponse)
    async def attempts_status(student_name: str, role_name: str, request: Request) -> AttemptStatusResponse:
        if LOCK_BROWSER_AFTER_FINAL and request.cookies.get(BROWSER_LOCK_COOKIE_NAME) == "1":
            return AttemptStatusResponse(
                attempts_used=MAX_ATTEMPTS,
                attempts_remaining=0,
                next_attempt_number=MAX_ATTEMPTS + 1,
                max_attempts=MAX_ATTEMPTS,
                is_final_attempt=False,
                is_locked=True,
                warning="Final attempt already completed on this browser session.",
            )
        student = student_name.strip()
        role = role_name.strip()
        if not student or not role:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "ATTEMPT_IDENTITY_REQUIRED",
                    "message": "student_name and role_name are required.",
                    "retryable": False,
                },
            )
        used = attempts_used_for_identity(request, student, role)
        return build_attempt_status(used)

    @app.post("/transcribe")
    async def transcribe_audio(
        request: Request,
        audio: UploadFile = File(...),
        duration_ms: int = Form(default=0),
        student_name: str | None = Form(default=None),
        role_name: str | None = Form(default=None),
    ) -> dict[str, str | int]:
        if student_name and role_name:
            ensure_attempts_available(request, student_name, role_name)

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

    @app.post("/tts")
    async def text_to_speech(payload: TtsRequest) -> Response:
        if not tts_enabled():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "TTS_DISABLED",
                    "message": "Server-side TTS is disabled.",
                    "retryable": False,
                },
            )
        client = get_openai_client()
        try:
            result = client.audio.speech.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=payload.text,
                response_format="mp3",
                timeout=45,
            )
            audio_bytes = read_audio_bytes(result)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "TTS_FAILED",
                    "message": f"TTS service failed: {exc}",
                    "retryable": True,
                },
            ) from exc

        if not audio_bytes:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "TTS_EMPTY",
                    "message": "TTS returned empty audio.",
                    "retryable": True,
                },
            )
        return Response(content=audio_bytes, media_type="audio/mpeg")

    @app.post("/chat", response_model=ChatResponse)
    async def chat_reply(payload: ChatRequest, request: Request) -> ChatResponse:
        ensure_attempts_available(request, payload.student_name, payload.role_name)

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
        next_question: str | None = None

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

        if payload.phase in {"main_answer", "probe_answer"} and not contains_complete_tag and not is_probe:
            upcoming_index = payload.question_index + 1
            next_question = select_next_pooled_question(
                next_question_index=upcoming_index,
                role_name=payload.role_name,
                student_text=payload.student_text,
                history=payload.history,
            )

        return ChatResponse(
            reply=reply,
            is_probe=is_probe,
            contains_complete_tag=contains_complete_tag,
            next_question=next_question,
        )

    @app.post("/evaluate", response_model=EvaluateResponse)
    async def evaluate_interview(
        payload: EvaluateRequest,
        request: Request,
        http_response: Response,
    ) -> EvaluateResponse:
        if not payload.transcript:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "EMPTY_TRANSCRIPT",
                    "message": "Transcript must contain at least one turn.",
                    "retryable": False,
                },
            )

        attempt_key = normalize_attempt_key(payload.student_name, payload.role_name)
        attempt_store = parse_attempt_cookie(request.cookies.get(ATTEMPTS_COOKIE_NAME))
        attempts_used = attempts_used_for_identity(request, payload.student_name, payload.role_name)
        attempt_status = build_attempt_status(attempts_used)
        if attempt_status.is_locked:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ATTEMPTS_EXHAUSTED",
                    "message": (
                        f"All {MAX_ATTEMPTS} attempts are already used for this student/role. "
                        "No additional report can be generated."
                    ),
                    "retryable": False,
                },
            )

        attempt_number = attempt_status.next_attempt_number
        is_assessment_attempt = attempt_number == MAX_ATTEMPTS
        attempt_result = AttemptResult(
            attempt_number=attempt_number,
            max_attempts=MAX_ATTEMPTS,
            is_final_attempt=is_assessment_attempt,
            is_assessment_attempt=is_assessment_attempt,
        )

        def finalize_response(report_text: str, scores: ScorePayload) -> EvaluateResponse:
            attempt_banner = (
                f"Attempt {attempt_number}/{MAX_ATTEMPTS} "
                + (
                    "(FINAL - this grade counts for assessment)."
                    if is_assessment_attempt
                    else "(practice attempt - formative feedback)."
                )
            )
            full_report_text = f"{attempt_banner}\n\n{report_text}".strip()
            report_payload: dict[str, object] = {
                "report_version": 1,
                "issued_at": now_iso_utc(),
                "student_name": payload.student_name,
                "role_name": payload.role_name,
                "attempt": attempt_result.model_dump(),
                "duration_seconds": payload.duration_seconds,
                "off_topic_strikes": payload.off_topic_strikes,
                "answered_questions": payload.answered_questions,
                "total_questions": payload.total_questions,
                "interview_completed": payload.interview_completed,
                "scores": scores.model_dump(),
                "report_text": full_report_text,
                "transcript_sha256": hashlib.sha256(
                    canonical_json([turn.model_dump() for turn in payload.transcript]).encode("utf-8")
                ).hexdigest(),
            }
            report_package = create_signed_report_package(report_payload)
            email_status: str | None = None

            if attempt_result.is_assessment_attempt:
                if email_delivery_configured():
                    sent, error_message = send_final_report_email(
                        payload.student_name,
                        payload.role_name,
                        full_report_text,
                        scores,
                        report_package,
                    )
                    email_status = "sent" if sent else f"failed: {error_message or 'unknown error'}"
                else:
                    logger.warning(
                        "Final attempt email not configured; report_id=%s",
                        report_package.report_id,
                    )
                    email_status = "not_configured"

            set_server_attempts(attempt_key, attempt_number)
            attempt_store[attempt_key] = attempt_number
            max_age = max(1, ATTEMPTS_COOKIE_TTL_HOURS) * 3600
            http_response.set_cookie(
                ATTEMPTS_COOKIE_NAME,
                serialize_attempt_cookie(attempt_store),
                max_age=max_age,
                httponly=True,
                samesite="lax",
            )
            if attempt_result.is_assessment_attempt and LOCK_BROWSER_AFTER_FINAL:
                http_response.set_cookie(
                    BROWSER_LOCK_COOKIE_NAME,
                    "1",
                    max_age=max_age,
                    httponly=True,
                    samesite="lax",
                )

            return EvaluateResponse(
                report_text=full_report_text,
                scores=scores,
                attempt=attempt_result,
                report_package=report_package,
                final_report_email_status=email_status,
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
                            "c1": {"type": "integer", "minimum": 0, "maximum": 4},
                            "c2": {"type": "integer", "minimum": 0, "maximum": 4},
                            "c3": {"type": "integer", "minimum": 0, "maximum": 4},
                            "c4": {"type": "integer", "minimum": 0, "maximum": 4},
                            "c5": {"type": "integer", "minimum": 0, "maximum": 4},
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
                payload.off_topic_strikes,
            )
            report_text = validated.report_text
            if caps_applied:
                note = (
                    f"Note: Interview incomplete ({payload.answered_questions}/{payload.total_questions} "
                    "main questions answered). Rubric caps were applied to prevent over-scoring.\n\n"
                )
                report_text = f"{note}{report_text}"
            return finalize_response(report_text=report_text, scores=adjusted_scores)
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
                return finalize_response(report_text=report_text, scores=null_scores())
            except Exception as fallback_exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "EVALUATION_FAILED",
                        "message": f"Evaluation service failed: {fallback_exc}",
                        "retryable": True,
                    },
                ) from fallback_exc

    @app.post("/verify-report", response_model=VerifyReportResponse)
    async def verify_report(report_package: SignedReportPackage) -> VerifyReportResponse:
        valid, reason = verify_signed_report_package(report_package)
        return VerifyReportResponse(
            valid=valid,
            report_id=report_package.report_id,
            reason=reason,
            verified_at=now_iso_utc(),
        )

    return app


app = create_app()
