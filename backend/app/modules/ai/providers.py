from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstraction for LLM providers so different backends can be swapped in."""

    @abstractmethod
    def generate_review(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    def generate_review(self, prompt: str) -> str:
        return f"OpenAI review for: {prompt}"


class ClaudeProvider(LLMProvider):
    def generate_review(self, prompt: str) -> str:
        return f"Claude review for: {prompt}"


class OllamaProvider(LLMProvider):
    def generate_review(self, prompt: str) -> str:
        return f"Ollama review for: {prompt}"
