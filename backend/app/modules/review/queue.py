from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable


class ReviewJobQueue:
    """Small local worker boundary; production deployments can replace the executor."""

    def __init__(self, worker: Callable[[dict[str, object]], dict[str, object]], max_workers: int = 2) -> None:
        self._worker = worker
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="codexguardian-review")

    def enqueue(self, payload: dict[str, object]) -> Future[dict[str, object]]:
        return self._executor.submit(self._worker, payload)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
