from backend.app.infrastructure.idempotency import InMemoryReviewIdempotencyStore
from concurrent.futures import ThreadPoolExecutor


def test_in_memory_review_idempotency_store_tracks_completed_keys() -> None:
    store = InMemoryReviewIdempotencyStore()

    assert store.claim("repo:1:head")
    assert not store.claim("repo:1:head")
    assert store.claim("repo:1:new-head")


def test_in_memory_idempotency_claim_is_atomic_under_concurrency() -> None:
    store = InMemoryReviewIdempotencyStore()

    with ThreadPoolExecutor(max_workers=16) as executor:
        claims = list(executor.map(lambda _: store.claim("same-key"), range(100)))

    assert sum(claims) == 1
