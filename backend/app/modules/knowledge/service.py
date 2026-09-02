from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeGraph:
    repository_name: str
    file_count: int
    module_count: int
    files: list[str]


class KnowledgeGraphService:
    """Simple repository knowledge graph built from file layout."""

    def build(self, repository_path: str) -> KnowledgeGraph:
        repo_path = Path(repository_path)
        files = []
        module_count = 0

        for file_path in sorted(repo_path.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part in {".git", "__pycache__"} for part in file_path.parts):
                continue
            files.append(str(file_path.relative_to(repo_path)))
            if file_path.suffix == ".py":
                module_count += 1

        return KnowledgeGraph(
            repository_name=repo_path.name,
            file_count=len(files),
            module_count=module_count,
            files=files,
        )
