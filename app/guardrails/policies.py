from typing import Any


class GuardrailViolation(ValueError):
    pass


def validate_payload_against_schema(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    missing = [field for field in required if field not in payload]
    if missing:
        raise GuardrailViolation(f"Missing required fields: {missing}")


def enforce_token_limit(prompt: str, max_chars: int = 12_000) -> None:
    if len(prompt) > max_chars:
        raise GuardrailViolation("Prompt exceeds configured token budget")
