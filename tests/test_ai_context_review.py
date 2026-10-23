from __future__ import annotations

from backend.app.modules.ai.service import ContextAwareAIReviewer, MockAIReviewer
from backend.app.modules.review.models import DiffLine, ReviewContext, ReviewFileContext


def _context() -> ReviewContext:
    return ReviewContext(
        files=[
            ReviewFileContext(
                file_path="app.py",
                language="Python",
                added_lines=[DiffLine("app.py", 3, "print(value)")],
                source_excerpt="1: value = 1\n3: print(value)",
            )
        ],
        deterministic_findings=[],
    )


def _finding(**overrides: object) -> dict[str, object]:
    finding: dict[str, object] = {
        "category": "quality",
        "severity": "low",
        "file_path": "app.py",
        "line": 3,
        "message": "Debug output detected.",
        "explanation": "The added line writes directly to stdout.",
        "suggestion": "Use the project logger.",
    }
    finding.update(overrides)
    return finding


def test_real_review_context_reaches_ai_reviewer_and_valid_finding_survives() -> None:
    received: list[ReviewContext] = []

    def responder(context: ReviewContext) -> dict[str, object]:
        received.append(context)
        return {"summary": "One quality issue", "findings": [_finding()]}

    result = ContextAwareAIReviewer(responder).review(_context())

    assert received == [_context()]
    assert result.summary == "One quality issue"
    assert result.findings == [_finding()]
    assert result.confidence == 0.0


def test_invalid_category_severity_file_and_line_are_discarded() -> None:
    response = {
        "summary": "Review completed",
        "findings": [
            _finding(category="unknown"),
            _finding(severity="urgent"),
            _finding(file_path="other.py"),
            _finding(line=4),
            _finding(),
        ],
    }

    result = MockAIReviewer(response).review(_context())

    assert result.findings == [_finding()]


def test_malformed_ai_output_is_handled_safely() -> None:
    reviewer = MockAIReviewer({"summary": "missing findings"})

    result = reviewer.review(_context())

    assert result.findings == []
    assert result.summary == ""
    assert "malformed" in result.rationale


def test_ai_failure_does_not_raise() -> None:
    def failing_responder(_context: ReviewContext) -> object:
        raise RuntimeError("provider unavailable")

    result = ContextAwareAIReviewer(failing_responder).review(_context())

    assert result.findings == []
    assert result.confidence == 0.0
    assert "RuntimeError" in result.rationale
