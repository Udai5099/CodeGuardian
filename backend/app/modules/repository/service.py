from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess
from threading import BoundedSemaphore, Lock
from urllib.parse import urlparse


class RepositoryAccessError(ValueError):
    """Raised when a repository cannot be opened or fetched."""


@dataclass(frozen=True)
class RepositoryAnalysis:
    repository_name: str
    is_dirty: bool
    changed_files: int
    head_commit: str


class RepositoryIntelligenceService:
    """Repository inspection plus a small local cache for remote repositories."""

    def __init__(self, cache_root: Path | None = None, max_concurrent_fetches: int = 8) -> None:
        self._cache_root = cache_root
        self._locks: dict[str, Lock] = {}
        self._locks_guard = Lock()
        self._fetch_slots = BoundedSemaphore(max_concurrent_fetches)

    def set_cache_root(self, cache_root: Path) -> None:
        """Set the process-lifetime directory used for remote checkouts."""
        self._cache_root = cache_root

    def resolve(
        self, repository_path: str = "", repository_url: str = "", require_git: bool = False
    ) -> str:
        """Return a usable local Git checkout for a path or remote Git URL."""
        source = repository_url.strip() or repository_path.strip()
        if not source:
            raise RepositoryAccessError("Enter a local repository path or a Git repository URL.")

        if self._is_remote_url(source):
            return str(self._fetch_remote(source))

        path = Path(source).expanduser()
        if not path.is_dir():
            raise RepositoryAccessError(f"Repository path does not exist: {path}")
        if require_git and not (path / ".git").exists():
            raise RepositoryAccessError(f"Not a Git repository: {path}")
        return str(path.resolve())

    @staticmethod
    def _is_remote_url(source: str) -> bool:
        parsed = urlparse(source)
        return parsed.scheme in {"http", "https", "ssh", "git"} or source.startswith("git@")

    def _fetch_remote(self, repository_url: str) -> Path:
        if self._cache_root is None:
            raise RepositoryAccessError("Repository cache is not ready. Please retry in a moment.")

        cache_root = self._cache_root
        cache_key = sha256(repository_url.encode("utf-8")).hexdigest()[:16]
        checkout = cache_root / cache_key
        cache_root.mkdir(exist_ok=True)

        with self._get_lock(cache_key), self._fetch_slots:
            try:
                if (checkout / ".git").is_dir():
                    self._git(["fetch", "--depth", "1", "origin"], checkout)
                    self._git(["checkout", "--detach", "FETCH_HEAD"], checkout)
                else:
                    self._git(["clone", "--depth", "1", repository_url, str(checkout)], cache_root)
            except subprocess.CalledProcessError as error:
                detail = error.stderr.strip() or error.stdout.strip() or "Git could not fetch this repository."
                raise RepositoryAccessError(detail) from error
        return checkout

    def _get_lock(self, cache_key: str) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(cache_key, Lock())

    @staticmethod
    def _git(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *command], cwd=cwd, capture_output=True, text=True, check=True)

    def analyze(self, repository_path: str) -> RepositoryAnalysis:
        repo_path = Path(repository_path)
        repo_name = repo_path.name

        try:
            status_output = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            head_commit_output = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", "") or "Git could not inspect this repository."
            raise RepositoryAccessError(detail.strip()) from error
        changed_files = len([line for line in status_output.stdout.splitlines() if line.strip()])

        return RepositoryAnalysis(
            repository_name=repo_name,
            is_dirty=changed_files > 0,
            changed_files=changed_files,
            head_commit=head_commit_output.stdout.strip(),
        )
