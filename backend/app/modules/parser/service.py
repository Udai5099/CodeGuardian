from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ParsedChange:
    file_path: str
    line_count: int
    content: str


class ParserService:
    """Basic parser service that extracts changed files and simple content summaries."""

    def parse_changes(self, repository_path: str) -> list[ParsedChange]:
        repo_path = Path(repository_path)
        changed_files = []
        for file_path in sorted(repo_path.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part in {".git", "__pycache__"} for part in file_path.parts):
                continue
            if file_path.name.endswith((".py", ".md", ".txt", ".json", ".yaml", ".yml")):
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                changed_files.append(
                    ParsedChange(
                        file_path=str(file_path.relative_to(repo_path)),
                        line_count=len(content.splitlines()),
                        content=content,
                    )
                )
        return changed_files

    def detect_style_issue(self, content: str) -> bool:
        return bool(re.search(r"print\(|eval\(|exec\(", content))
