"""Application settings for the modular monolith scaffold."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Simple settings object encapsulating environment-driven configuration."""

    app_name: str = "CodexGuardian"
    debug: bool = True


settings = Settings()
