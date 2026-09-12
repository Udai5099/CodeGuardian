from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any, Callable, Protocol

from backend.app.modules.review.models import ReviewContext
from backend.app.modules.review.validation import validate_context_findings


@dataclass(frozen=True)
class AIAgentResult:
    agent_name: str
    confidence: float
    suggested_fix: str
    rationale: str
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)


class DiffAwareAIReviewer(Protocol):
    """Contract for AI reviewers that reason over the actual review context."""

    def review(self, context: ReviewContext) -> AIAgentResult: ...


class ContextAwareAIReviewer:
    """Adapt a structured AI response to the validated review contract."""

    def __init__(
        self,
        responder: Callable[[ReviewContext], object],
        *,
        agent_name: str = "context-aware-ai-reviewer",
    ) -> None:
        self._responder = responder
        self._agent_name = agent_name

    def review(self, context: ReviewContext) -> AIAgentResult:
        try:
            response = self._responder(context)
        except Exception as error:
            return AIAgentResult(
                agent_name=self._agent_name,
                confidence=0.0,
                suggested_fix="",
                rationale=f"AI review failed safely: {type(error).__name__}.",
                summary="",
                findings=[],
            )

        if not isinstance(response, dict):
            return self._empty_result("AI review returned malformed output.")

        summary = response.get("summary")
        raw_findings = response.get("findings")
        if not isinstance(summary, str) or not isinstance(raw_findings, list):
            return self._empty_result("AI review returned malformed output.")

        findings = validate_context_findings(raw_findings, context)
        return AIAgentResult(
            agent_name=self._agent_name,
            confidence=0.0,
            suggested_fix="",
            rationale="AI findings were validated against the supplied review context.",
            summary=summary,
            findings=findings,
        )

    def _empty_result(self, rationale: str) -> AIAgentResult:
        return AIAgentResult(
            agent_name=self._agent_name,
            confidence=0.0,
            suggested_fix="",
            rationale=rationale,
            summary="",
            findings=[],
        )


class MockAIReviewer(ContextAwareAIReviewer):
    """Deterministic, offline reviewer for contract and integration tests."""

    def __init__(self, response: object) -> None:
        super().__init__(lambda _context: response, agent_name="mock-ai-reviewer")


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
