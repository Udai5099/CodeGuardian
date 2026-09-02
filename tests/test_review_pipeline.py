import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _init_git_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)


def test_diff_review_pipeline(tmp_path: Path) -> None:
    repo_dir = tmp_path / "review-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    (repo_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True, capture_output=True, text=True)

    (repo_dir / "app.py").write_text("print('hello world')\n", encoding="utf-8")

    response = client.post(
        "/api/v1/review/diff",
        json={"repository_path": str(repo_dir)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_id"]
    assert payload["summary"] == "1 file changed"
    assert payload["findings"][0]["category"] == "style"
