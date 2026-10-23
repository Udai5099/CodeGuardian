from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any, Protocol

import httpx

from backend.app.modules.review.models import ReviewContext


class LLMProvider(ABC):
    """Abstraction for LLM providers so different backends can be swapped in."""

    @abstractmethod
    def generate_review(self, prompt: str) -> str:
        raise NotImplementedError


class StructuredLLMProvider(Protocol):
    def generate_structured_review(self, context: ReviewContext) -> object: ...


class OpenAICompatibleProvider:
    """HTTP adapter for providers exposing an OpenAI-compatible chat API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def generate_structured_review(self, context: ReviewContext) -> object:
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=self.build_payload(context),
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise ValueError("LLM response content is not structured JSON.")
        return json.loads(content)

    def build_payload(self, context: ReviewContext) -> dict[str, Any]:
        context_payload = {
            "files": [
                {
                    "file_path": file_context.file_path,
                    "language": file_context.language,
                    "added_lines": [
                        {
                            "line_number": line.line_number,
                            "content": line.content,
                        }
                        for line in file_context.added_lines
                    ],
                    "source_excerpt": file_context.source_excerpt,
                }
                for file_context in context.files
            ],
            "deterministic_findings": [
                {
                    "category": finding.category,
                    "severity": finding.severity,
                    "file_path": finding.file_path,
                    "line": finding.line,
                    "message": finding.message,
                    "explanation": finding.explanation,
                    "suggestion": finding.suggestion,
                }
                for finding in context.deterministic_findings
            ],
        }
        return {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Review only the supplied pull-request context. Return JSON with "
                        "summary and findings. Each finding must include category, severity, "
                        "file_path, line, message, explanation, and suggestion."
                    ),
                },
                {"role": "user", "content": json.dumps(context_payload, ensure_ascii=True)},
            ],
        }


class OpenAIProvider(LLMProvider):
    def generate_review(self, prompt: str) -> str:
        return f"OpenAI review for: {prompt}"


class ClaudeProvider(LLMProvider):
    def generate_review(self, prompt: str) -> str:
        return f"Claude review for: {prompt}"


class OllamaProvider(LLMProvider):
    def generate_review(self, prompt: str) -> str:
        return f"Ollama review for: {prompt}"
