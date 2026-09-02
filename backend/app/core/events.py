from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class DomainEvent:
    """Simple domain event for intra-process communication."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Minimal event bus for the modular monolith scaffold."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[DomainEvent], None]]] = {}

    def subscribe(self, event_name: str, handler: Callable[[DomainEvent], None]) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def publish(self, event_name: str, data: dict[str, Any] | None = None) -> None:
        event = DomainEvent(name=event_name, data=data or {})
        for handler in self._handlers.get(event_name, []):
            handler(event)
