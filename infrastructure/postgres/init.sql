CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS repository_activity (
    user_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    repository_name TEXT NOT NULL,
    action_count INTEGER NOT NULL DEFAULT 0,
    last_action TEXT NOT NULL,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_commit_sha TEXT,
    PRIMARY KEY (user_id, repository_id)
);

CREATE INDEX IF NOT EXISTS repository_activity_repository_idx
    ON repository_activity (repository_name, last_updated_at DESC);

CREATE TABLE IF NOT EXISTS repository_file_vectors (
    repository_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_preview TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repository_id, file_path)
);

CREATE INDEX IF NOT EXISTS repository_file_vectors_repository_idx
    ON repository_file_vectors (repository_id);
