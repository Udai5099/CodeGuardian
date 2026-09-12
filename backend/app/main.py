from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.events import EventBus
from backend.app.core.settings import settings
from backend.app.infrastructure.idempotency import create_review_idempotency_store
from backend.app.modules.ai.service import HeuristicReviewAgent
from backend.app.modules.agent.memory import create_repository_memory_store
from backend.app.modules.agent.service import PullRequestReviewAgent
from backend.app.modules.embeddings.service import EmbeddingRetrievalService
from backend.app.modules.github.auth import get_installation_access_token
from backend.app.modules.github.service import GitHubIntegrationService
from backend.app.infrastructure.activity_store import RepositoryActivity, create_activity_store
from backend.app.modules.indexing.service import IndexingService
from backend.app.modules.knowledge.service import KnowledgeGraphService
from backend.app.modules.repository.service import RepositoryAccessError, RepositoryIntelligenceService
from backend.app.modules.review.repository import ReviewRecord, ReviewRepository
from backend.app.modules.review.queue import ReviewJobQueue
from backend.app.modules.review.diff_analyzer import DiffAnalyzer
from backend.app.modules.review.service import ReviewService
from backend.app.modules.review.workflows import ReviewWorkflowEngine, WorkflowStep
from backend.app.modules.vector.service import RepositoryVectorService, create_vector_store

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create a cache that lasts only for this server process."""
    cache_parent = Path(tempfile.gettempdir())
    for stale_cache in cache_parent.glob("codexguardian-repositories-*"):
        owner_file = stale_cache / ".owner"
        try:
            owner_pid = int(owner_file.read_text(encoding="utf-8"))
            if os.name == "nt":
                owner_is_running = _windows_process_exists(owner_pid)
            else:
                try:
                    os.kill(owner_pid, 0)
                    owner_is_running = True
                except (ProcessLookupError, PermissionError, OSError):
                    owner_is_running = False
        except (FileNotFoundError, ValueError):
            owner_is_running = False
        if stale_cache.is_dir() and not owner_is_running:
            shutil.rmtree(stale_cache, ignore_errors=True)

    with tempfile.TemporaryDirectory(prefix="codexguardian-repositories-") as cache_root:
        cache_path = Path(cache_root)
        (cache_path / ".owner").write_text(str(os.getpid()), encoding="utf-8")
        application.state.repository_service.set_cache_root(cache_path)
        yield
        review_queue = getattr(application.state, "review_queue", None)
        if review_queue is not None:
            review_queue.shutdown()


def _windows_process_exists(pid: int) -> bool:
    """Check whether a Windows process ID is still alive."""
    try:
        import ctypes

        process_handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not process_handle:
            return False
        ctypes.windll.kernel32.CloseHandle(process_handle)
        return True
    except (AttributeError, OSError, ValueError):
        return False


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.event_bus = EventBus()
app.state.repository_service = RepositoryIntelligenceService()
app.state.review_service = ReviewService()
app.state.knowledge_service = KnowledgeGraphService()
app.state.ai_agent = HeuristicReviewAgent()
app.state.repository_memory = create_repository_memory_store(settings.redis_url)
app.state.pr_review_agent = PullRequestReviewAgent(
    app.state.repository_memory,
    knowledge_service=app.state.knowledge_service,
    review_service=app.state.review_service,
    ai_agent=app.state.ai_agent,
)
app.state.activity_store = create_activity_store(settings.database_url)
app.state.review_idempotency_store = create_review_idempotency_store(settings.redis_url)
app.state.vector_store = create_vector_store(settings.database_url)
app.state.vector_service = RepositoryVectorService(app.state.vector_store)
app.state.review_repository = ReviewRepository()
app.state.indexing_service = IndexingService()
app.state.retrieval_service = EmbeddingRetrievalService()
app.state.review_workflow = ReviewWorkflowEngine(
    app.state.event_bus,
    repository_service=app.state.repository_service,
    knowledge_service=app.state.knowledge_service,
    review_service=app.state.review_service,
    retrieval_service=app.state.retrieval_service,
    ai_agent=app.state.ai_agent,
)


def _get_oauth_state_store() -> object:
    """Return a Redis client when configured, otherwise a per-process in-memory fallback."""
    if settings.redis_url:
        try:
            import redis

            return redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            pass

    if not hasattr(app.state, "oauth_state_store"):
        app.state.oauth_state_store = {}
    return app.state.oauth_state_store


def _oauth_state_key(state: str) -> str:
    return f"codexguardian:oauth-state:{state}"


def _save_oauth_state(state: str, *, ttl_seconds: int = 600) -> None:
    store = _get_oauth_state_store()
    if hasattr(store, "set"):
        store.set(_oauth_state_key(state), "valid", ex=ttl_seconds)
        return

    expires_at = time.time() + ttl_seconds
    store[state] = {"expires_at": expires_at}


def _consume_oauth_state(state: str | None) -> bool:
    if not state:
        return False

    store = _get_oauth_state_store()
    if hasattr(store, "delete"):
        return bool(store.delete(_oauth_state_key(state)))

    record = store.get(state)
    if record is None:
        return False
    if record.get("expires_at", 0) < time.time():
        store.pop(state, None)
        return False
    store.pop(state, None)
    return True


def resolve_repository(payload: dict[str, str], require_git: bool = False) -> str:
    try:
        return app.state.repository_service.resolve(
            repository_path=payload.get("repository_path", ""),
            repository_url=payload.get("repository_url", ""),
            require_git=require_git,
        )
    except RepositoryAccessError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.exception_handler(RepositoryAccessError)
async def repository_access_error(_: Request, error: RepositoryAccessError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, error: Exception) -> JSONResponse:
    """Keep API errors machine-readable for the browser client."""
    return JSONResponse(status_code=500, content={"detail": f"Server error: {type(error).__name__}. Check the backend terminal for details."})


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/review/health")
def review_health() -> dict[str, str]:
    return {"status": "review-module-ready"}


@app.get("/api/v1/repository/health")
def repository_health() -> dict[str, str]:
    return {"status": "repository-module-ready"}


@app.get("/api/v1/system/modules")
def module_registry() -> dict[str, list[str]]:
    modules = [
        "review",
        "repository",
        "parser",
        "indexing",
        "graph",
        "embeddings",
        "knowledge",
        "ai",
        "rag",
        "testing",
        "security",
        "merge",
        "analytics",
        "notification",
        "dashboard",
    ]
    return {"modules": modules}


@app.post("/api/v1/repository/analyze")
def analyze_repository(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload, require_git=True)
    repository_id = payload.get("repository_url") or str(Path(repository_path).resolve())
    analysis = app.state.repository_service.analyze(repository_path)
    vector_count = app.state.vector_service.index_repository(repository_id, repository_path)
    return {
        "repository_name": analysis.repository_name,
        "is_dirty": analysis.is_dirty,
        "changed_files": analysis.changed_files,
        "head_commit": analysis.head_commit,
        "vector_index": {"storage": app.state.vector_service.storage_name, "files_indexed": vector_count},
        "analysis_overview": (
            "Repository analysis checks the Git working tree and identifies the current commit "
            "so you can understand the state of the codebase before running a review."
        ),
        "how_it_works": [
            "Opens the supplied local repository or shallow-clones a remote Git URL.",
            "Runs Git status to count files with uncommitted changes.",
            "Reads the current HEAD commit to establish the review baseline.",
        ],
        "next_steps": [
            "Run AI review for context-aware suggestions.",
            "Build the symbol index to inspect Python code structure.",
            "Map the codebase to view its files and module count.",
        ],
    }


@app.post("/api/v1/review/diff")
def review_diff(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload, require_git=True)
    review = app.state.review_service.review_diff(repository_path)
    workflow_context = {
        "repository_path": repository_path,
        "summary": review.summary,
        "status": "completed",
    }
    app.state.review_workflow.run(
        "review",
        workflow_context,
        steps=[WorkflowStep("complete", lambda ctx: ctx)],
    )
    app.state.review_repository.save(
        ReviewRecord(
            review_id=review.review_id,
            summary=review.summary,
            findings=[
                {
                    "category": finding.category,
                    "severity": finding.severity,
                    "file_path": finding.file_path,
                    "line": finding.line,
                    "message": finding.message,
                    "explanation": finding.explanation,
                    "suggestion": finding.suggestion,
                }
                for finding in review.findings
            ],
        )
    )
    return {
        "review_id": review.review_id,
        "summary": review.summary,
        "context": {
            "module_count": app.state.knowledge_service.build(repository_path).module_count,
            "file_count": app.state.knowledge_service.build(repository_path).file_count,
        },
        "findings": [
            {
                "category": finding.category,
                "severity": finding.severity,
                "file_path": finding.file_path,
                "line": finding.line,
                "message": finding.message,
                "explanation": finding.explanation,
                "suggestion": finding.suggestion,
            }
            for finding in review.findings
        ],
    }


@app.post("/api/v1/knowledge/graph")
def build_knowledge_graph(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload)
    graph = app.state.knowledge_service.build(repository_path)
    return {
        "repository_name": graph.repository_name,
        "file_count": graph.file_count,
        "module_count": graph.module_count,
        "files": graph.files,
    }


@app.post("/api/v1/review/ai")
def ai_review(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload, require_git=True)
    repository_analysis = app.state.repository_service.analyze(repository_path)
    knowledge_graph = app.state.knowledge_service.build(repository_path)

    retrieval_results = app.state.retrieval_service.retrieve(repository_path, "python tests")
    review_context = {
        "repository_name": repository_analysis.repository_name,
        "changed_files": repository_analysis.changed_files,
        "module_count": knowledge_graph.module_count,
        "file_count": knowledge_graph.file_count,
        "retrieval_results": [
            {"content": result.content, "score": result.score}
            for result in retrieval_results
        ],
    }
    result = app.state.ai_agent.review(review_context)

    return {
        "agent_name": result.agent_name,
        "confidence": result.confidence,
        "suggested_fix": result.suggested_fix,
        "rationale": result.rationale,
    }


@app.post("/api/v1/indexing/build")
def build_index(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload)
    index = app.state.indexing_service.build_index(repository_path)
    return {
        "repository_name": index.repository_name,
        "symbol_count": index.symbol_count,
        "indexed_files": index.indexed_files,
        "symbols": index.symbols,
    }


@app.post("/api/v1/rag/retrieve")
def retrieve_context(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload)
    query = payload.get("query", "")
    results = app.state.retrieval_service.retrieve(repository_path, query)
    return {
        "query": query,
        "results": [
            {"content": result.content, "score": result.score}
            for result in results
        ],
    }


@app.post("/api/v1/vector/index")
def index_repository_vectors(payload: dict[str, str]) -> dict[str, object]:
    repository_path = resolve_repository(payload)
    repository_id = payload.get("repository_url") or str(Path(repository_path).resolve())
    indexed_files = app.state.vector_service.index_repository(repository_id, repository_path)
    return {
        "repository_id": repository_id,
        "indexed_files": indexed_files,
        "storage": app.state.vector_service.storage_name,
        "embedding_dimensions": 384,
    }


def build_github_review_body(review: object) -> str:
    """Build a human-readable GitHub PR review from a CodexGuardian review."""

    severity_markers = {
        "critical": "🔴",
        "high": "🔴",
        "medium": "🟡",
        "low": "🔵",
        "info": "⚪",
    }
    lines = [
        "## CodexGuardian Review",
        "",
        f"**Summary:** {review.summary}",
        "",
        f"**Confidence:** {review.confidence:.0%}",
        "",
        "### Findings",
        "",
    ]

    if review.findings:
        for finding in review.findings:
            severity = str(finding.get("severity", "info")).lower()
            marker = severity_markers.get(severity, "⚪")
            category = str(finding.get("category", "review")).title()
            location = finding.get("file_path") or "General review"
            if finding.get("line") is not None:
                location = f"{location}:{finding['line']}"
            lines.extend(
                [
                    f"#### {marker} {severity.upper()} — {category}",
                    "",
                    f"**`{location}`**",
                    "",
                    f"**{finding.get('message', '')}**",
                    "",
                    str(finding.get("explanation", "")),
                ]
            )
            if finding.get("suggestion"):
                lines.extend(["", f"**Suggestion:** {finding['suggestion']}"])
            lines.append("")
    else:
        lines.append("No findings were identified.")

    if review.recommendation:
        lines.extend(
            [
                "",
                "### Recommendation",
                "",
                review.recommendation,
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "_Generated automatically by CodexGuardian._",
        ]
    )

    return "\n".join(lines)


def build_github_inline_comments(
    review: object,
    repository_path: str,
    base_sha: str,
    head_sha: str,
) -> list[dict[str, object]]:
    command = ["git", "diff", "--unified=0"]
    if base_sha and head_sha:
        command.extend([base_sha, head_sha])
    try:
        diff_text = subprocess.run(
            command,
            cwd=repository_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []

    changed_lines = {
        (line.file_path, line.line_number)
        for line in DiffAnalyzer().parse_added_lines(diff_text)
    }
    comments: list[dict[str, object]] = []
    for finding in review.findings:
        file_path = finding.get("file_path")
        line_number = finding.get("line")
        if (file_path, line_number) not in changed_lines:
            continue
        comment_body = f"**{finding.get('message', '')}**\n\n{finding.get('explanation', '')}"
        if finding.get("suggestion"):
            comment_body += f"\n\n**Suggestion:** {finding['suggestion']}"
        comments.append(
            {
                "body": comment_body,
                "path": str(file_path).replace("\\", "/"),
                "line": line_number,
                "side": "RIGHT",
                **({"commit_id": head_sha} if head_sha else {}),
            }
        )
    return comments


def run_pull_request_agent(payload: dict[str, object]) -> dict[str, object]:
    installation_id = str(payload.get("installation_id") or "").strip()
    installation_token = str(payload.get("installation_token") or "").strip()

    if installation_id:
        if not installation_token:
            try:
                installation_token = get_installation_access_token(installation_id)
            except Exception as error:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not authenticate GitHub App installation: {type(error).__name__}.",
                ) from error

        repository_url = str(payload.get("repository_url") or "").strip()
        head_sha = str(payload.get("head_sha") or "").strip()

        if not repository_url:
            raise HTTPException(status_code=400, detail="GitHub repository URL is missing.")

        try:
            repository_path = app.state.repository_service.resolve_github_repository(
                repository_url=repository_url,
                installation_token=installation_token,
                base_sha=str(payload.get("base_sha") or ""),
                head_sha=head_sha,
            )
        except RepositoryAccessError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    else:
        repository_path = resolve_repository(payload, require_git=True)  # type: ignore[arg-type]

    repository_id = str(payload.get("repository_url") or Path(repository_path).resolve())
    repository_name = Path(repository_path).name
    user_id = str(payload.get("user_id") or "anonymous")
    pr_number = int(payload.get("pull_request_number", 0))
    if pr_number <= 0:
        raise HTTPException(status_code=400, detail="pull_request_number must be a positive integer.")
    base_sha = str(payload.get("base_sha", ""))
    head_sha = str(payload.get("head_sha", ""))
    if payload.get("repository_url") and not payload.get("installation_id"):
        try:
            app.state.repository_service.fetch_revisions(
                repository_path,
                [base_sha, head_sha],
            )
        except RepositoryAccessError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    vector_count = app.state.vector_service.index_repository(repository_id, repository_path)

    if payload.get("merged") is True:
        memory = app.state.pr_review_agent.remember_merged_repository(repository_id, repository_path, pr_number)
        activity = app.state.activity_store.record(
            RepositoryActivity(user_id, repository_id, repository_name, 0, "merged-pr-memory-saved", last_commit_sha=memory.commit_sha)
        )
        return {
            "agent_name": "pull-request-review-agent",
            "status": "repository-memory-updated",
            "storage": app.state.repository_memory.storage_name,
            "message": "Merged PR analysis saved as the baseline for future pull-request reviews.",
            "baseline_commit": memory.commit_sha,
            "file_count": memory.file_count,
            "module_count": memory.module_count,
            "vector_index": {"storage": app.state.vector_service.storage_name, "files_indexed": vector_count},
            "activity": activity_response(activity),
        }

    review = app.state.pr_review_agent.review_pull_request(
        repository_id,
        repository_path,
        pr_number,
        base_sha,
        head_sha,
    )

    github_review = None

    if installation_token:
        repository_url = str(payload.get("repository_url") or "").strip()

        if repository_url:
            github_service = GitHubIntegrationService(
                installation_id=installation_id,
                installation_token=installation_token,
            )

            repository_parts = repository_url.rstrip("/").split("/")

            if len(repository_parts) >= 2:
                owner = repository_parts[-2]
                repo = repository_parts[-1].removesuffix(".git")

                review_body = build_github_review_body(review)
                inline_comments = build_github_inline_comments(
                    review,
                    repository_path,
                    base_sha,
                    head_sha,
                )

                try:
                    github_review = github_service.submit_review(
                        owner,
                        repo,
                        pr_number,
                        review_body,
                        event="COMMENT",
                        comments=inline_comments,
                    )
                except Exception as error:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "CodexGuardian completed the review, "
                            f"but could not publish it to GitHub: {type(error).__name__}."
                        ),
                    ) from error

    activity = app.state.activity_store.record(
        RepositoryActivity(user_id, repository_id, repository_name, 0, "pull-request-reviewed", last_commit_sha=review.baseline_commit)
    )
    return {
        "agent_name": review.agent_name,
        "status": "review-complete",
        "storage": app.state.repository_memory.storage_name,
        "pull_request_number": review.pull_request_number,
        "changed_files": review.changed_files,
        "summary": review.summary,
        "findings": review.findings,
        "confidence": review.confidence,
        "confidence_reasons": review.confidence_reasons,
        "baseline_commit": review.baseline_commit,
        "recommendation": review.recommendation,
        "github_review": {
            "posted": github_review is not None,
            "review_id": github_review.get("id") if github_review else None,
            "html_url": github_review.get("html_url") if github_review else None,
        },
        "vector_index": {"storage": app.state.vector_service.storage_name, "files_indexed": vector_count},
        "activity": activity_response(activity),
    }


def activity_response(activity: RepositoryActivity) -> dict[str, object]:
    return {
        "storage": app.state.activity_store.storage_name,
        "user_id": activity.user_id,
        "repository_name": activity.repository_name,
        "action_count": activity.action_count,
        "last_action": activity.last_action,
        "last_updated_at": activity.last_updated_at.isoformat() if activity.last_updated_at else None,
        "last_commit_sha": activity.last_commit_sha,
    }


@app.get("/api/v1/repository/activity")
def repository_activity(user_id: str, repository_id: str) -> dict[str, object]:
    activity = app.state.activity_store.get(user_id, repository_id)
    if not activity:
        raise HTTPException(status_code=404, detail="No activity found for this user and repository.")
    return activity_response(activity)


@app.post("/api/v1/agent/pr-review")
def review_pull_request(payload: dict[str, object]) -> dict[str, object]:
    """Run an incremental PR review or record the baseline after a merge."""
    return run_pull_request_agent(payload)


@app.get("/api/v1/github/connection")
def github_connection() -> dict[str, object]:
    secret = settings.github_webhook_secret or ""
    return {
        "github_app_id_configured": bool(settings.github_app_id),
        "webhook_secret_configured": bool(secret and not secret.startswith("replace-with")),
        "webhook_endpoint": "/api/v1/webhooks/github",
    }


@app.get("/api/v1/github/authorize")
def github_authorize() -> RedirectResponse:
    """Redirect the user to GitHub's OAuth authorization page."""
    client_id = os.getenv("GITHUB_CLIENT_ID") or settings.github_client_id
    redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URL") or settings.github_oauth_redirect_url

    if not client_id or not redirect_uri:
        raise HTTPException(status_code=503, detail="GitHub OAuth client settings are not configured.")

    state = secrets.token_urlsafe(32)
    _save_oauth_state(state)

    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "read:user user:email",
        }
    )

    return RedirectResponse(url=f"https://github.com/login/oauth/authorize?{params}")

@app.get("/api/v1/github/callback")
def github_callback(code: str | None = None, state: str | None = None) -> dict[str, object]:
    """Exchange the GitHub OAuth code without exposing the resulting token."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing GitHub OAuth code.")

    if not _consume_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired GitHub OAuth state.")

    client_id = os.getenv("GITHUB_CLIENT_ID") or settings.github_client_id
    client_secret = os.getenv("GITHUB_CLIENT_SECRET") or settings.github_client_secret
    redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URL") or settings.github_oauth_redirect_url

    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth client settings are not configured.",
        )

    token_response = httpx.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Accept": "application/json"},
        timeout=15.0,
    )

    token_response.raise_for_status()

    token_payload = token_response.json()
    access_token = token_payload.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=502,
            detail="GitHub OAuth token exchange did not return an access token.",
        )

    return {
        "status": "oauth-success",
        "message": "GitHub OAuth callback completed successfully.",
        "token_received": True,
        "token_type": token_payload.get("token_type"),
        "scope": token_payload.get("scope"),
    }

@app.post("/api/v1/github/webhook")
@app.post("/api/v1/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, object]:
    """Verify GitHub delivery signatures before processing pull_request events."""
    secret = settings.github_webhook_secret or ""
    if not secret or secret.startswith("replace-with"):
        raise HTTPException(status_code=503, detail="Set GITHUB_WEBHOOK_SECRET before enabling GitHub webhooks.")
    raw_body = await request.body()
    expected_signature = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature.")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object.")
    pull_request = payload.get("pull_request")
    repository = payload.get("repository")
    installation = payload.get("installation")
    if not isinstance(pull_request, dict) or not isinstance(repository, dict):
        raise HTTPException(status_code=400, detail="Expected a GitHub pull_request webhook payload.")
    if not isinstance(installation, dict):
        raise HTTPException(status_code=400, detail="GitHub webhook is missing installation information.")
    installation_id = installation.get("id")
    if not installation_id:
        raise HTTPException(status_code=400, detail="GitHub webhook installation ID is missing.")
    action = str(payload.get("action", ""))
    if action not in {"opened", "reopened", "synchronize", "closed"}:
        return {"status": "ignored", "message": f"Webhook action '{action}' is not reviewed."}
    base = pull_request.get("base", {})
    head = pull_request.get("head", {})
    repository_url = str(repository.get("clone_url", ""))
    pull_request_number = pull_request.get("number", 0)
    head_sha = head.get("sha", "") if isinstance(head, dict) else ""
    repository_name = str(repository.get("full_name") or repository_url)
    stable_key = f"{repository_name}:{pull_request_number}:{head_sha}"
    delivery_key = f"delivery:{x_github_delivery}" if x_github_delivery else ""
    if not app.state.review_idempotency_store.claim(stable_key):
        return {"status": "duplicate", "message": "This pull-request revision was already reviewed."}
    if delivery_key and not app.state.review_idempotency_store.claim(delivery_key):
        return {"status": "duplicate", "message": "This pull-request revision was already reviewed."}

    review_payload = {
        "repository_url": repository_url,
        "installation_id": str(installation_id),
        "user_id": (
            payload.get("sender", {}).get("login", "anonymous")
            if isinstance(payload.get("sender"), dict)
            else "anonymous"
        ),
        "pull_request_number": pull_request_number,
        "base_sha": base.get("sha", "") if isinstance(base, dict) else "",
        "head_sha": head_sha,
        "merged": bool(pull_request.get("merged")) and action == "closed",
    }
    if settings.review_background_enabled:
        if not hasattr(app.state, "review_queue"):
            app.state.review_queue = ReviewJobQueue(run_pull_request_agent)
        app.state.review_queue.enqueue(review_payload)
        return {"status": "queued", "message": "Pull-request review queued for background processing."}

    result = run_pull_request_agent(review_payload)
    return result


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend", html=True), name="frontend")
