from __future__ import annotations

from pathlib import Path
import subprocess

from backend.app.modules.ai.service import AIAgentResult, MockAIReviewer
from backend.app.modules.agent.memory import InMemoryRepositoryMemoryStore
from backend.app.modules.agent.service import PullRequestReviewAgent
from backend.app.modules.review.models import ReviewContext
from backend.app.modules.review.service import ReviewService


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path, initial: str = "value = 1\n") -> tuple[Path, str, str]:
    repository = tmp_path / "review-repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "Test User")
    _git(repository, "config", "user.email", "test@example.com")
    source = repository / "app.py"
    source.write_text(initial, encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    base_sha = _git(repository, "rev-parse", "HEAD")
    return repository, base_sha, str(source)


def _head(repository: Path, source: str, content: str) -> str:
    Path(source).write_text(content, encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "change")
    return _git(repository, "rev-parse", "HEAD")


def _finding() -> dict[str, object]:
    return {
        "category": "security",
        "severity": "high",
        "file_path": "app.py",
        "line": 2,
        "message": "AI issue",
        "explanation": "The added line needs review.",
        "suggestion": "Use a safer implementation.",
    }


class RecordingReviewer:
    def __init__(self, result: AIAgentResult) -> None:
        self.context: ReviewContext | None = None
        self.result = result

    def review(self, context: ReviewContext) -> AIAgentResult:
        self.context = context
        return self.result


def test_real_review_context_is_passed_to_ai_reviewer(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nnew_value = 2\n")
    reviewer = RecordingReviewer(AIAgentResult("fake", 0.99, "", "", findings=[]))

    ReviewService(ai_reviewer=reviewer).review_diff(
        str(repository), base_sha, head_sha, changed_files=["app.py"]
    )

    assert reviewer.context is not None
    assert reviewer.context.files[0].file_path == "app.py"
    assert reviewer.context.files[0].language == "Python"
    assert reviewer.context.files[0].added_lines[0].line_number == 2
    assert "new_value = 2" in reviewer.context.files[0].source_excerpt


def test_valid_ai_findings_merge_with_deterministic_findings(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nprint(value)\n")
    reviewer = MockAIReviewer({"summary": "AI review", "findings": [_finding()]})
    result = ReviewService(ai_reviewer=reviewer).review_diff(str(repository), base_sha, head_sha)

    assert any(finding.category == "quality" for finding in result.findings)
    assert any(
        finding.category == "security" and finding.message == "AI issue"
        for finding in result.findings
    )


def test_duplicate_ai_and_deterministic_findings_are_emitted_once(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nSECRET_KEY = 'real-value'\n")
    deterministic = ReviewService().review_diff(str(repository), base_sha, head_sha)
    deterministic_finding = next(
        finding for finding in deterministic.findings if finding.category == "security"
    )
    duplicate = AIAgentResult(
        "fake",
        0.0,
        "",
        "",
        findings=[
            {
                "category": deterministic_finding.category,
                "severity": deterministic_finding.severity,
                "file_path": deterministic_finding.file_path,
                "line": deterministic_finding.line,
                "message": deterministic_finding.message,
                "explanation": deterministic_finding.explanation,
                "suggestion": deterministic_finding.suggestion,
            },
            {
                **_finding(),
                "category": "architecture",
                "message": "AI-only architecture issue",
            },
        ],
    )
    result = ReviewService(ai_reviewer=RecordingReviewer(duplicate)).review_diff(
        str(repository), base_sha, head_sha
    )

    deterministic_matches = [
        finding
        for finding in result.findings
        if finding.category == deterministic_finding.category
        and finding.message == deterministic_finding.message
    ]
    unique_ai_matches = [
        finding
        for finding in result.findings
        if finding.category == "architecture"
        and finding.message == "AI-only architecture issue"
    ]
    assert len(deterministic_matches) == 1
    assert len(unique_ai_matches) == 1
    assert len(result.findings) == 2


def test_invalid_ai_findings_do_not_enter_review_result(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nnew_value = 2\n")
    response = {
        "summary": "invalid AI output",
        "findings": [{**_finding(), "category": "not-allowed"}],
    }
    result = ReviewService(ai_reviewer=MockAIReviewer(response)).review_diff(
        str(repository), base_sha, head_sha
    )

    assert all(finding.category != "security" for finding in result.findings)
    assert any(finding.category == "review" for finding in result.findings)


def test_ai_failure_preserves_deterministic_findings(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nprint(value)\n")

    class FailingReviewer:
        def review(self, _context: ReviewContext) -> AIAgentResult:
            raise RuntimeError("AI unavailable")

    result = ReviewService(ai_reviewer=FailingReviewer()).review_diff(
        str(repository), base_sha, head_sha
    )

    assert any(finding.category == "quality" for finding in result.findings)


def test_context_builder_failure_preserves_deterministic_findings(tmp_path: Path, monkeypatch) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nprint(value)\n")

    import backend.app.modules.review.service as review_service_module

    class FailingBuilder:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("context unavailable")

    monkeypatch.setattr(review_service_module, "ReviewContextBuilder", FailingBuilder)
    result = ReviewService(ai_reviewer=MockAIReviewer({"summary": "", "findings": []})).review_diff(
        str(repository), base_sha, head_sha
    )

    assert any(finding.category == "quality" for finding in result.findings)


def test_ai_result_confidence_does_not_control_final_pr_confidence(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nnew_value = 2\n")
    ai_reviewer = RecordingReviewer(AIAgentResult("fake", 0.99, "", "", findings=[]))

    without_ai = PullRequestReviewAgent(
        InMemoryRepositoryMemoryStore(),
        review_service=ReviewService(),
    ).review_pull_request("repo", str(repository), 1, base_sha, head_sha)
    with_ai = PullRequestReviewAgent(
        InMemoryRepositoryMemoryStore(),
        review_service=ReviewService(ai_reviewer=ai_reviewer),
    ).review_pull_request("repo", str(repository), 1, base_sha, head_sha)

    assert ai_reviewer.result.confidence == 0.99
    assert with_ai.confidence == without_ai.confidence


def test_without_ai_reviewer_behavior_remains_deterministic(tmp_path: Path) -> None:
    repository, base_sha, source = _repository(tmp_path)
    head_sha = _head(repository, source, "value = 1\nprint(value)\n")

    result = ReviewService().review_diff(str(repository), base_sha, head_sha)

    assert [finding.category for finding in result.findings] == ["style", "quality"]
