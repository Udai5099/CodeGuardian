from __future__ import annotations

from typing import Any, Iterable

from backend.app.modules.review.models import ReviewContext

ALLOWED_CATEGORIES = {
    "security",
    "correctness",
    "performance",
    "maintainability",
    "style",
    "testing",
    "architecture",
    "quality",
    "review",
}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}


def validate_finding(finding: Any, changed_files: Iterable[str]) -> bool:
    if not isinstance(finding, dict):
        return False
    if finding.get("category") not in ALLOWED_CATEGORIES:
        return False
    if finding.get("severity") not in ALLOWED_SEVERITIES:
        return False
    if not isinstance(finding.get("message"), str) or not finding["message"].strip():
        return False
    if not isinstance(finding.get("explanation"), str) or not finding["explanation"].strip():
        return False

    file_path = finding.get("file_path")
    if file_path is not None and file_path not in set(changed_files):
        return False

    line = finding.get("line")
    if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
        return False

    suggestion = finding.get("suggestion")
    return suggestion is None or isinstance(suggestion, str)


def validate_findings(
    findings: Iterable[dict[str, Any]],
    changed_files: Iterable[str],
) -> list[dict[str, Any]]:
    changed_file_list = list(changed_files)
    return [
        finding
        for finding in findings
        if validate_finding(finding, changed_file_list)
    ]


def validate_context_findings(
    findings: Iterable[Any],
    context: ReviewContext,
) -> list[dict[str, Any]]:
    """Keep only findings that point to actual files and added diff lines."""
    added_lines_by_file = {
        file_context.file_path: {line.line_number for line in file_context.added_lines}
        for file_context in context.files
    }
    valid: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        file_path = finding.get("file_path")
        line = finding.get("line")
        if (
            not isinstance(file_path, str)
            or not isinstance(line, int)
            or isinstance(line, bool)
            or line not in added_lines_by_file.get(file_path, set())
        ):
            continue
        if validate_finding(finding, added_lines_by_file):
            valid.append(finding)
    return valid
