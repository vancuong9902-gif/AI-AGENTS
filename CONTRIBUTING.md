# Test & Coverage Notes

## Automated tests added
- Added **14** new service-focused test modules under `backend/tests/services/`.
- Added **29** new passing tests covering normal flow, edge cases, and exception/fallback paths.

## Coverage report summary
- CI is configured to run branch coverage with fail-under 70%.
- Local environment could not execute `pytest-cov` due package index connectivity restrictions, so a local numeric total is not available in this run.

## Modules requiring mocks
The new tests use mocks/monkeypatching for external dependencies in these areas:
- LLM availability and chat responses (OpenAI-facing logic)
- RAG retrieval behavior
- Environment-driven settings flags

## Where mocks are defined
- Per-test monkeypatching in:
  - `backend/tests/services/test_agent_service.py`
  - `backend/tests/services/test_homework_service.py`
- Shared fixture-level mocking in:
  - `backend/tests/conftest.py` (`mock_env`, `mock_rag`)
