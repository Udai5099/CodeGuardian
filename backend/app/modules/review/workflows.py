from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from backend.app.core.events import EventBus


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class ReviewWorkflowEngine:
    """A simple workflow engine that publishes a domain event at the end."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def run(
        self,
        workflow_name: str,
        context: dict[str, Any],
        steps: list[WorkflowStep] | None = None,
    ) -> dict[str, Any]:
        steps = steps or []
        result = dict(context)
        for step in steps:
            result = step.handler(result)

        self._event_bus.publish("review.completed", {"status": result.get("status"), "workflow": workflow_name})
        return result
