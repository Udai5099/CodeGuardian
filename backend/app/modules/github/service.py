from __future__ import annotations

from typing import Any

from backend.app.modules.github.auth import get_installation_access_token
from backend.app.modules.github.client import GitHubAPIClient


class GitHubIntegrationService:
    """Coordinate GitHub App authentication and repository/PR access."""

    def __init__(
        self,
        installation_id: str | None = None,
        installation_token: str | None = None,
    ) -> None:
        self.installation_id = installation_id
        self._installation_token = installation_token

    def installation_token(self) -> str:
        if self._installation_token:
            return self._installation_token

        if not self.installation_id:
            raise ValueError("GitHub installation ID is missing.")

        self._installation_token = get_installation_access_token(
            self.installation_id
        )
        return self._installation_token

    def client(self) -> GitHubAPIClient:
        return GitHubAPIClient(self.installation_token())

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return self.client().get_repository(owner, repo)

    def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> dict[str, Any]:
        return self.client().get_pull_request(owner, repo, pr_number)

    def get_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> list[dict[str, Any]]:
        return self.client().get_pull_request_files(owner, repo, pr_number)

    def submit_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        *,
        event: str = "COMMENT",
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.client().submit_review(
            owner,
            repo,
            pr_number,
            body,
            event=event,
            comments=comments,
        )
