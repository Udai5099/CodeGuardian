from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.modules.parser.ast_service import ASTSymbolService


@dataclass(frozen=True)
class IndexingResult:
    repository_name: str
    symbol_count: int
    indexed_files: int
    symbols: list[dict[str, str]]


class IndexingService:
    """Simple repository indexing service that builds a symbol index from Python files."""

    def __init__(self, symbol_service: ASTSymbolService | None = None) -> None:
        self._symbol_service = symbol_service or ASTSymbolService()

    def build_index(self, repository_path: str) -> IndexingResult:
        repo_path = Path(repository_path)
        symbols = self._symbol_service.extract_symbols(repository_path)
        indexed_files = len({symbol.file_path for symbol in symbols})
        return IndexingResult(
            repository_name=repo_path.name,
            symbol_count=len(symbols),
            indexed_files=indexed_files,
            symbols=[{"name": symbol.name, "kind": symbol.kind, "file_path": symbol.file_path} for symbol in symbols],
        )
