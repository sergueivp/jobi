from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module


def test_questions_endpoint_returns_seven_items() -> None:
    client = TestClient(app_module.create_app())
    response = client.get("/questions")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["questions"], list)
    assert len(payload["questions"]) == 7
    assert all(isinstance(item, str) and item for item in payload["questions"])


def test_parse_questions_fails_when_missing_headings() -> None:
    bad_prompt = """
### Q1
"Only one question"
"""
    try:
        app_module.parse_questions_from_prompt(bad_prompt)
    except ValueError as exc:
        assert "Expected 7 question headings" in str(exc)
    else:
        raise AssertionError("Expected parser to raise ValueError")


def test_questions_endpoint_returns_500_on_parser_error(monkeypatch) -> None:
    client = TestClient(app_module.create_app())

    def boom(_prompt: str) -> list[str]:
        raise ValueError("broken parser")

    monkeypatch.setattr(app_module, "parse_questions_from_prompt", boom)
    response = client.get("/questions")

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["code"] == "QUESTION_PARSE_ERROR"


def _fake_openai_client(reply_text: str):
    message = SimpleNamespace(content=reply_text)
    choice = SimpleNamespace(message=message)
    completion = SimpleNamespace(choices=[choice])

    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return completion

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    return FakeClient()


def _chat_payload() -> dict:
    return {
        "student_name": "Maria",
        "role_name": "Junior Developer",
        "question_index": 1,
        "phase": "main_answer",
        "probe_used_current_question": False,
        "strike_count": 0,
        "history": [
            {
                "role": "assistant",
                "content": "Could you briefly introduce yourself?",
                "timestamp": "10:00:00",
            }
        ],
        "student_text": "I am a computer science student.",
    }


def test_chat_returns_is_probe_true(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_openai_client",
        lambda: _fake_openai_client("Could you tell me more about your specific contribution?"),
    )

    client = TestClient(app_module.create_app())
    response = client.post("/chat", json=_chat_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_probe"] is True
    assert payload["contains_complete_tag"] is False


def test_chat_returns_is_probe_false(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_openai_client",
        lambda: _fake_openai_client("Right, that's clear context. Let's continue."),
    )

    client = TestClient(app_module.create_app())
    response = client.post("/chat", json=_chat_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_probe"] is False


def test_detect_probe_function_positive_and_negative_cases() -> None:
    assert app_module.detect_probe("Can you elaborate on the outcome?") is True
    assert app_module.detect_probe("Could you walk me through the timeline?") is True
    assert app_module.detect_probe("Tell me more about that") is False
    assert app_module.detect_probe("Thank you for the context.") is False


def test_reply_contains_canonical_question_match() -> None:
    reply = (
        "Thank you for sharing that. Let's dive deeper into your knowledge about NovaTech. "
        "Why specifically NovaTech? What do you know about what we do, and why does it interest you?"
    )
    question = "Why specifically NovaTech? What do you know about what we do, and why does it interest you?"
    assert app_module.reply_contains_canonical_question(reply, question) is True


def test_prune_questions_from_reply_keeps_statement_only() -> None:
    reply = "Right. Let's dive deeper. Why specifically NovaTech?"
    pruned = app_module.prune_questions_from_reply(reply)
    assert pruned == "Right. Let's dive deeper."


def test_de_echo_opening_rewrites_boilerplate() -> None:
    rewritten = app_module.de_echo_opening(
        "Thank you for sharing that, Sergi. I see. Could you tell me more about the outcome?"
    )
    assert rewritten.startswith("Right.")


def test_chat_sanitizes_accidental_next_question(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_openai_client",
        lambda: _fake_openai_client(
            "Thank you for sharing that, Sergi. Why specifically NovaTech? What do you know about what we do, and why does it interest you?"
        ),
    )

    client = TestClient(app_module.create_app())
    payload = _chat_payload()
    payload["question_index"] = 1
    response = client.post("/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["is_probe"] is False
    assert "Why specifically NovaTech" not in data["reply"]


def test_select_next_pooled_question_returns_slot_category_question() -> None:
    question = app_module.select_next_pooled_question(
        next_question_index=3,
        role_name="Remote Sensing Analyst",
        student_text="I worked with satellite imagery and Sentinel data.",
        history=[],
    )
    assert question
    allowed = {entry["text"] for entry in app_module.POOL_BY_CATEGORY["A"]}
    assert question in allowed


def test_chat_returns_adaptive_next_question_for_pool_slots(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_openai_client",
        lambda: _fake_openai_client("Right. That's clear context."),
    )

    client = TestClient(app_module.create_app())
    payload = _chat_payload()
    payload["question_index"] = 2
    payload["role_name"] = "GIS Analyst"
    payload["student_text"] = "I used QGIS and PostGIS to process spatial data under deadline."
    response = client.post("/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["is_probe"] is False
    assert isinstance(data.get("next_question"), str)
    assert data["next_question"]


def test_chat_next_question_none_for_fixed_slots(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_openai_client",
        lambda: _fake_openai_client("Right. Let's continue."),
    )

    client = TestClient(app_module.create_app())
    payload = _chat_payload()
    payload["question_index"] = 1
    response = client.post("/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data.get("next_question") is None


def test_frontend_fetches_questions_and_avoids_hardcoded_q1() -> None:
    js_path = Path(__file__).resolve().parents[1] / "static" / "app.js"
    content = js_path.read_text(encoding="utf-8")

    assert 'fetch("/questions")' in content
    assert "Could you briefly introduce yourself and tell me what motivated you to apply for this role at NovaTech?" not in content


def test_incomplete_interview_caps_single_answer() -> None:
    original = app_module.ScorePayload(c1=4, c2=4, c3=4, c4=4, c5=4, total=20, percent=100, grade="A", cefr="B2+")
    adjusted, applied = app_module.apply_incomplete_interview_caps(
        original,
        answered_questions=1,
        total_questions=7,
        interview_completed=False,
    )

    assert applied is True
    assert adjusted.c1 == 1
    assert adjusted.total is not None and adjusted.total <= 8
    assert adjusted.grade in {"D", "F", "C"}


def test_complete_interview_recomputes_without_caps() -> None:
    original = app_module.ScorePayload(c1=3, c2=3, c3=3, c4=3, c5=3, total=0, percent=0, grade="F", cefr="Below B1.1")
    adjusted, applied = app_module.apply_incomplete_interview_caps(
        original,
        answered_questions=7,
        total_questions=7,
        interview_completed=True,
    )

    assert applied is False
    assert adjusted.total == 15
    assert adjusted.percent == 75
    assert adjusted.grade == "B"
