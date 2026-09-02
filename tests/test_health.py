from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_review_health_endpoint() -> None:
    response = client.get("/api/v1/review/health")
    assert response.status_code == 200
    assert response.json() == {"status": "review-module-ready"}


def test_module_registry_endpoint() -> None:
    response = client.get("/api/v1/system/modules")
    assert response.status_code == 200
    payload = response.json()
    assert "modules" in payload
    assert "review" in payload["modules"]
    assert "repository" in payload["modules"]
