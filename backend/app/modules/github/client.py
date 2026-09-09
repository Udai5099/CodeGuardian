from __future__ import annotations

from typing import Any

import httpx


class GitHubAPIClient:
    """Thin GitHub API wrapper for repository and pull request operations."""

    def __init__(self, installation_token: str, *, base_url: str = "https://api.github.com") -> None:
        self._token = installation_token
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CodexGuardian",
        }

    def get(self, path: str) -> dict[str, Any] | list[Any]:
        response = httpx.get(f"{self._base_url}{path}", headers=self._headers(), timeout=20.0)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}{path}",
            headers=self._headers(),
            json=payload or {},
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return self.get(f"/repos/{owner}/{repo}")

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        return self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")

    def get_pull_request_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        return self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")

    def get_pull_request_commits(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        return self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")

    def submit_review(self, owner: str, repo: str, pr_number: int, body: str, *, event: str = "COMMENT") -> dict[str, Any]:
        return self.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            {"body": body, "event": event},
        )

    def create_issue_comment(self, owner: str, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        return self.post(f"/repos/{owner}/{repo}/issues/{pr_number}/comments", {"body": body})
