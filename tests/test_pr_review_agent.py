import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_pr_agent_reuses_memory_from_a_merged_pr(tmp_path: Path) -> None:
    repo = tmp_path / "agent-repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")

    with TestClient(app) as client:
        stored = client.post(
            "/api/v1/agent/pr-review",
            json={"repository_path": str(repo), "user_id": "test-user", "pull_request_number": 12, "merged": True},
        )
        assert stored.status_code == 200
        assert stored.json()["status"] == "repository-memory-updated"

        base_sha = git(repo, "rev-parse", "HEAD")
        (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        git(repo, "commit", "-am", "change value")
        head_sha = git(repo, "rev-parse", "HEAD")
        reviewed = client.post(
            "/api/v1/agent/pr-review",
            json={
                "repository_path": str(repo),
                "user_id": "test-user",
                "pull_request_number": 13,
                "base_sha": base_sha,
                "head_sha": head_sha,
            },
        )

    assert reviewed.status_code == 200
    payload = reviewed.json()
    assert payload["agent_name"] == "pull-request-review-agent"
    assert payload["baseline_commit"] == base_sha
    assert payload["confidence"] >= 0.7
    assert payload["changed_files"] == ["app.py"]
    assert payload["activity"]["action_count"] == 2
    assert payload["activity"]["last_action"] == "pull-request-reviewed"
