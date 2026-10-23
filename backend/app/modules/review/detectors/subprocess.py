from __future__ import annotations

import re

from backend.app.modules.review.models import DiffLine, ReviewFinding


class UnsafeSubprocessDetector:
    _shell_pattern = re.compile(r"\b(?:subprocess\.(?:run|Popen)|subprocess\.call)\s*\([^\n]*\bshell\s*=\s*True\b")
    _system_pattern = re.compile(r"\bos\.system\s*\(")

    def detect(self, lines: list[DiffLine]) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for line in lines:
            if not (self._shell_pattern.search(line.content) or self._system_pattern.search(line.content)):
                continue
            findings.append(
                ReviewFinding(
                    category="security",
                    severity="high",
                    file_path=line.file_path,
                    line=line.line_number,
                    message="Potentially unsafe shell command execution detected.",
                    explanation="Executing dynamically constructed commands through a shell can expose the application to command injection.",
                    suggestion="Prefer argument arrays with shell execution disabled and validate untrusted input.",
                )
            )
        return findings
