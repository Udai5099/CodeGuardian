from __future__ import annotations

import re

from backend.app.modules.review.models import DiffLine, ReviewFinding


class HardCodedSecretDetector:
    _assignment = re.compile(
        r"\b(?:API_KEY|SECRET_KEY|PASSWORD|TOKEN|AWS_ACCESS_KEY_ID)\b\s*=\s*([\"'])(?P<value>[^\"']+)\1"
    )
    _placeholders = {
        "your_api_key",
        "replace-me",
        "example-token",
        "changeme",
        "test",
    }

    def detect(self, lines: list[DiffLine]) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for line in lines:
            match = self._assignment.search(line.content)
            if not match:
                continue
            value = match.group("value").strip()
            normalized = value.lower()
            if normalized in self._placeholders or value.startswith("<") or value.endswith(">"):
                continue
            findings.append(
                ReviewFinding(
                    category="security",
                    severity="high",
                    file_path=line.file_path,
                    line=line.line_number,
                    message="Potential hard-coded secret detected.",
                    explanation="The changed line appears to contain a credential-like value directly in source code.",
                    suggestion="Move the secret to an environment variable or a dedicated secret manager.",
                )
            )
        return findings
