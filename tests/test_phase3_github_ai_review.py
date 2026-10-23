from __future__ import annotations

from pathlib import Path
import subprocess

from backend.app.main import app, run_pull_request_agent
from backend.app.modules.ai.service import AIAgentResult
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


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "github-review-repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "Test User")
    _git(repository, "config", "user.email", "test@example.com")
    source = repository / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    base_sha = _git(repository, "rev-parse", "HEAD")
    source.write_text("value = 1\nprint(value)\n", encoding="utf-8")
    _git(repository, "commit", "-am", "change")
    head_sha = _git(repository, "rev-parse", "HEAD")
    return repository, base_sha, head_sha


class RecordingReviewer:
    def __init__(self, result: AIAgentResult) -> None:
        self.result = result
        self.context: ReviewContext | None = None

    def review(self, context: ReviewContext) -> AIAgentResult:
        self.context = context
        return self.result


def _ai_finding() -> dict[str, object]:
    return {
        "category": "architecture",
        "severity": "medium",
        "file_path": "app.py",
        "line": 2,
        "message": "AI architecture issue",
        "explanation": "The added code should follow the repository boundary.",
        "suggestion": "Move this behavior into the service layer.",
    }


def _configure_local_review(monkeypatch, repository: Path, reviewer: RecordingReviewer) -> None:
    review_service = ReviewService(ai_reviewer=reviewer)
    monkeypatch.setattr(
        app.state.repository_service,
        "resolve_github_repository",
        lambda **_kwargs: str(repository),
    )
    monkeypatch.setattr(
        app.state.vector_service,
        "index_repository",
        lambda _repository_id, _repository_path: 0,
    )
    monkeypatch.setattr(
        app.state,
        "pr_review_agent",
        PullRequestReviewAgent(
            InMemoryRepositoryMemoryStore(),
            review_service=review_service,
        ),
    )


def test_github_review_path_passes_context_to_ai_and_publishes_merged_findings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository, base_sha, head_sha = _repository(tmp_path)
    reviewer = RecordingReviewer(
        AIAgentResult("fake", 0.99, "", "", findings=[_ai_finding()])
    )
    _configure_local_review(monkeypatch, repository, reviewer)
    published: dict[str, object] = {}

    def fake_submit(self, owner, repo, pr_number, body, *, event="COMMENT", comments=None):
        published.update({"owner": owner, "repo": repo, "body": body, "comments": comments})
        return {"id": 12, "html_url": "https://github.test/review/12"}

    monkeypatch.setattr("backend.app.modules.github.service.GitHubIntegrationService.submit_review", fake_submit)

    response = run_pull_request_agent(
        {
            "repository_url": "https://github.com/example/project",
            "installation_id": "123",
            "installation_token": "test-installation-token",
            "pull_request_number": 4,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
    )

    assert reviewer.context is not None
    assert reviewer.context.files[0].file_path == "app.py"
    assert any(finding["message"] == "AI architecture issue" for finding in response["findings"])
    assert any(finding["category"] == "quality" for finding in response["findings"])
    assert published["owner"] == "example"
    assert published["repo"] == "project"
    assert any(comment["path"] == "app.py" and comment["line"] == 2 for comment in published["comments"])


def test_ai_failure_still_publishes_deterministic_review(tmp_path: Path, monkeypatch) -> None:
    repository, base_sha, head_sha = _repository(tmp_path)

    class FailingReviewer:
        def review(self, _context: ReviewContext) -> AIAgentResult:
            raise TimeoutError("provider timeout")

    _configure_local_review(monkeypatch, repository, RecordingReviewer(AIAgentResult("unused", 0, "", "", [])))
    monkeypatch.setattr(
        app.state,
        "pr_review_agent",
        PullRequestReviewAgent(
            InMemoryRepositoryMemoryStore(),
            review_service=ReviewService(ai_reviewer=FailingReviewer()),
        ),
    )
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        "backend.app.modules.github.service.GitHubIntegrationService.submit_review",
        lambda self, owner, repo, pr_number, body, *, event="COMMENT", comments=None: published.append(
            {"body": body, "comments": comments}
        ) or {"id": 13, "html_url": "https://github.test/review/13"},
    )

    response = run_pull_request_agent(
        {
            "repository_url": "https://github.com/example/project",
            "installation_id": "123",
            "installation_token": "test-installation-token",
            "pull_request_number": 5,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
    )

    assert any(finding["category"] == "quality" for finding in response["findings"])
    assert len(published) == 1


def test_invalid_ai_location_does_not_create_inline_comment(tmp_path: Path, monkeypatch) -> None:
    repository, base_sha, head_sha = _repository(tmp_path)
    invalid_finding = {**_ai_finding(), "file_path": "other.py", "line": 99}
    _configure_local_review(
        monkeypatch,
        repository,
        RecordingReviewer(AIAgentResult("fake", 0.0, "", "", findings=[invalid_finding])),
    )
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        "backend.app.modules.github.service.GitHubIntegrationService.submit_review",
        lambda self, owner, repo, pr_number, body, *, event="COMMENT", comments=None: published.append(
            {"body": body, "comments": comments}
        ) or {"id": 14, "html_url": "https://github.test/review/14"},
    )

    response = run_pull_request_agent(
        {
            "repository_url": "https://github.com/example/project",
            "installation_id": "123",
            "installation_token": "test-installation-token",
            "pull_request_number": 6,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
    )

    assert all(finding["message"] != "AI architecture issue" for finding in response["findings"])
    comments = published[0]["comments"]
    assert all(not (comment["path"] == "other.py" and comment["line"] == 99) for comment in comments)
    assert any(comment["path"] == "app.py" and comment["line"] == 2 for comment in comments)
