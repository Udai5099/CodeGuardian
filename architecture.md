# ADR-0001: Use a Modular Monolith as the Foundation

## Status

Accepted

## Decision

Build CodexGuardian as a modular monolith using FastAPI. Each domain such as repository, parser, review, AI, testing, merge, and notification will be implemented as an isolated module with clear interfaces. Inter-module communication will use in-process calls initially, with domain events where appropriate.

## Rationale

- Faster development than a microservice-first approach.
- Easier debugging and local setup.
- Lower operational overhead in the first release.
- Keeps the focus on repository intelligence and AI workflows rather than infrastructure.
- Makes future extraction into services straightforward.

## Consequences

- Positive: Faster iteration, lower deployment complexity, easier local development.
- Negative: Module boundaries must remain disciplined as the system grows.

## Proposed Project Structure

```text
CodexGuardian/
backend/
  app/
    core/
    infrastructure/
    modules/
      github/
      repository/
      parser/
      review/
      ai/
      rag/
      testing/
      merge/
      dashboard/
      notification/
    main.py
frontend/
docs/
infra/
scripts/
```

## Evolution Principles

The architecture should evolve in stages toward an autonomous software-engineering platform.

- Each module should adopt a domain-layer structure: api, application, domain, infrastructure, workflows, events, dto, services, and tests.
- Repository intelligence should become the central subsystem: clone -> checkout -> git diff -> AST/CFG/DFG/call graph/dependency graph -> knowledge graph -> embeddings -> repository memory.
- Repository memory should persist architecture details, coding standards, domain concepts, API contracts, naming conventions, historical bugs, prior reviews, developer feedback, and known false positives.
- The review layer should evolve into a review engine pipeline: planner -> retriever -> context builder -> agent coordinator -> consensus -> confidence -> comment generation.
- The platform should add a policy engine, confidence engine, risk engine, persisted event sourcing, and a vendor-independent LLM provider abstraction.

## Module Boundary Rule

No module should access another module's database directly. Communication should happen through well-defined services, interfaces, or events.

## Execution Notes

The application entrypoint is `backend/app/main.py`.

Run it with:

```bash
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```
