from __future__ import annotations

from typing import Protocol

from backend.app.modules.review.models import DiffLine, ReviewFinding


class DiffDetector(Protocol):
    def detect(self, lines: list[DiffLine]) -> list[ReviewFinding]: ...
