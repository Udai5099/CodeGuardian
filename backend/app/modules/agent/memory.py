from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Protocol


@dataclass(frozen=True)
class RepositoryMemory:
    repository_id: str
    commit_sha: str
    file_count: int
    module_count: int
    merged_pr_number: int


class RepositoryMemoryStore(Protocol):
    storage_name: str

    def get(self, repository_id: str) -> RepositoryMemory | None: ...

    def save(self, memory: RepositoryMemory) -> None: ...


class InMemoryRepositoryMemoryStore:
    """Development fallback used only when Redis is not configured."""

    storage_name = "in-memory development fallback"

    def __init__(self) -> None:
        self._records: dict[str, RepositoryMemory] = {}

    def get(self, repository_id: str) -> RepositoryMemory | None:
        return self._records.get(repository_id)

    def save(self, memory: RepositoryMemory) -> None:
        self._records[memory.repository_id] = memory


class RedisRepositoryMemoryStore:
    storage_name = "redis"

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    @staticmethod
    def _key(repository_id: str) -> str:
        digest = sha256(repository_id.encode("utf-8")).hexdigest()
        return f"codexguardian:repository-memory:{digest}"

    def get(self, repository_id: str) -> RepositoryMemory | None:
        raw = self._client.get(self._key(repository_id))
        return RepositoryMemory(**json.loads(raw)) if raw else None

    def save(self, memory: RepositoryMemory) -> None:
        self._client.set(self._key(memory.repository_id), json.dumps(asdict(memory)))


def create_repository_memory_store(redis_url: str | None) -> RepositoryMemoryStore:
    if not redis_url:
        return InMemoryRepositoryMemoryStore()
    try:
        return RedisRepositoryMemoryStore(redis_url)
    except Exception:
        return InMemoryRepositoryMemoryStore()
