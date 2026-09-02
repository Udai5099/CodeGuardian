import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _init_git_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)


def test_review_ai_uses_retrieval_context(tmp_path: Path) -> None:
    repo_dir = tmp_path / "review-rag-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    (repo_dir / "docs").mkdir()
    (repo_dir / "docs" / "guide.md").write_text("The project uses Python and tests.\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True, capture_output=True, text=True)

    response = client.post(
        "/api/v1/review/ai",
        json={"repository_path": str(repo_dir)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] >= 0.0
    assert payload["rationale"]
