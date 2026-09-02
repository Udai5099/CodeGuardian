from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AIAgentResult:
    agent_name: str
    confidence: float
    suggested_fix: str
    rationale: str


class HeuristicReviewAgent:
    """A lightweight AI-style review agent that uses heuristics and repository context."""

    def review(self, repository_context: dict[str, Any]) -> AIAgentResult:
        changed_files = repository_context.get("changed_files", 0)
        module_count = repository_context.get("module_count", 0)
        file_count = repository_context.get("file_count", 0)
        retrieval_results = repository_context.get("retrieval_results", [])

        confidence = min(0.95, 0.35 + (changed_files * 0.1) + (module_count * 0.03) + (file_count * 0.01))
        suggested_fix = "Consider documenting the change and adding focused tests for the affected module."
        rationale = (
            f"The repository has {file_count} files and {module_count} modules; "
            f"the change set spans {changed_files} files, and retrieval surfaced {len(retrieval_results)} relevant context items."
        )

        return AIAgentResult(
            agent_name="heuristic-review-agent",
            confidence=round(confidence, 2),
            suggested_fix=suggested_fix,
            rationale=rationale,
        )
