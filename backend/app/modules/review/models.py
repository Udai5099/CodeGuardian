from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewFinding:
    category: str
    severity: str = "info"
    file_path: str | None = None
    line: int | None = None
    message: str = ""
    explanation: str = ""
    suggestion: str | None = None


@dataclass(frozen=True)
class ReviewResult:
    review_id: str
    summary: str
    findings: list[ReviewFinding]


@dataclass(frozen=True)
class DiffLine:
    file_path: str
    line_number: int
    content: str


@dataclass(frozen=True)
class ReviewFileContext:
    file_path: str
    language: str
    added_lines: list[DiffLine]
    source_excerpt: str


@dataclass(frozen=True)
class ReviewContext:
    files: list[ReviewFileContext]
    deterministic_findings: list[ReviewFinding]
