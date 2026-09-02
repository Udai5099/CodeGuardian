from backend.app.infrastructure.database import DatabaseConfig, DatabaseConnection
from backend.app.modules.ai.providers import ClaudeProvider, OllamaProvider, OpenAIProvider


def test_database_config_defaults() -> None:
    conn = DatabaseConnection()
    assert conn.config.name == "codexguardian"
    assert conn.config.port == 5432


def test_llm_provider_abstraction() -> None:
    providers = [OpenAIProvider(), ClaudeProvider(), OllamaProvider()]
    reviews = [provider.generate_review("demo") for provider in providers]
    assert len(reviews) == 3
    assert "demo" in reviews[0]
