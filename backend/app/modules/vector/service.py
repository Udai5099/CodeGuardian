from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b, sha256
from math import sqrt
from pathlib import Path
import re
from typing import Protocol


VECTOR_DIMENSIONS = 384
MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class FileVector:
    repository_id: str
    file_path: str
    content_hash: str
    content_preview: str
    embedding: list[float]


class VectorStore(Protocol):
    storage_name: str

    def upsert_many(self, vectors: list[FileVector]) -> int: ...


class InMemoryVectorStore:
    storage_name = "in-memory development fallback"

    def __init__(self) -> None:
        self._vectors: dict[tuple[str, str], FileVector] = {}

    def upsert_many(self, vectors: list[FileVector]) -> int:
        for vector in vectors:
            self._vectors[(vector.repository_id, vector.file_path)] = vector
        return len(vectors)


class PostgresVectorStore:
    storage_name = "postgresql-pgvector"

    def __init__(self, database_url: str) -> None:
        import psycopg

        self._psycopg = psycopg
        self._database_url = database_url
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS repository_file_vectors (
                    repository_id TEXT NOT NULL, file_path TEXT NOT NULL, content_hash TEXT NOT NULL,
                    content_preview TEXT NOT NULL, embedding vector(384) NOT NULL,
                    indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (repository_id, file_path)
                )
                """
            )

    def upsert_many(self, vectors: list[FileVector]) -> int:
        if not vectors:
            return 0
        rows = [
            (v.repository_id, v.file_path, v.content_hash, v.content_preview, _vector_literal(v.embedding))
            for v in vectors
        ]
        with self._psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO repository_file_vectors (repository_id, file_path, content_hash, content_preview, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (repository_id, file_path) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash, content_preview = EXCLUDED.content_preview,
                    embedding = EXCLUDED.embedding, indexed_at = NOW()
                """,
                rows,
            )
        return len(vectors)


def create_vector_store(database_url: str | None) -> VectorStore:
    if not database_url:
        return InMemoryVectorStore()
    try:
        return PostgresVectorStore(database_url)
    except Exception:
        return InMemoryVectorStore()


class RepositoryVectorService:
    """Creates one deterministic embedding per readable repository file."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    @property
    def storage_name(self) -> str:
        return self._store.storage_name

    def index_repository(self, repository_id: str, repository_path: str) -> int:
        root = Path(repository_path)
        vectors: list[FileVector] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            vectors.append(
                FileVector(
                    repository_id=repository_id,
                    file_path=str(path.relative_to(root)).replace("\\", "/"),
                    content_hash=sha256(content.encode("utf-8")).hexdigest(),
                    content_preview=content[:1000],
                    embedding=deterministic_embedding(content),
                )
            )
        return self._store.upsert_many(vectors)


def deterministic_embedding(content: str) -> list[float]:
    """Local, stable embedding suitable for offline development and tests."""
    values = [0.0] * VECTOR_DIMENSIONS
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", content.lower()):
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % VECTOR_DIMENSIONS
        values[bucket] += 1.0 if digest[4] % 2 else -1.0
    magnitude = sqrt(sum(value * value for value in values))
    return [round(value / magnitude, 7) for value in values] if magnitude else values


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"
