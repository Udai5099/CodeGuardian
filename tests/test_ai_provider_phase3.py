from __future__ import annotations

import json

from backend.app.modules.ai.providers import OpenAICompatibleProvider
from backend.app.modules.ai.service import (
    LLMBackedAIReviewer,
    create_configured_ai_reviewer,
)
from backend.app.modules.review.models import DiffLine, ReviewContext, ReviewFinding, ReviewFileContext


def _context() -> ReviewContext:
    return ReviewContext(
        files=[
            ReviewFileContext(
                file_path="app.py",
                language="Python",
                added_lines=[DiffLine("app.py", 4, "print(value)")],
                source_excerpt="3: value = 1\n4: print(value)",
            )
        ],
        deterministic_findings=[
            ReviewFinding(
                category="quality",
                severity="low",
                file_path="app.py",
                line=4,
                message="Deterministic issue",
                explanation="Found by a deterministic detector.",
                suggestion="Use logging.",
            )
        ],
    )


def _valid_response() -> dict[str, object]:
    return {
        "summary": "One issue",
        "findings": [
            {
                "category": "quality",
                "severity": "low",
                "file_path": "app.py",
                "line": 4,
                "message": "Debug output detected.",
                "explanation": "The added line writes to stdout.",
                "suggestion": "Use the project logger.",
            }
        ],
    }


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_provider_payload_contains_only_review_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse({"choices": [{"message": {"content": json_module.dumps(_valid_response())}}]})

    json_module = json
    monkeypatch.setattr("httpx.post", fake_post)
    provider = OpenAICompatibleProvider("test-key", "test-model", timeout=7.0)

    provider.generate_structured_review(_context())

    payload = captured["json"]
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["timeout"] == 7.0
    assert payload["model"] == "test-model"
    user_content = json.loads(payload["messages"][1]["content"])
    assert user_content["files"][0]["file_path"] == "app.py"
    assert user_content["files"][0]["language"] == "Python"
    assert user_content["files"][0]["added_lines"][0]["line_number"] == 4
    assert "print(value)" in user_content["files"][0]["source_excerpt"]
    assert user_content["deterministic_findings"][0]["message"] == "Deterministic issue"
    assert "repository" not in user_content


def test_llm_reviewer_validates_structured_provider_output() -> None:
    class FakeProvider:
        def generate_structured_review(self, context: ReviewContext) -> object:
            assert context == _context()
            return _valid_response()

    result = LLMBackedAIReviewer(FakeProvider()).review(_context())

    assert result.summary == "One issue"
    assert len(result.findings) == 1
    assert result.findings[0]["file_path"] == "app.py"


def test_llm_reviewer_discards_invalid_file_and_line() -> None:
    response = _valid_response()
    response["findings"] = [
        {**response["findings"][0], "file_path": "other.py"},
        {**response["findings"][0], "line": 99},
    ]

    class FakeProvider:
        def generate_structured_review(self, _context: ReviewContext) -> object:
            return response

    result = LLMBackedAIReviewer(FakeProvider()).review(_context())

    assert result.findings == []


def test_llm_reviewer_handles_malformed_json_and_provider_errors() -> None:
    class MalformedProvider:
        def generate_structured_review(self, _context: ReviewContext) -> object:
            return "not-json"

    class FailingProvider:
        def generate_structured_review(self, _context: ReviewContext) -> object:
            raise TimeoutError("provider timeout")

    malformed = LLMBackedAIReviewer(MalformedProvider()).review(_context())
    failed = LLMBackedAIReviewer(FailingProvider()).review(_context())

    assert malformed.findings == []
    assert failed.findings == []
    assert "TimeoutError" in failed.rationale


def test_configuration_is_disabled_without_explicit_enablement_or_key() -> None:
    assert create_configured_ai_reviewer(
        enabled=False,
        provider="openai-compatible",
        model="test-model",
        api_key=None,
        base_url="https://example.test/v1",
        timeout=1.0,
    ) is None
    assert create_configured_ai_reviewer(
        enabled=True,
        provider="openai-compatible",
        model="test-model",
        api_key=None,
        base_url="https://example.test/v1",
        timeout=1.0,
    ) is None
