from dataclasses import dataclass
from pathlib import Path
import subprocess

from backend.app.main import build_github_inline_comments, build_github_review_body
from backend.app.modules.review.validation import validate_findings


@dataclass
class Review:
    summary: str
    confidence: float
    findings: list[dict[str, object]]
    recommendation: str


def test_validation_rejects_malformed_or_unchanged_file_findings() -> None:
    findings = [
        {
            "category": "security",
            "severity": "high",
            "file_path": "changed.py",
            "line": 4,
            "message": "Secret",
            "explanation": "Credential-like value.",
            "suggestion": "Use a secret manager.",
        },
        {
            "category": "unknown",
            "severity": "high",
            "file_path": "changed.py",
            "line": 4,
            "message": "Bad",
            "explanation": "Bad category.",
            "suggestion": None,
        },
        {
            "category": "quality",
            "severity": "low",
            "file_path": "unchanged.py",
            "line": 4,
            "message": "Bad location",
            "explanation": "Not part of this change.",
            "suggestion": None,
        },
    ]

    assert validate_findings(findings, ["changed.py"]) == findings[:1]


def test_github_review_body_contains_structured_finding_details() -> None:
    body = build_github_review_body(
        Review(
            summary="1 file changed",
            confidence=0.91,
            findings=[
                {
                    "category": "security",
                    "severity": "high",
                    "file_path": "config.py",
                    "line": 12,
                    "message": "Potential hard-coded secret detected.",
                    "explanation": "The changed line appears to contain a credential-like value.",
                    "suggestion": "Move the secret to an environment variable.",
                }
            ],
            recommendation="Add focused tests.",
        )
    )

    assert "HIGH — Security" in body
    assert "`config.py:12`" in body
    assert "credential-like value" in body
    assert "**Suggestion:** Move the secret" in body


def test_inline_comments_only_target_added_lines(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    source.write_text("value = 1\nprint(value)\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, check=True, capture_output=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    comments = build_github_inline_comments(
        Review(
            summary="1 file changed",
            confidence=0.9,
            findings=[
                {
                    "category": "quality",
                    "severity": "low",
                    "file_path": "app.py",
                    "line": 2,
                    "message": "Debug print statement detected.",
                    "explanation": "Writes diagnostic output.",
                    "suggestion": "Use logging.",
                },
                {
                    "category": "quality",
                    "severity": "low",
                    "file_path": "app.py",
                    "line": 1,
                    "message": "Unchanged line.",
                    "explanation": "Not in the added diff.",
                    "suggestion": None,
                },
            ],
            recommendation="Add focused tests.",
        ),
        str(tmp_path),
        base_sha,
        head_sha,
    )

    assert len(comments) == 1
    assert comments[0]["path"] == "app.py"
    assert comments[0]["line"] == 2
    assert comments[0]["side"] == "RIGHT"
