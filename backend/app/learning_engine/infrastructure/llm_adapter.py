from __future__ import annotations

from app.learning_engine.domain.ports import LLMPort
from app.services.llm_service import chat_json


class OpenAILLMAdapter(LLMPort):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
