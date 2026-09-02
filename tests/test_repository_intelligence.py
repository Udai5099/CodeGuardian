import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _init_git_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)


def test_repository_analysis_endpoint(tmp_path: Path) -> None:
    repo_dir = tmp_path / "sample-repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    (repo_dir / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True, capture_output=True, text=True)

    (repo_dir / "README.md").write_text("hello\nworld\n", encoding="utf-8")

    response = client.post(
        "/api/v1/repository/analyze",
        json={"repository_path": str(repo_dir)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repository_name"] == "sample-repo"
    assert payload["is_dirty"] is True
    assert payload["changed_files"] >= 1
    assert payload["head_commit"]


def test_workflow_engine_emits_domain_event() -> None:
    from backend.app.core.events import EventBus
    from backend.app.modules.review.workflows import ReviewWorkflowEngine, WorkflowStep

    event_bus = EventBus()
    events: list[str] = []

    def handler(event) -> None:
        events.append(event.data["status"])

    event_bus.subscribe("review.completed", handler)
    workflow = ReviewWorkflowEngine(event_bus)

    result = workflow.run(
        "review",
        {"repository": "demo"},
        steps=[WorkflowStep("inspect", lambda context: {**context, "status": "reviewed"})],
    )

    assert result["status"] == "reviewed"
    assert events == ["reviewed"]
