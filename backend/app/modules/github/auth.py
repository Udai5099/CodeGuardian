from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import jwt

from backend.app.core.settings import settings


def _resolve_private_key() -> str:
    private_key = settings.github_app_private_key_contents
    if not private_key:
        raise ValueError("GitHub App private key is not configured. Set GITHUB_APP_PRIVATE_KEY_PATH or GITHUB_APP_PRIVATE_KEY.")
    return private_key


def create_app_jwt() -> str:
    """Create a short-lived JWT signed with the GitHub App private key."""
    if not settings.github_app_id:
        raise ValueError("GitHub App ID is not configured.")

    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    payload = {
        "iat": now - 30,
        "exp": now + 570,
        "iss": settings.github_app_id,
    }
    private_key = _resolve_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_access_token(installation_id: str) -> str:
    """Request an installation token for a specific GitHub App installation."""
    jwt_token = create_app_jwt()
    response = httpx.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CodexGuardian",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise ValueError("GitHub installation token was not returned by the API.")
    return token
