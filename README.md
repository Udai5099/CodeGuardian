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

## Persistent local services

All environment variables are in the root [`.env`](.env) file, outside both `frontend` and `backend`. It contains local development values for PostgreSQL, Redis, the application, and GitHub webhooks. Do not commit real production credentials; use [`.env.example`](.env.example) as the safe template.

Start the durable services with Docker Desktop running:

```powershell
docker compose up -d
```

This starts `postgres:16-alpine` and `redis:7-alpine`. PostgreSQL creates the durable `repository_activity` table, which stores each user/repository pair, action count, last action, update time, and baseline commit. Redis stores short-term repository memory; deleting its cache does not delete PostgreSQL activity records.

## GitHub PR agent and pgvector memory

The PostgreSQL service uses the pgvector image and stores one 384-dimension vector per readable repository file in `repository_file_vectors`. A repository is indexed automatically whenever it is analyzed or processed by the pull-request agent. Use `POST /api/v1/vector/index` to re-index a repository manually.

To connect GitHub, create a GitHub App with repository read access and pull-request webhooks, then set `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, and a long random `GITHUB_WEBHOOK_SECRET` in the root `.env`. Point the GitHub App webhook URL at `https://YOUR_PUBLIC_DOMAIN/api/v1/webhooks/github`, subscribe to **Pull requests**, and use the same webhook secret. The endpoint verifies GitHub's `X-Hub-Signature-256` before it accepts a delivery. Check `/api/v1/github/connection` to confirm that GitHub configuration is present.

## Run the application

From the project root:

- `python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`

Or on Windows, run:

- `scripts\\run_full_demo.bat`

Open the starter dashboard at `frontend/index.html` in a browser.

## Repository cache and production scaling

Remote repositories are cloned into a temporary, process-scoped cache. The cache is deleted when the backend shuts down and any stale CodexGuardian cache is removed on the next startup. No cloned source code is retained in the project folder.

For a production deployment serving thousands of users, run multiple API replicas behind a load balancer and move clone/review work to a job queue with isolated workers. Use shared object storage for short-lived checkouts, Redis (or equivalent) for distributed locks and rate limits, and a managed database for review records. The local development server intentionally keeps a per-process limit of eight simultaneous Git fetches to avoid exhausting CPU, disk, and network resources.

## Pull-request review agent and Redis memory

Set `REDIS_URL` before starting the backend to persist repository memory across application restarts, for example `REDIS_URL=redis://localhost:6379/0`. The `POST /api/v1/agent/pr-review` endpoint stores the current repository analysis when called with `merged: true`. Subsequent calls for a new PR retrieve that merged baseline, compare the supplied `base_sha` and `head_sha`, and return a confidence score plus the reasons for it.

`POST /api/v1/webhooks/github` accepts GitHub `pull_request` webhook payloads for `opened`, `reopened`, `synchronize`, and `closed` events. Before exposing this endpoint publicly, configure a webhook secret and signature verification at the deployment boundary. Without `REDIS_URL`, the application intentionally identifies its non-persistent in-memory development fallback in the API response.

Set `REVIEW_BACKGROUND_ENABLED=true` only when a worker-capable deployment is ready; local development keeps webhook review processing synchronous by default.

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
