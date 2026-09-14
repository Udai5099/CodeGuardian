from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RepositoryActivity:
    user_id: str
    repository_id: str
    repository_name: str
    action_count: int
    last_action: str
    last_updated_at: datetime | None = None
    last_commit_sha: str | None = None


class RepositoryActivityStore(Protocol):
    storage_name: str

    def record(self, activity: RepositoryActivity) -> RepositoryActivity: ...

    def get(self, user_id: str, repository_id: str) -> RepositoryActivity | None: ...


class InMemoryActivityStore:
    storage_name = "in-memory development fallback"

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], RepositoryActivity] = {}

    def record(self, activity: RepositoryActivity) -> RepositoryActivity:
        key = (activity.user_id, activity.repository_id)
        previous = self._records.get(key)
        saved = RepositoryActivity(
            **{**asdict(activity), "action_count": (previous.action_count if previous else 0) + 1, "last_updated_at": datetime.now().astimezone()}
        )
        self._records[key] = saved
        return saved

    def get(self, user_id: str, repository_id: str) -> RepositoryActivity | None:
        return self._records.get((user_id, repository_id))


class PostgresActivityStore:
    storage_name = "postgresql"

    def __init__(self, database_url: str) -> None:
        import psycopg

        self._psycopg = psycopg
        self._database_url = database_url
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self._psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS repository_activity (
                    user_id TEXT NOT NULL, repository_id TEXT NOT NULL, repository_name TEXT NOT NULL,
                    action_count INTEGER NOT NULL DEFAULT 0, last_action TEXT NOT NULL,
                    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), last_commit_sha TEXT,
                    PRIMARY KEY (user_id, repository_id)
                )
                """
            )

    def record(self, activity: RepositoryActivity) -> RepositoryActivity:
        with self._psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO repository_activity (user_id, repository_id, repository_name, action_count, last_action, last_commit_sha)
                VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT (user_id, repository_id) DO UPDATE SET
                    repository_name = EXCLUDED.repository_name,
                    action_count = repository_activity.action_count + 1,
                    last_action = EXCLUDED.last_action,
                    last_commit_sha = EXCLUDED.last_commit_sha,
                    last_updated_at = NOW()
                RETURNING user_id, repository_id, repository_name, action_count, last_action, last_updated_at, last_commit_sha
                """,
                (activity.user_id, activity.repository_id, activity.repository_name, activity.last_action, activity.last_commit_sha),
            )
            return RepositoryActivity(*cursor.fetchone())

    def get(self, user_id: str, repository_id: str) -> RepositoryActivity | None:
        with self._psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT user_id, repository_id, repository_name, action_count, last_action, last_updated_at, last_commit_sha
                   FROM repository_activity WHERE user_id = %s AND repository_id = %s""",
                (user_id, repository_id),
            )
            row = cursor.fetchone()
            return RepositoryActivity(*row) if row else None


def create_activity_store(database_url: str | None) -> RepositoryActivityStore:
    if not database_url:
        return InMemoryActivityStore()
    try:
        return PostgresActivityStore(database_url)
    except Exception:
        return InMemoryActivityStore()
