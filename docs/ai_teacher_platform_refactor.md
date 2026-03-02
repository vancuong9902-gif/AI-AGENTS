# AI Teacher Platform – Production Refactor Blueprint

## Target Folder Structure (Clean Architecture)

```text
backend/app/learning_engine/
  presentation/
    router.py
    schemas.py
    dependencies.py
  application/
    agents.py
    services.py
  domain/
    models.py
    ports.py
  infrastructure/
    repositories.py
    vector_adapter.py
    llm_adapter.py
```

## Multi-agent Orchestration Flow

1. **TopicExtractionAgent**: ingest PDF text and produce semantic topic graph.
2. **AssessmentAgent**: generate adaptive entrance test and classify student level.
3. **LearningPathAgent**: produce personalized sequence of learning steps.
4. **ExerciseAgent**: generate exercises using RAG context.
5. **ReportingAgent**: summarize progress + final exam outcomes into report.

## RAG Pipeline

1. Upload PDF -> parse text.
2. Chunk and embed topic summaries.
3. Upsert chunks into vector index (FAISS/Chroma compatible port).
4. Retrieve top-k chunks for exercise generation and tutoring.
5. Ground model outputs with retrieved context.

## Scalability Notes

- Use async API boundary and non-blocking I/O in FastAPI handlers.
- Isolate model calls behind `LLMPort` to support horizontal worker scaling.
- Keep orchestration stateless; persist progress/report in PostgreSQL.
- Put long tasks (topic extraction, exam generation) on queue workers.
- Add Redis for caching and throttling.

## Internal Prompts

Prompts are centralized in `docs/ai_teacher_prompts.md` and injected by agents.
