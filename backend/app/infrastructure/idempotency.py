from __future__ import annotations

import hashlib
from threading import Lock
from typing import Protocol


class ReviewIdempotencyStore(Protocol):
    storage_name: str

    def claim(self, key: str) -> bool: ...


class InMemoryReviewIdempotencyStore:
    storage_name = "in-memory development fallback"

    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._lock = Lock()

    def claim(self, key: str) -> bool:
        with self._lock:
            if key in self._keys:
                return False
            self._keys.add(key)
            return True


class RedisReviewIdempotencyStore:
    storage_name = "redis"

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    @staticmethod
    def _key(key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"codexguardian:review-processed:{digest}"

    def claim(self, key: str) -> bool:
        return bool(self._client.set(self._key(key), "1", nx=True, ex=60 * 60 * 24 * 30))


def create_review_idempotency_store(redis_url: str | None) -> ReviewIdempotencyStore:
    if not redis_url:
        return InMemoryReviewIdempotencyStore()
    try:
        return RedisReviewIdempotencyStore(redis_url)
    except Exception:
        return InMemoryReviewIdempotencyStore()
