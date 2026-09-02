# CodexGuardian

CodexGuardian is a modular-monolith platform for repository intelligence, diff-based review, knowledge graphs, indexing, retrieval-augmented context, and AI-style review suggestions.

## Current maturity

- Modular monolith architecture with explicit domain boundaries
- Repository intelligence and diff-based review flow
- Repository knowledge graph builder
- Lightweight workflow engine and domain-event foundation
- Persistence boundary for review records
- Indexing and AST-style symbol extraction for Python repositories
- Embeddings-based retrieval layer for repository context
- Retrieval-aware AI review agent that can incorporate relevant context into its rationale
- ADR and roadmap documentation

## Architecture direction

The next evolution is to move from a simple review scaffold toward an autonomous software-engineering platform.

- Each domain module should follow a consistent structure: api, application, domain, infrastructure, workflows, events, dto, services, and tests.
- Repository intelligence should become the core subsystem: clone -> checkout -> git diff -> AST/CFG/DFG/call graph/dependency graph -> knowledge graph -> embeddings -> repository memory.
- Repository memory should capture architecture, coding standards, domain concepts, API contracts, naming conventions, historical bugs, past reviews, developer feedback, and known false positives.
- The review experience should evolve from a single AI review step into a review engine pipeline: planner -> retriever -> context builder -> agent coordinator -> consensus -> confidence -> comment generation.
- The platform should add a policy engine, confidence engine, risk engine, persisted event sourcing, and a vendor-independent LLM provider abstraction.

## Project layout

- backend/app/core: shared infrastructure, settings, and events
- backend/app/infrastructure: persistence and integration boundaries
- backend/app/modules: review, repository, parser, indexing, graph, embeddings, knowledge, ai, testing, security, merge, analytics, notification, and dashboard modules
- docs/ADR: architecture decision records
- frontend: starter dashboard
- scripts: execution helpers
- tests: regression tests for review, indexing, retrieval, and workflow behavior

## Setup

1. Open a terminal in the project folder.
2. Create a virtual environment:
   - `python -m venv .venv`
3. Activate it:
   - Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
   - Windows Command Prompt: `.venv\\Scripts\\activate.bat`
4. Install dependencies:
   - `pip install -r requirements.txt`
5. Review the execution instructions in `execution_steps` or `execution_steps.md`.

## Run the application

From the project root:

- `python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`

Or on Windows, run:

- `scripts\\run_full_demo.bat`

Open the starter dashboard at `frontend/index.html` in a browser.

## Repository cache and production scaling

Remote repositories are cloned into a temporary, process-scoped cache. The cache is deleted when the backend shuts down and any stale CodexGuardian cache is removed on the next startup. No cloned source code is retained in the project folder.

For a production deployment serving thousands of users, run multiple API replicas behind a load balancer and move clone/review work to a job queue with isolated workers. Use shared object storage for short-lived checkouts, Redis (or equivalent) for distributed locks and rate limits, and a managed database for review records. The local development server intentionally keeps a per-process limit of eight simultaneous Git fetches to avoid exhausting CPU, disk, and network resources.

## Key endpoints

- `GET /health`
- `GET /api/v1/review/health`
- `GET /api/v1/repository/health`
- `GET /api/v1/system/modules`
- `POST /api/v1/repository/analyze`
- `POST /api/v1/review/diff`
- `POST /api/v1/review/ai`
- `POST /api/v1/knowledge/graph`
- `POST /api/v1/indexing/build`
- `POST /api/v1/rag/retrieve`

## Example workflow

1. Analyze a repository with `POST /api/v1/repository/analyze`
2. Build the searchable index with `POST /api/v1/indexing/build`
3. Retrieve relevant context with `POST /api/v1/rag/retrieve`
4. Trigger an AI review with `POST /api/v1/review/ai`

## Tests

Run:

- `pytest -q`
