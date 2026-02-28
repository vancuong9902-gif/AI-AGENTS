from __future__ import annotations

import json

from typing import Any, Dict, List

from functools import lru_cache

from app.core.config import settings

_client = None


def _parse_json_object_env(name: str, value: str | None) -> Dict[str, Any] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise RuntimeError(
            f"{name} must be a valid JSON object string. Example: {name}={{\"foo\":\"bar\"}}. Error: {type(e).__name__}: {str(e)[:120]}"
        ) from e
    if not isinstance(obj, dict):
        raise RuntimeError(f"{name} must be a JSON object ({{...}}), got {type(obj).__name__}.")
    return obj


def _get_openai_client():
    """Create a cached OpenAI client.

    Lazy-imports OpenAI so the backend can still start in "keyword-only" mode
    when the optional dependency isn't installed.
    """
    global _client
    if _client is not None:
        return _client

    try:
        from openai import OpenAI  # type: ignore
        from openai import AzureOpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "openai package is not installed. Install backend requirements to enable semantic RAG."
        ) from e

    # Optional provider-specific headers/query params (JSON strings in .env)
    default_headers = _parse_json_object_env(
        "OPENAI_EXTRA_HEADERS_JSON",
        getattr(settings, "OPENAI_EXTRA_HEADERS_JSON", None),
    )
    default_query = _parse_json_object_env(
        "OPENAI_EXTRA_QUERY_JSON",
        getattr(settings, "OPENAI_EXTRA_QUERY_JSON", None),
    )

    timeout = float(getattr(settings, "OPENAI_HTTP_TIMEOUT_SEC", 120))
    max_retries = int(getattr(settings, "OPENAI_MAX_RETRIES", 1))

    # Prefer Azure OpenAI when configured
    azure_endpoint = (getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or "").strip() or None
    azure_key = (getattr(settings, "AZURE_OPENAI_API_KEY", None) or "").strip() or None
    azure_api_version = (getattr(settings, "AZURE_OPENAI_API_VERSION", None) or "").strip() or "2024-02-15-preview"
    if azure_endpoint:
        if not azure_key:
            raise RuntimeError(
                "Azure OpenAI is selected (AZURE_OPENAI_ENDPOINT is set) but AZURE_OPENAI_API_KEY is missing."
            )
        _client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=azure_api_version,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
        )
        return _client

    base_url = (getattr(settings, "OPENAI_BASE_URL", None) or "").strip() or None
    if base_url:
        _client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
        )
    else:
        _client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
        )
    return _client



def _norm_text(text: str) -> str:
    return " ".join((text or "").split())


@lru_cache(maxsize=256)
def _embed_text_cached(text: str, model: str) -> tuple[float, ...]:
    # Use 1-item batch to reuse embed_texts logic and client cache
    emb = embed_texts([text], model=model)[0]
    return tuple(float(x) for x in emb)


def embed_texts(texts: List[str], model: str | None = None) -> List[List[float]]:
    """Return embeddings for a list of strings."""
    if not getattr(settings, "SEMANTIC_RAG_ENABLED", True):
        raise RuntimeError(
            "Semantic RAG is disabled (SEMANTIC_RAG_ENABLED=false). Enable it if you want embeddings + FAISS."
        )
    if not (settings.OPENAI_API_KEY or getattr(settings, "AZURE_OPENAI_API_KEY", None)):
        raise RuntimeError(
            "Embeddings provider key is missing. Set OPENAI_API_KEY (OpenAI) or AZURE_OPENAI_API_KEY (Azure OpenAI) to enable semantic RAG."
        )
    client = _get_openai_client()
    m = (model or getattr(settings, "OPENAI_EMBEDDING_MODEL", None) or "text-embedding-3-small").strip()
    res = client.embeddings.create(model=m, input=texts)
    data = sorted(res.data, key=lambda x: x.index)
    return [d.embedding for d in data]


def embed_text(text: str, model: str | None = None) -> List[float]:
    t = _norm_text(text)
    m = (model or getattr(settings, "OPENAI_EMBEDDING_MODEL", None) or "text-embedding-3-small").strip()
    return list(_embed_text_cached(t, m))
