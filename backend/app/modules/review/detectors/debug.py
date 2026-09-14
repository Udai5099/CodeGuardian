from __future__ import annotations

import re

from backend.app.modules.review.models import DiffLine, ReviewFinding


class DebugDetector:
    _patterns = (
        re.compile(r"\bprint\s*\("),
        re.compile(r"\bconsole\.log\s*\("),
        re.compile(r"\bSystem\.out\.println\s*\("),
        re.compile(r"\bfmt\.Println\s*\("),
    )

    def detect(self, lines: list[DiffLine]) -> list[ReviewFinding]:
        return [
            ReviewFinding(
                category="quality",
                severity="low",
                file_path=line.file_path,
                line=line.line_number,
                message="Debug print statement detected.",
                explanation="The changed line writes diagnostic output directly to stdout.",
                suggestion="Remove the debug statement or replace it with the project's logging mechanism.",
            )
            for line in lines
            if any(pattern.search(line.content) for pattern in self._patterns)
        ]
