from __future__ import annotations

import re

from backend.app.modules.review.models import DiffLine, ReviewFinding


from backend.app.modules.review.detectors import (
    BroadExceptionDetector,
    DebugDetector,
    HardCodedSecretDetector,
    TodoMarkerDetector,
    UnsafeSubprocessDetector,
)


class DiffAnalyzer:
    _hunk_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

    def __init__(self) -> None:
        self._detectors = (
            DebugDetector(),
            TodoMarkerDetector(),
            BroadExceptionDetector(),
            HardCodedSecretDetector(),
            UnsafeSubprocessDetector(),
        )

    def parse_added_lines(self, diff_text: str) -> list[DiffLine]:
        file_path: str | None = None
        next_line_number: int | None = None
        added_lines: list[DiffLine] = []

        for raw_line in diff_text.splitlines():
            if raw_line.startswith("+++ "):
                file_path = raw_line[6:] if raw_line.startswith("+++ b/") else raw_line[4:]
                if file_path == "/dev/null":
                    file_path = None
                continue

            hunk = self._hunk_pattern.match(raw_line)
            if hunk:
                next_line_number = int(hunk.group(1))
                continue

            if file_path is None or next_line_number is None:
                continue

            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                added_lines.append(DiffLine(file_path, next_line_number, raw_line[1:]))
                next_line_number += 1
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                continue
            else:
                next_line_number += 1

        return added_lines

    def analyze(self, diff_text: str) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        lines = self.parse_added_lines(diff_text)
        for detector in self._detectors:
            findings.extend(detector.detect(lines))
        return self._deduplicate(findings)

    @staticmethod
    def _deduplicate(findings: list[ReviewFinding]) -> list[ReviewFinding]:
        unique: list[ReviewFinding] = []
        seen: set[tuple[str, str | None, int | None, str]] = set()
        for finding in findings:
            identity = (finding.category, finding.file_path, finding.line, finding.message)
            if identity not in seen:
                seen.add(identity)
                unique.append(finding)
        return unique
