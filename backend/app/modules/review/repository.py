from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.infrastructure.database import DatabaseConnection


@dataclass
class ReviewRecord:
    review_id: str
    summary: str
    findings: list[dict[str, Any]]


class ReviewRepository:
    """A simple persistence boundary for review records."""

    def __init__(self, connection: DatabaseConnection | None = None) -> None:
        self._connection = connection or DatabaseConnection()
        self._records: list[ReviewRecord] = []

    def save(self, record: ReviewRecord) -> None:
        self._records.append(record)

    def list(self) -> list[ReviewRecord]:
        return list(self._records)
