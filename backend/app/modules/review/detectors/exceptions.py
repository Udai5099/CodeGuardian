from __future__ import annotations

import re

from backend.app.modules.review.models import DiffLine, ReviewFinding


class BroadExceptionDetector:
    _broad_pattern = re.compile(r"^\s*except(?:\s+Exception)?\s*:")

    def detect(self, lines: list[DiffLine]) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for index, line in enumerate(lines):
            if not self._broad_pattern.search(line.content):
                continue
            swallowed = any(
                candidate.content.strip() in {"pass", "..."}
                for candidate in lines[index + 1 : index + 3]
                if candidate.file_path == line.file_path
                and candidate.line_number > line.line_number
            )
            severity = "high" if swallowed else "medium"
            explanation = (
                "The broad exception handler can swallow unexpected failures and make debugging difficult."
                if swallowed
                else "Catching broad exceptions can hide unexpected failures and make debugging difficult."
            )
            findings.append(
                ReviewFinding(
                    category="correctness",
                    severity=severity,
                    file_path=line.file_path,
                    line=line.line_number,
                    message="Broad exception handling detected.",
                    explanation=explanation,
                    suggestion="Catch the specific exceptions that the operation is expected to raise and handle them explicitly.",
                )
            )
        return findings
