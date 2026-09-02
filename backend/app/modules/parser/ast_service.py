from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    file_path: str


class ASTSymbolService:
    """A lightweight symbol extractor based on regex heuristics for Python files."""

    def extract_symbols(self, repository_path: str) -> list[Symbol]:
        repo_path = Path(repository_path)
        symbols: list[Symbol] = []
        for file_path in sorted(repo_path.rglob("*.py")):
            if any(part in {".git", "__pycache__"} for part in file_path.parts):
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"def\s+(\w+)", content):
                symbols.append(Symbol(name=match.group(1), kind="function", file_path=str(file_path.relative_to(repo_path))))
            for match in re.finditer(r"class\s+(\w+)", content):
                symbols.append(Symbol(name=match.group(1), kind="class", file_path=str(file_path.relative_to(repo_path))))
        return symbols
