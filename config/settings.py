from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    env: str
    llm_provider: str
    llm_model: str
    rate_limit_per_minute: int


def load_settings() -> Settings:
    return Settings(
        env=os.getenv("APP_ENV", "dev"),
        llm_provider=os.getenv("LLM_PROVIDER", "mock"),
        llm_model=os.getenv("LLM_MODEL", "mock-1"),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")),
    )
