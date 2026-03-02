# Scalable Multi-Agent Orchestration System (Event-Driven)

## 1) Architecture Overview

The system is built around an **Event Bus** (Kafka/RabbitMQ/NATS), with each agent implemented as an independent service that consumes and publishes domain events.

Core goals:
- Scale each agent independently based on queue depth and latency.
- Isolate failures with retries + dead-letter queues.
- Keep per-student state consistent via event sourcing + materialized views.
- Support observability and replay for learning/audit workflows.

---

## 2) Agents, Responsibilities, and Contracts

Common envelope for all events:

```json
{
  "event_id": "uuid",
  "event_type": "string",
  "trace_id": "uuid",
  "correlation_id": "uuid",
  "causation_id": "uuid|null",
  "tenant_id": "string",
  "student_id": "string",
  "session_id": "string",
  "timestamp": "ISO-8601",
  "schema_version": "v1",
  "payload": {}
}
```

### 2.1 Orchestrator Agent
**Responsibilities**
- Receive external requests (`LearningRequestReceived`).
- Validate request, initialize workflow, and emit first command/event.
- Track workflow status and enforce SLA/timeout policies.
- Handle compensation flow when downstream fails.

**Input events**
- `LearningRequestReceived`
- All agent completion/failure events.

**Output events**
- `PDFProcessRequested`
- `TopicExtractionRequested`
- `TestGenerationRequested`
- `EvaluationRequested`
- `LearningPathRequested`
- `ProgressTrackingRequested`
- `ReportGenerationRequested`
- `WorkflowCompleted` / `WorkflowFailed`

**Input schema** (`LearningRequestReceived.payload`)
```json
{
  "source": "upload|lms|api",
  "pdf_uri": "string",
  "student_profile": {
    "grade": "int",
    "language": "string",
    "goals": ["string"]
  },
  "config": {
    "difficulty": "easy|medium|hard",
    "num_questions": "int"
  }
}
```

**Output schema** (`WorkflowCompleted.payload`)
```json
{
  "workflow_id": "uuid",
  "status": "completed",
  "artifacts": {
    "topics_uri": "string",
    "test_uri": "string",
    "evaluation_uri": "string",
    "learning_path_uri": "string",
    "progress_uri": "string",
    "report_uri": "string"
  }
}
```

### 2.2 PDF Processing Agent
**Responsibilities**
- Fetch and parse PDF.
- OCR fallback for scanned pages.
- Normalize structure (sections, headings, tables, metadata).

**Input events**
- `PDFProcessRequested`

**Output events**
- `PDFProcessed`
- `PDFProcessingFailed`

**Input schema**
```json
{
  "pdf_uri": "string",
  "options": {
    "ocr_enabled": true,
    "language": "en|vi"
  }
}
```

**Output schema** (`PDFProcessed.payload`)
```json
{
  "document_id": "uuid",
  "text_chunks_uri": "string",
  "structure": {
    "num_pages": "int",
    "sections": [
      {"title": "string", "start_page": "int", "end_page": "int"}
    ]
  },
  "quality_score": "float"
}
```

### 2.3 Topic Extraction Agent
**Responsibilities**
- Extract topics/concepts and learning objectives from processed content.
- Generate topic graph with prerequisites.

**Input events**
- `TopicExtractionRequested`

**Output events**
- `TopicsExtracted`
- `TopicExtractionFailed`

**Input schema**
```json
{
  "document_id": "uuid",
  "text_chunks_uri": "string",
  "taxonomy": "curriculum_v1"
}
```

**Output schema** (`TopicsExtracted.payload`)
```json
{
  "document_id": "uuid",
  "topics": [
    {
      "topic_id": "string",
      "name": "string",
      "difficulty": "1-5",
      "objectives": ["string"],
      "prerequisites": ["topic_id"]
    }
  ],
  "topic_graph_uri": "string"
}
```

### 2.4 Test Generator Agent
**Responsibilities**
- Generate question bank and adaptive test forms.
- Enforce blueprint constraints (difficulty distribution, objective coverage).

**Input events**
- `TestGenerationRequested`

**Output events**
- `TestGenerated`
- `TestGenerationFailed`

**Input schema**
```json
{
  "topics": [{"topic_id": "string", "weight": "float"}],
  "constraints": {
    "num_questions": "int",
    "difficulty_mix": {"easy": "float", "medium": "float", "hard": "float"},
    "question_types": ["mcq", "short_answer"]
  }
}
```

**Output schema** (`TestGenerated.payload`)
```json
{
  "test_id": "uuid",
  "questions_uri": "string",
  "answer_key_uri": "string",
  "estimated_duration_min": "int"
}
```

### 2.5 Evaluation Agent
**Responsibilities**
- Score student answers.
- Produce skill mastery and misconception analysis.

**Input events**
- `EvaluationRequested`

**Output events**
- `EvaluationCompleted`
- `EvaluationFailed`

**Input schema**
```json
{
  "test_id": "uuid",
  "student_answers_uri": "string",
  "answer_key_uri": "string",
  "rubric_version": "string"
}
```

**Output schema** (`EvaluationCompleted.payload`)
```json
{
  "evaluation_id": "uuid",
  "score": "float",
  "topic_mastery": [{"topic_id": "string", "mastery": "0-1"}],
  "misconceptions": ["string"],
  "feedback_uri": "string"
}
```

### 2.6 Learning Path Agent
**Responsibilities**
- Build personalized learning path based on mastery gaps and goals.
- Prioritize sequencing using prerequisite graph.

**Input events**
- `LearningPathRequested`

**Output events**
- `LearningPathGenerated`
- `LearningPathFailed`

**Input schema**
```json
{
  "student_profile": {"grade": "int", "goals": ["string"], "weekly_time_budget_min": "int"},
  "topic_mastery": [{"topic_id": "string", "mastery": "0-1"}],
  "topic_graph_uri": "string"
}
```

**Output schema** (`LearningPathGenerated.payload`)
```json
{
  "learning_path_id": "uuid",
  "phases": [
    {
      "phase": "int",
      "focus_topics": ["topic_id"],
      "activities": [{"type": "video|quiz|practice", "uri": "string", "duration_min": "int"}]
    }
  ],
  "estimated_completion_weeks": "int"
}
```

### 2.7 Progress Tracking Agent
**Responsibilities**
- Continuously aggregate student interactions and outcomes.
- Compute KPIs: mastery trend, completion, retention risk.

**Input events**
- `ProgressTrackingRequested`
- Passive telemetry events (`ActivityCompleted`, `QuizSubmitted`, `SessionEnded`).

**Output events**
- `ProgressUpdated`
- `ProgressTrackingFailed`
- `AtRiskAlertRaised`

**Input schema**
```json
{
  "student_id": "string",
  "learning_path_id": "uuid",
  "recent_events": ["event_ref"]
}
```

**Output schema** (`ProgressUpdated.payload`)
```json
{
  "student_id": "string",
  "snapshot_time": "ISO-8601",
  "kpis": {
    "overall_mastery": "0-1",
    "completion_rate": "0-1",
    "streak_days": "int",
    "retention_risk": "low|medium|high"
  },
  "next_recommended_action": "string"
}
```

### 2.8 Report Generation Agent
**Responsibilities**
- Build student/teacher reports from workflow artifacts.
- Render JSON + PDF/HTML report.

**Input events**
- `ReportGenerationRequested`

**Output events**
- `ReportGenerated`
- `ReportGenerationFailed`

**Input schema**
```json
{
  "student_id": "string",
  "artifacts": {
    "evaluation_id": "uuid",
    "learning_path_id": "uuid",
    "progress_snapshot_id": "uuid"
  },
  "format": ["json", "pdf"]
}
```

**Output schema** (`ReportGenerated.payload`)
```json
{
  "report_id": "uuid",
  "report_uri": "string",
  "summary": {
    "score": "float",
    "mastery": "0-1",
    "risk": "low|medium|high"
  }
}
```

---

## 3) Communication Pattern

- **Primary**: Asynchronous pub/sub via topics (event-driven).
- **Command vs Event**:
  - `*Requested` = command-style intent from Orchestrator.
  - `*Completed/*Failed` = immutable domain events from worker agents.
- **Delivery semantics**:
  - At-least-once delivery.
  - Idempotent handlers (dedupe by `event_id`).
- **Topic strategy**:
  - `workflow.requests`, `workflow.results`, `workflow.failures`, `telemetry.progress`.
  - Partition by `student_id` to preserve per-student ordering.
- **Schema governance**:
  - JSON Schema + registry.
  - Backward compatible evolution via `schema_version`.

---

## 4) State Management Strategy

Use **hybrid event sourcing + materialized views**:

1. **Event Store**
   - Append-only store of all workflow events.
   - Enables replay, auditing, and model retraining.

2. **Workflow State Store**
   - Materialized view keyed by `workflow_id`.
   - Tracks status per stage (`pending|running|done|failed`).

3. **Student State Store**
   - Materialized view keyed by `student_id`.
   - Stores latest mastery map, path version, and KPI snapshots.

4. **Saga/Process Manager (in Orchestrator)**
   - Controls long-running transaction across agents.
   - Compensation examples:
     - If `ReportGenerationFailed`, mark workflow partial-complete + raise manual review task.
     - If `EvaluationFailed`, retry with alternate scorer profile.

---

## 5) Memory Per Student

A multi-layer memory model:

- **Short-term session memory (TTL: hours-days)**
  - Recent attempts, current topic context, active hints.
  - Fast cache (Redis) for low-latency adaptation.

- **Long-term learning memory (TTL: months-years)**
  - Historical mastery trajectory, misconception history, preferred content type.
  - Stored in relational/document DB.

- **Semantic memory**
  - Embeddings for notes, previous explanations, and question rationales.
  - Vector store for retrieval-augmented personalization.

- **Memory write policy**
  - Write only on meaningful events (`EvaluationCompleted`, `ActivityCompleted`, `ProgressUpdated`).
  - Include confidence score and source provenance.

- **Privacy controls**
  - PII tokenization/encryption at rest.
  - Tenant + student scoped access controls.
  - Configurable retention and right-to-delete workflow.

---

## 6) Error Handling Strategy

- **Standard failure event**
```json
{
  "error_code": "string",
  "error_type": "TRANSIENT|PERMANENT|VALIDATION|DEPENDENCY",
  "message": "safe message",
  "retryable": true,
  "failed_stage": "TopicExtraction",
  "context": {"provider": "ocr_service"}
}
```

- **Retries**
  - Exponential backoff with jitter for transient errors.
  - Max retry per stage (e.g., 3).

- **Dead-letter queue (DLQ)**
  - Non-retryable or max-retry-exceeded events routed to DLQ.
  - Ops dashboard + replay tooling.

- **Circuit breakers**
  - For OCR/LLM/storage dependencies.
  - Fallback models/providers when available.

- **Timeouts and SLA guards**
  - Per stage timeout + global workflow timeout.
  - Emit `WorkflowFailed` if SLA exceeded.

- **Observability**
  - Distributed traces using `trace_id` across all events.
  - Metrics: p95 stage latency, retry count, DLQ rate, success ratio.

---

## 7) Text Flow Diagrams

### 7.1 End-to-End Main Flow

```text
[Client/API]
   |
   | LearningRequestReceived
   v
[Orchestrator]
   |--> PDFProcessRequested ----------------------> [PDF Processing Agent]
   |<-- PDFProcessed / PDFProcessingFailed --------|
   |
   |--> TopicExtractionRequested -----------------> [Topic Extraction Agent]
   |<-- TopicsExtracted / TopicExtractionFailed ---|
   |
   |--> TestGenerationRequested ------------------> [Test Generator Agent]
   |<-- TestGenerated / TestGenerationFailed ------|
   |
   |--> EvaluationRequested -----------------------> [Evaluation Agent]
   |<-- EvaluationCompleted / EvaluationFailed ----|
   |
   |--> LearningPathRequested --------------------> [Learning Path Agent]
   |<-- LearningPathGenerated / LearningPathFailed |
   |
   |--> ProgressTrackingRequested ----------------> [Progress Tracking Agent]
   |<-- ProgressUpdated / ProgressTrackingFailed --|
   |
   |--> ReportGenerationRequested ----------------> [Report Generation Agent]
   |<-- ReportGenerated / ReportGenerationFailed -|
   |
   |--> WorkflowCompleted / WorkflowFailed
   v
[Client/API Notification]
```

### 7.2 Error + Retry + DLQ Flow

```text
[Agent X] -- emits --> [StageFailed(retryable=true)] --> [Orchestrator]
   |                                                    |
   |                                                    | retry policy check
   |                                                    v
   |<------------------------- re-emit StageRequested --|

If retries exhausted or retryable=false:
[Orchestrator] --> [workflow.failures topic] --> [DLQ Consumer]
                                         |--> [Ops Alert]
                                         |--> [Manual Replay Tool]
```

### 7.3 Student Memory Update Flow

```text
[EvaluationCompleted] / [ActivityCompleted] / [ProgressUpdated]
                |
                v
        [Memory Writer Service]
          |        |          |
          |        |          +--> [Vector Store: semantic memory]
          |        +-------------> [Student Profile DB: long-term memory]
          +----------------------> [Redis: short-term session memory]
```

### 7.4 Progress Streaming Flow

```text
[LMS/App Events] --> [telemetry.progress topic] --> [Progress Tracking Agent]
                                                      |
                                                      +--> ProgressUpdated
                                                      +--> AtRiskAlertRaised
                                                                |
                                                                v
                                                    [Teacher Dashboard / Notification Service]
```

---

## 8) Scalability Notes

- Scale workers horizontally by topic partition and consumer group.
- Separate heavy CPU stages (OCR, scoring) to dedicated queues.
- Use backpressure controls (rate limit + max in-flight per student).
- Keep payloads lightweight; pass large artifacts as object-store URIs.
- Support replay by date range, tenant, or workflow ID for recovery.
