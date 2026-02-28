from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import settings
from app.services.llm_service import llm_available, ping_model, _looks_like_placeholder_key
from app.services import vector_store


router = APIRouter(tags=["llm"])


@router.get("/llm/status")
def llm_status(request: Request):
    """Lightweight LLM healthcheck.

    Why this exists:
    - The app may silently fall back to offline generators if the LLM call fails.
    - This endpoint lets you confirm: key/base_url/model are wired correctly.

    It does NOT expose your API key.
    """

    base_url = (settings.OPENAI_BASE_URL or "").strip()
    azure_endpoint = (getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or "").strip()

    provider = "openai"
    if azure_endpoint:
        provider = "azure_openai"
    elif base_url:
        if "megallm" in base_url.lower():
            provider = "megallm"
        elif "dashscope" in base_url.lower():
            provider = "alibaba_model_studio"
        elif "ollama" in base_url.lower() or "11434" in base_url:
            provider = "ollama"
        else:
            provider = "openai_compatible"

    # SDK version (useful for debugging provider compatibility)
    sdk_version = None
    try:
        import openai  # type: ignore

        sdk_version = getattr(openai, "__version__", None)
    except Exception:
        sdk_version = None

    data = {
        "llm_available": bool(llm_available()),
        "model": settings.OPENAI_CHAT_MODEL,
        "provider": provider,
        "sdk_version": sdk_version,
        "base_url": base_url or None,
        "azure_endpoint": azure_endpoint or None,
        "base_url_set": bool(base_url),
        "azure_set": bool(azure_endpoint),
        "api_key_set": bool((settings.OPENAI_API_KEY or "").strip()),
        "azure_api_key_set": bool((getattr(settings, "AZURE_OPENAI_API_KEY", None) or "").strip()),
        "api_key_is_placeholder": bool(_looks_like_placeholder_key(settings.OPENAI_API_KEY)),
        "quiz_gen_mode": settings.QUIZ_GEN_MODE,
        "lesson_gen_mode": settings.LESSON_GEN_MODE,
        "semantic_rag_enabled": bool(settings.SEMANTIC_RAG_ENABLED),
        "vector": vector_store.status(),
    }

    # If the LLM isn't configured at all, return config only.
    if not llm_available():
        return {"request_id": request.state.request_id, "data": data, "error": None}

    # Fast, resilient test calls.
    # We DO NOT raise errors here: if a model times out, we report it in test_response,
    # but keep the endpoint responsive so the UI doesn't hang on "Đang kiểm tra…".
    timeout_sec = float(getattr(settings, "OPENAI_STATUS_TEST_TIMEOUT_SEC", 12))
    # Reasoning models often emit "thinking" preambles. 64 tokens is too small and causes
    # finish_reason=length and empty/partial JSON in many gateways.
    max_tokens = max(256, int(getattr(settings, "OPENAI_STATUS_TEST_MAX_TOKENS", 256)))

    # Safety bump for DeepSeek-R1 style models.
    if "deepseek" in (settings.OPENAI_CHAT_MODEL or "").lower() and max_tokens < 256:
        max_tokens = 256

    data["json_model"] = settings.OPENAI_JSON_MODEL

    tests = {}
    if settings.OPENAI_JSON_MODEL:
        tests["json_model"] = ping_model(
            model=settings.OPENAI_JSON_MODEL,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
        )

    tests["chat_model"] = ping_model(
        model=settings.OPENAI_CHAT_MODEL,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
    )

    data["test_response"] = tests
    return {"request_id": request.state.request_id, "data": data, "error": None}
