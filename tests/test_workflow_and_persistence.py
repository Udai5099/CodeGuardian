from backend.app.modules.review.repository import ReviewRecord, ReviewRepository
from backend.app.modules.review.workflows import ReviewWorkflowEngine, WorkflowStep
from backend.app.core.events import EventBus


def test_review_repository_persists_records() -> None:
    repository = ReviewRepository()
    record = ReviewRecord(review_id="review-42", summary="pending", findings=[{"category": "style", "message": "ok"}])
    repository.save(record)
    assert repository.list()[0].review_id == "review-42"


def test_review_workflow_engine_emits_event() -> None:
    event_bus = EventBus()
    events: list[str] = []

    def handler(event) -> None:
        events.append(event.name)

    event_bus.subscribe("review.completed", handler)
    workflow = ReviewWorkflowEngine(event_bus)
    workflow.run("review", {"status": "done"}, steps=[WorkflowStep("noop", lambda ctx: {**ctx, "status": "done"})])
    assert events == ["review.completed"]
