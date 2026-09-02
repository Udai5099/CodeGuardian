# Milestone Roadmap

## Phase 1: Repository Intelligence
- Repository clone and checkout workflow
- Git diff inspection
- AST, CFG, DFG, dependency, and call-graph analysis
- Knowledge graph construction

## Phase 2: Repository Memory
- Persistent repository memory for architecture, standards, APIs, naming, historical bugs, and review feedback
- Learned false-positive suppression and repository-specific heuristics

## Phase 3: RAG and Context Retrieval
- Repository indexing
- Embeddings and retrieval layer
- Context-augmented review planning

## Phase 4: Review Engine Planning
- Planner and retriever components
- Context builder and agent coordination layer
- Structured review output schema

## Phase 5: Multi-Agent Review
- Specialized agents for security, performance, architecture, testing, documentation, dependency, and refactoring
- Clear prompts, tools, and output schemas for each agent

## Phase 6: Consensus and Confidence
- Consensus engine
- Confidence scoring for review findings
- Evidence-backed explanations and supporting rules

## Phase 7: Risk and Policy
- Risk engine with weighted scoring for security, performance, complexity, coverage, and tests
- Policy engine for repository, organization, security, merge, and cost rules

## Phase 8: Execution and Learning
- Auto-repair and test-generation capabilities
- Safe merge orchestration
- Event-sourced workflow replay, auditing, and learning loops

## Phase 9: LLM Abstraction and Vendor Independence
- Unified LLM provider interface
- Support for OpenAI, Gemini, Claude, Ollama, Groq, DeepSeek, and OpenRouter
