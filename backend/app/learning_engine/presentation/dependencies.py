from __future__ import annotations

import asyncio

from app.learning_engine.application.agents import AssessmentAgent, ExerciseAgent, LearningPathAgent, ReportingAgent, TopicExtractionAgent
from app.learning_engine.application.services import LearningOrchestratorService
from app.learning_engine.infrastructure.repositories import InMemoryAssessmentRepository, InMemoryTopicRepository
from app.learning_engine.infrastructure.vector_adapter import InMemoryVectorAdapter
from app.learning_engine.infrastructure.llm_adapter import OpenAILLMAdapter


class AsyncLLMAdapter(OpenAILLMAdapter):
    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return await asyncio.to_thread(super().generate_json, system_prompt, user_prompt)


def build_learning_service() -> LearningOrchestratorService:
    llm = AsyncLLMAdapter()
    vector_adapter = InMemoryVectorAdapter()
    topic_repo = InMemoryTopicRepository()
    assessment_repo = InMemoryAssessmentRepository()
    return LearningOrchestratorService(
        topic_repo=topic_repo,
        assessment_repo=assessment_repo,
        vector_index=vector_adapter,
        topic_agent=TopicExtractionAgent(llm=llm),
        assessment_agent=AssessmentAgent(llm=llm),
        path_agent=LearningPathAgent(llm=llm),
        exercise_agent=ExerciseAgent(llm=llm, vector_index=vector_adapter),
        reporting_agent=ReportingAgent(llm=llm),
    )
