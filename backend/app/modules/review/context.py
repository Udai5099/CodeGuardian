from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import subprocess

from backend.app.modules.review.diff_analyzer import DiffAnalyzer
from backend.app.modules.review.models import (
    DiffLine,
    ReviewContext,
    ReviewFinding,
    ReviewFileContext,
)


class ReviewContextBuilder:
    """Build bounded, file-focused context from a repository diff."""

    _diff_file_pattern = re.compile(r"^diff --git a/(.+?) b/(.+)$")
    _language_by_suffix = {
        ".c": "C",
        ".cc": "C++",
        ".cpp": "C++",
        ".cs": "C#",
        ".go": "Go",
        ".java": "Java",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".py": "Python",
        ".rb": "Ruby",
        ".rs": "Rust",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".json": "JSON",
        ".md": "Markdown",
    }
    _sensitive_names = {
        "credentials",
        "credentials.json",
        "secret",
        "secrets",
        "id_rsa",
        "id_ed25519",
    }
    _private_key_suffixes = {".crt", ".der", ".key", ".pem", ".p12", ".pfx"}

    def __init__(
        self,
        repository_path: str,
        base_sha: str,
        head_sha: str,
        deterministic_findings: list[ReviewFinding],
        *,
        max_files: int = 20,
        max_source_chars_per_file: int = 12_000,
        max_total_source_chars: int = 50_000,
    ) -> None:
        self.repository_path = Path(repository_path)
        self.base_sha = base_sha
        self.head_sha = head_sha
        self.deterministic_findings = deterministic_findings
        self.max_files = max_files
        self.max_source_chars_per_file = max_source_chars_per_file
        self.max_total_source_chars = max_total_source_chars

    def build(self) -> ReviewContext:
        diff_text = self._git_diff()
        added_lines = self._added_lines_by_file(diff_text)
        changed_files = self._changed_files(diff_text)

        files: list[ReviewFileContext] = []
        total_chars = 0
        for file_path in changed_files:
            if len(files) >= self.max_files or self._is_sensitive(file_path):
                continue
            file_added_lines = added_lines.get(file_path, [])
            if self._is_binary(diff_text, file_path):
                continue

            remaining_chars = self.max_total_source_chars - total_chars
            if remaining_chars <= 0:
                break
            excerpt_limit = min(self.max_source_chars_per_file, remaining_chars)
            source_excerpt = self._source_excerpt(file_path, file_added_lines, excerpt_limit)
            files.append(
                ReviewFileContext(
                    file_path=file_path,
                    language=self._language(file_path),
                    added_lines=file_added_lines,
                    source_excerpt=source_excerpt,
                )
            )
            total_chars += len(source_excerpt)

        return ReviewContext(files=files, deterministic_findings=self.deterministic_findings)

    def _git_diff(self) -> str:
        result = subprocess.run(
            ["git", "diff", "--unified=20", self.base_sha, self.head_sha],
            cwd=self.repository_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    @staticmethod
    def _changed_files(diff_text: str) -> list[str]:
        files: list[str] = []
        for raw_line in diff_text.splitlines():
            match = ReviewContextBuilder._diff_file_pattern.match(raw_line)
            if not match:
                continue
            old_path, new_path = match.groups()
            file_path = new_path if new_path != "/dev/null" else old_path
            if file_path not in files:
                files.append(file_path)
        return files

    @staticmethod
    def _added_lines_by_file(diff_text: str) -> dict[str, list[DiffLine]]:
        lines_by_file: dict[str, list[DiffLine]] = defaultdict(list)
        for line in DiffAnalyzer().parse_added_lines(diff_text):
            lines_by_file[line.file_path].append(line)
        return lines_by_file

    def _source_excerpt(
        self,
        file_path: str,
        added_lines: list[DiffLine],
        limit: int,
    ) -> str:
        if not added_lines:
            return ""
        try:
            source = subprocess.run(
                ["git", "show", f"{self.head_sha}:{file_path}"],
                cwd=self.repository_path,
                capture_output=True,
                check=True,
            ).stdout.decode("utf-8")
        except (OSError, UnicodeDecodeError, subprocess.CalledProcessError):
            return ""

        source_lines = source.splitlines()
        line_numbers = {line.line_number for line in added_lines}
        selected_numbers: set[int] = set()
        for line_number in sorted(line_numbers):
            start = max(1, line_number - 10)
            end = min(len(source_lines), line_number + 10)
            selected_numbers.update(range(start, end + 1))

        excerpt = "\n".join(
            f"{line_number}: {source_lines[line_number - 1]}"
            for line_number in sorted(selected_numbers)
        )
        return excerpt[:limit]

    @classmethod
    def _language(cls, file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        return cls._language_by_suffix.get(suffix, "Text")

    @classmethod
    def _is_sensitive(cls, file_path: str) -> bool:
        path = Path(file_path)
        name = path.name.lower()
        return (
            any(part.lower() == ".git" for part in path.parts)
            or name.startswith(".env")
            or name in cls._sensitive_names
            or path.suffix.lower() in cls._private_key_suffixes
            or "credential" in name
            or "secret" in name
        )

    @staticmethod
    def _is_binary(diff_text: str, file_path: str) -> bool:
        return any(
            raw_line.startswith("Binary files ") and file_path in raw_line
            for raw_line in diff_text.splitlines()
        )