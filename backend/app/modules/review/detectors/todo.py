from __future__ import annotations

import re

from backend.app.modules.review.models import DiffLine, ReviewFinding


class TodoMarkerDetector:
    _pattern = re.compile(r"(?<![A-Za-z0-9_])(TODO|FIXME|XXX|HACK)(?![A-Za-z0-9_])")
    _severity = {"TODO": "low", "FIXME": "medium", "XXX": "low", "HACK": "low"}

    def detect(self, lines: list[DiffLine]) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for line in lines:
            match = self._pattern.search(line.content)
            if match:
                marker = match.group(1)
                findings.append(
                    ReviewFinding(
                        category="maintainability",
                        severity=self._severity[marker],
                        file_path=line.file_path,
                        line=line.line_number,
                        message=f"{marker} marker introduced in the change.",
                        explanation="The changed code introduces an unresolved implementation marker.",
                        suggestion="Resolve the marker before merging or create a tracked issue for the remaining work.",
                    )
                )
        return findings
