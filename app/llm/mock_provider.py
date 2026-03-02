from collections.abc import AsyncIterator
from typing import Any

from app.domain.interfaces.llm_provider_interface import LLMProviderInterface


class MockLLMProvider(LLMProviderInterface):
    async def generate(self, prompt: str, *, model: str) -> str:
        return f"[{model}] {prompt}"

    async def stream(self, prompt: str, *, model: str) -> AsyncIterator[str]:
        for token in [f"[{model}]", *prompt.split()[:3]]:
            yield token

    async def structured_output(
        self, prompt: str, schema: dict[str, Any], *, model: str
    ) -> dict[str, Any]:
        return {"steps": ["tool:search:enterprise multi-agent architecture", "tool:codegen:scaffold"]}

    async def embeddings(self, texts: list[str], *, model: str) -> list[list[float]]:
        return [[float(len(text))] for text in texts]
