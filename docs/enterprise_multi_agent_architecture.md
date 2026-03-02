# Enterprise Multi-Agent Architecture (Refactor Blueprint)

This document defines a clean architecture redesign with strict separation between domain, application, infrastructure, and interfaces.

## 1) Architecture overview
- **Domain**: task entities, memory/LLM/tool ports, error taxonomy.
- **Application**: orchestrators and use-cases implementing planner → executor → critic loops.
- **Infrastructure**: logging, metrics, resilience (retry/backoff/circuit-breaker), provider adapters.
- **Interfaces**: CLI/API/WebSocket adapters only coordinate requests/responses.

## 2) Agent interaction model
1. Planner decomposes objective into step graph.
2. Executor resolves steps through tool registry (schema validated + timeout bounded).
3. Critic evaluates result quality and requests re-run if needed.
4. Memory agent stores episodic traces and summaries.
5. Coordinator finalizes lifecycle state.

## 3) Execution mode support
- Sequential pipeline: deterministic planner → executor → critic chain.
- Graph mode: planner emits a DAG that the orchestrator schedules concurrently.
- Event-driven mode: blackboard updates publish events for subscribers (future extension).

## 4) Memory model
MemoryInterface supports short-term, long-term vector memory, episodic and reflection namespaces.
Backends are swappable through dependency injection (in-memory, FAISS, PGVector adapters).

## 5) LLM abstraction
LLMProviderInterface provides `generate`, `stream`, `structured_output`, and `embeddings`.
No domain class imports vendor SDKs; adapters are injected at composition root.

## 6) Safety and control
- Guardrails: schema and token budget enforcement.
- Retry + exponential backoff for transient faults.
- Circuit breaker for cascading failure protection.
- Tool execution timeout and deterministic error boundaries.

## 7) Observability design
- JSON structured logs (`event`, `task_id`, `status`, `latency_ms`).
- Counter metrics for total/completed/failed tasks.
- Add OpenTelemetry spans in orchestrator for production rollout.

## 8) Scaling strategy
- Stateless agents, externalized memory/cache, and queue-driven execution enable horizontal scaling.
- Distinct process pools per role agent to isolate CPU/IO saturation.
- Shard workload by tenant/classroom/workspace keys.

## 9) Failure recovery strategy
- Crash isolation at task boundary.
- Persisted episodic checkpoints allow replay.
- Circuit breaker halts unstable dependencies and reduces blast radius.

## 10) Migration plan from old structure
1. Introduce new `app/` architecture in parallel with legacy backend.
2. Route one capability behind feature flag to new orchestrator.
3. Dual-write key traces to both old/new observability pipeline.
4. Incrementally cut over agent services and remove legacy coupling.

## 11) Roadmap to autonomous self-improvement
- Add evaluator agent + offline benchmark harness.
- Reinforcement loop for planner quality from critic feedback.
- Memory reflection jobs generating strategy updates.
- Policy engine for safe self-modification approvals.
