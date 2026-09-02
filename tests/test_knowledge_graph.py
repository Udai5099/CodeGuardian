from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_knowledge_graph_endpoint(tmp_path: Path) -> None:
    repo_dir = tmp_path / "kg-repo"
    repo_dir.mkdir()

    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (repo_dir / "tests").mkdir()
    (repo_dir / "tests" / "test_main.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")

    response = client.post(
        "/api/v1/knowledge/graph",
        json={"repository_path": str(repo_dir)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repository_name"] == "kg-repo"
    assert payload["file_count"] >= 2
    assert payload["module_count"] >= 1
