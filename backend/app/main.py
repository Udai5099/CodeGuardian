from contextlib import asynccontextmanager
import os
from pathlib import Path
import shutil
import tempfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.events import EventBus
from backend.app.core.settings import settings
from backend.app.modules.ai.service import HeuristicReviewAgent
from backend.app.modules.embeddings.service import EmbeddingRetrievalService
from backend.app.modules.indexing.service import IndexingService
from backend.app.modules.knowledge.service import KnowledgeGraphService
from backend.app.modules.repository.service import RepositoryAccessError, RepositoryIntelligenceService
from backend.app.modules.review.repository import ReviewRecord, ReviewRepository
from backend.app.modules.review.service import ReviewService
from backend.app.modules.review.workflows import ReviewWorkflowEngine, WorkflowStep

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create a cache that lasts only for this server process."""
    cache_parent = Path(tempfile.gettempdir())
    for stale_cache in cache_parent.glob("codexguardian-repositories-*"):
        owner_file = stale_cache / ".owner"
        try:
            owner_pid = int(owner_file.read_text(encoding="utf-8"))
            os.kill(owner_pid, 0)
            owner_is_running = True
        except (FileNotFoundError, ProcessLookupError, ValueError):
            owner_is_running = False
        except PermissionError:
            owner_is_running = True
        if stale_cache.is_dir() and not owner_is_running:
            shutil.rmtree(stale_cache, ignore_errors=True)

    with tempfile.TemporaryDirectory(prefix="codexguardian-repositories-") as cache_root:
        cache_path = Path(cache_root)
        (cache_path / ".owner").write_text(str(os.getpid()), encoding="utf-8")
        application.state.repository_service.set_cache_root(cache_path)
        yield


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
app.state.review_repository = ReviewRepository()
app.state.review_workflow = ReviewWorkflowEngine(app.state.event_bus)
app.state.indexing_service = IndexingService()
app.state.retrieval_service = EmbeddingRetrievalService()


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
    analysis = app.state.repository_service.analyze(repository_path)
    return {
        "repository_name": analysis.repository_name,
        "is_dirty": analysis.is_dirty,
        "changed_files": analysis.changed_files,
        "head_commit": analysis.head_commit,
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
                {"category": finding.category, "message": finding.message}
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
            {"category": finding.category, "message": finding.message}
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


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend", html=True), name="frontend")
