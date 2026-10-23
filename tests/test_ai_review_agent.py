import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.modules.agent.memory import InMemoryRepositoryMemoryStore
from backend.app.modules.agent.service import PullRequestReviewAgent
from backend.app.modules.ai.service import AIAgentResult


client = TestClient(app)


def _init_git_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)


def test_ai_review_agent_suggests_fix(tmp_path: Path) -> None:
    repo_dir = tmp_path / "ai-review-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True, capture_output=True, text=True)

    (repo_dir / "src" / "main.py").write_text("print('hello world')\n", encoding="utf-8")

    response = client.post(
        "/api/v1/review/ai",
        json={"repository_path": str(repo_dir)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_name"] == "heuristic-review-agent"
    assert payload["confidence"] >= 0.0
    assert payload["suggested_fix"]


class HighConfidenceAI:
    def review(self, context: dict[str, object]) -> AIAgentResult:
        assert context["module_count"] == 0
        assert context["file_count"] == 0
        assert context["retrieval_results"] == []
        return AIAgentResult("synthetic-ai", 0.99, "synthetic", "synthetic")


def test_synthetic_empty_ai_context_does_not_increase_pr_confidence(tmp_path: Path) -> None:
    repo_dir = tmp_path / "confidence-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    source = repo_dir / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True, capture_output=True, text=True)
    source.write_text("value = 2\n", encoding="utf-8")

    without_ai = PullRequestReviewAgent(InMemoryRepositoryMemoryStore())
    with_ai = PullRequestReviewAgent(InMemoryRepositoryMemoryStore(), ai_agent=HighConfidenceAI())

    baseline = without_ai.review_pull_request("repo", str(repo_dir), 1)
    candidate = with_ai.review_pull_request("repo", str(repo_dir), 1)

    assert candidate.confidence == baseline.confidence
