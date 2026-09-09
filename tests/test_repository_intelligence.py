import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def test_github_webhook_alias_route_is_registered() -> None:
    response = client.post(
        "/api/v1/github/webhook",
        json={"action": "opened"},
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    assert response.status_code != 404


def test_github_oauth_callback_route_is_registered(monkeypatch) -> None:
    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "gho_example_token", "token_type": "bearer", "scope": "repo"}

    def fake_post(url, data=None, headers=None, timeout=None):
        assert url == "https://github.com/login/oauth/access_token"
        assert data["client_id"] == "test-client-id"
        assert data["client_secret"] == "test-client-secret"
        assert data["code"] == "test-code"
        assert data["redirect_uri"]
        assert timeout == 15.0
        return DummyResponse()

    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GITHUB_OAUTH_REDIRECT_URL", "https://example.test/api/v1/github/callback")
    monkeypatch.setattr("httpx.post", fake_post)

    auth_response = client.get("/api/v1/github/authorize", follow_redirects=False)
    assert auth_response.status_code in {301, 302, 307, 308}
    location = auth_response.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    response = client.get(f"/api/v1/github/callback?code=test-code&state={state}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "oauth-success"
    assert payload["token_received"] is True
    assert payload["token_type"] == "bearer"
    assert payload["scope"] == "repo"
    assert "access_token" not in payload
