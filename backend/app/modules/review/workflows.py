from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from backend.app.core.events import EventBus
from backend.app.modules.review.models import ReviewFinding, ReviewResult
from backend.app.modules.review.validation import validate_findings

try:
    from langgraph.graph import END, StateGraph
except ImportError as exc:  # pragma: no cover - dependency is required in the runtime environment.
    raise RuntimeError("langgraph is required for the review workflow engine.") from exc


class ReviewWorkflowState(TypedDict, total=False):
    workflow_name: str
    repository_path: str
    repository_id: str
    status: str
    base_sha: str
    head_sha: str
    changed_files: list[str]
    summary: str
    confidence: float
    confidence_reasons: list[str]
    recommendation: str
    decision: str
    findings: list[dict[str, Any]]


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class ReviewWorkflowEngine:
    """Agent-style review workflow backed by a LangGraph state machine."""

    def __init__(
        self,
        event_bus: EventBus,
        repository_service: Any | None = None,
        knowledge_service: Any | None = None,
        review_service: Any | None = None,
        retrieval_service: Any | None = None,
        ai_agent: Any | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._repository_service = repository_service
        self._knowledge_service = knowledge_service
        self._review_service = review_service
        self._retrieval_service = retrieval_service
        self._ai_agent = ai_agent
        self._graph = self.build_graph()

    def build_graph(self):
        graph = StateGraph(dict)

        graph.add_node("repository_indexing", self._repository_indexing)
        graph.add_node("baseline_retrieval", self._baseline_retrieval)
        graph.add_node("diff_review", self._diff_review)
        graph.add_node("confidence_scoring", self._confidence_scoring)
        graph.add_node("decision_gate", self._decision_gate)
        graph.add_node("request_more_context", self._request_more_context)
        graph.add_node("persistence", self._persistence)

        graph.set_entry_point("repository_indexing")
        graph.add_edge("repository_indexing", "baseline_retrieval")
        graph.add_edge("baseline_retrieval", "diff_review")
        graph.add_edge("diff_review", "confidence_scoring")
        graph.add_edge("confidence_scoring", "decision_gate")
        graph.add_conditional_edges(
            "decision_gate",
            self._route_decision,
            {
                "persist": "persistence",
                "request_more_context": "request_more_context",
            },
        )
        graph.add_edge("request_more_context", "persistence")
        graph.add_edge("persistence", END)

        return graph.compile()

    def _repository_indexing(self, state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        result.setdefault("status", "indexed")
        result.setdefault("changed_files", [])
        if "repository_id" not in result and "repository_path" in result:
            result["repository_id"] = result["repository_path"]

        repository_path = result.get("repository_path")
        if repository_path and self._repository_service is not None:
            try:
                analysis = self._repository_service.analyze(repository_path)
                result["repository_name"] = analysis.repository_name
                result["is_dirty"] = analysis.is_dirty
                result["head_commit"] = analysis.head_commit
                if not result.get("changed_files"):
                    result["changed_files"] = [str(repository_path)] if analysis.changed_files > 0 else []
            except Exception:
                pass
        return result

    def _baseline_retrieval(self, state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        result.setdefault("confidence_reasons", [])
        repository_id = result.get("repository_id")
        reasons = list(result["confidence_reasons"])
        if result.get("repository_path") and self._knowledge_service is not None:
            try:
                graph = self._knowledge_service.build(result["repository_path"])
                result["module_count"] = graph.module_count
                result["file_count"] = graph.file_count
                reasons.append(f"Repository graph inspected {graph.file_count} files across {graph.module_count} modules.")
            except Exception:
                reasons.append("Repository graph was unavailable, so the review proceeded with the live repository state.")
        if repository_id:
            reasons.append(f"Repository baseline loaded for {repository_id}.")
        else:
            reasons.append("No repository baseline was available; starting from the live working tree.")
        result["confidence_reasons"] = reasons
        return result

    def _diff_review(self, state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        repository_path = result.get("repository_path")
        changed_files = list(result.get("changed_files") or [])

        if repository_path and self._review_service is not None:
            try:
                review = self._review_service.review_diff(
                    repository_path=repository_path,
                    base_sha=str(result.get("base_sha") or ""),
                    head_sha=str(result.get("head_sha") or ""),
                    changed_files=changed_files,
                )

                result["summary"] = review.summary

                findings = [
                    {
                        "category": finding.category,
                        "severity": finding.severity,
                        "file_path": finding.file_path,
                        "line": finding.line,
                        "message": finding.message,
                        "explanation": finding.explanation,
                        "suggestion": finding.suggestion,
                    }
                    for finding in review.findings
                ]
                result["findings"] = validate_findings(findings, changed_files)

            except Exception:
                pass

        result["changed_files"] = changed_files

        if not result.get("summary"):
            result["summary"] = (
                f"Reviewed {len(changed_files)} changed file(s) against "
                "the supplied base and head commits."
                if changed_files
                else "Reviewed the repository state without a file diff."
            )

        return result

    def _confidence_scoring(self, state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        confidence = 0.45
        reasons = list(result.get("confidence_reasons", []))
        if result.get("repository_id"):
            confidence += 0.25
            reasons.append("The workflow used a repository identity for contextual review.")
        if result.get("base_sha") and result.get("head_sha"):
            confidence += 0.15
            reasons.append("Both the base and head commit SHAs were available for precise comparison.")
        changed_files = result.get("changed_files") or []
        if changed_files:
            confidence += min(0.12, len(changed_files) * 0.02)
            reasons.append(f"The diff included {len(changed_files)} changed file(s).")
        else:
            reasons.append("No diff files were available; verify that commit references are fetched.")

        if self._ai_agent is not None and result.get("repository_path"):
            try:
                ai_context = {
                    "changed_files": len(changed_files),
                    "module_count": result.get("module_count", 0),
                    "file_count": result.get("file_count", 0),
                    "retrieval_results": [],
                }
                if self._retrieval_service is not None:
                    ai_context["retrieval_results"] = [
                        {"content": item.content, "score": item.score}
                        for item in self._retrieval_service.retrieve(result["repository_path"], "review tests fix")
                    ]
                ai_result = self._ai_agent.review(ai_context)
                confidence = float(ai_result.confidence)
                result["ai_result"] = {
                    "agent_name": ai_result.agent_name,
                    "confidence": ai_result.confidence,
                    "suggested_fix": ai_result.suggested_fix,
                    "rationale": ai_result.rationale,
                }
                reasons.append(f"AI review agent reported a {ai_result.confidence} confidence score.")
            except Exception:
                pass

        result["confidence"] = round(min(confidence, 0.95), 2)
        result["confidence_reasons"] = reasons
        result["recommendation"] = "Add focused tests for each changed module before merging."
        return result

    @staticmethod
    def _decision_gate(state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        result.setdefault("decision", "persist")
        return result

    @staticmethod
    def _route_decision(state: dict[str, Any]) -> str:
        confidence = float(state.get("confidence") or 0.0)
        changed_files = state.get("changed_files") or []
        if confidence < 0.6 or not changed_files:
            return "request_more_context"
        return "persist"

    @staticmethod
    def _request_more_context(state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        reasons = list(result.get("confidence_reasons", []))
        reasons.append("Lower confidence triggered a follow-up evidence check before finalizing the review.")
        result["confidence_reasons"] = reasons
        result["status"] = "needs_more_context"
        result["decision"] = "manual_review"
        return result

    @staticmethod
    def _persistence(state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        result["status"] = "completed"
        result.setdefault("workflow_name", "review")
        result.setdefault("decision", "merge_ready")
        result.setdefault("confidence", 0.0)
        return result

    def run(
        self,
        workflow_name: str,
        context: dict[str, Any],
        steps: list[WorkflowStep] | None = None,
    ) -> dict[str, Any]:
        if steps is not None:
            result = dict(context)
            for step in steps:
                result = step.handler(result)
            self._event_bus.publish("review.completed", {"status": result.get("status"), "workflow": workflow_name})
            return result

        graph_state = dict(context)
        graph_state["workflow_name"] = workflow_name
        result = self._graph.invoke(graph_state)
        result["workflow_name"] = workflow_name
        self._event_bus.publish("review.completed", {"status": result.get("status"), "workflow": workflow_name})
        return result
