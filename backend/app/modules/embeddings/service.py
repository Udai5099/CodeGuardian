from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RetrievalResult:
    content: str
    score: float


class EmbeddingRetrievalService:
    """Simple retrieval service over text files for the RAG layer."""

    def retrieve(self, repository_path: str, query: str) -> list[RetrievalResult]:
        repo_path = Path(repository_path)
        results: list[RetrievalResult] = []
        normalized_query = query.lower()
        terms = [term for term in normalized_query.split() if term]
        for file_path in sorted(repo_path.rglob("*")):
            if not file_path.is_file() or any(part in {".git", "__pycache__"} for part in file_path.parts):
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            normalized_content = content.lower()
            match_count = sum(1 for term in terms if term in normalized_content)
            if match_count > 0:
                score = min(1.0, round(match_count / max(1, len(terms)), 2))
                results.append(RetrievalResult(content=content[:200], score=score))
        return sorted(results, key=lambda item: item.score, reverse=True)
