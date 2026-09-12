"""Application settings for the modular monolith scaffold."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


@dataclass(frozen=True)
class Settings:
    """Simple settings object encapsulating environment-driven configuration."""

    app_name: str = os.getenv("APP_NAME", "CodexGuardian")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    redis_url: str | None = os.getenv("REDIS_URL")
    database_url: str | None = os.getenv("DATABASE_URL")
    github_webhook_secret: str | None = os.getenv("GITHUB_WEBHOOK_SECRET")
    github_app_id: str | None = os.getenv("GITHUB_APP_ID")
    github_client_id: str | None = os.getenv("GITHUB_CLIENT_ID")
    github_client_secret: str | None = os.getenv("GITHUB_CLIENT_SECRET")
    github_oauth_redirect_url: str | None = os.getenv("GITHUB_OAUTH_REDIRECT_URL")
    github_app_private_key_path: str | None = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
    github_app_private_key: str | None = os.getenv("GITHUB_APP_PRIVATE_KEY")
    review_background_enabled: bool = os.getenv("REVIEW_BACKGROUND_ENABLED", "false").lower() == "true"
    ai_review_enabled: bool = os.getenv("AI_REVIEW_ENABLED", "false").lower() == "true"
    ai_provider: str = os.getenv("AI_PROVIDER", "openai-compatible")
    ai_model: str = os.getenv("AI_MODEL", "gpt-4o-mini")
    ai_api_key: str | None = os.getenv("AI_API_KEY")
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    ai_timeout: float = float(os.getenv("AI_TIMEOUT", "30"))

    @property
    def github_app_private_key_contents(self) -> str | None:
        configured_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") or self.github_app_private_key_path
        if configured_path:
            candidate = configured_path
            if not os.path.isabs(candidate):
                candidate = str(Path(__file__).resolve().parents[3] / candidate)
            try:
                return Path(candidate).read_text(encoding="utf-8")
            except OSError:
                pass
        return os.getenv("GITHUB_APP_PRIVATE_KEY") or self.github_app_private_key


settings = Settings()
