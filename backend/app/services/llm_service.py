from __future__ import annotations

import ast
import json
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional

from app.core.config import settings


_client = None



PLACEHOLDER_KEY_MARKERS = [
    'your megallm api key',
    'your_api_key',
    'your api key',
    'your-api-key',
    'replace_me',
    'replace-me',
    'changeme',
    'change_me',
    'sk-mega-xxxxxxxx',
    'sk-xxxxxxxx',
    # common env placeholders
    'your_megallm_api_key',
    'your_megallm_key',
    'your_openai_api_key',
    'openai_api_key',
    'megalLM_api_key'.lower(),
]


def _looks_like_placeholder_key(k: str | None) -> bool:
    if not k:
        return False
    ks = (k or '').strip().lower()
    if not ks:
        return False
    if any(m in ks for m in PLACEHOLDER_KEY_MARKERS):
        return True
    # Generic placeholder patterns (avoid false positives by checking that it doesn't look like a real key)
    # - Real keys typically start with: sk-, sk-mega-
    # - Placeholders often contain: your / api / key / demo
    if not ks.startswith("sk-") and all(tok in ks for tok in ("key",)):
        if any(tok in ks for tok in ("your", "demo", "sample", "example", "replace")):
            return True
    # common placeholder pattern like 'xxxxxx'
    if 'xxxx' in ks:
        return True
    return False



def llm_available() -> bool:
    """Return True if we can call an LLM from this backend.

    Supported providers:
    - OpenAI API: set OPENAI_API_KEY
    - OpenAI-compatible local servers (Ollama/LM Studio): set OPENAI_BASE_URL (key can be blank)

    This project is designed to work in two modes:
    - Offline/demo-friendly: keyword RAG + deterministic generators (no LLM).
    - Enhanced: LLM-assisted generation when LLM config is provided.
    """
    has_llm_cfg = (
        bool(settings.OPENAI_API_KEY)
        or bool(getattr(settings, 'OPENAI_BASE_URL', None))
        or bool(getattr(settings, 'AZURE_OPENAI_ENDPOINT', None))
        or bool(getattr(settings, 'AZURE_OPENAI_API_KEY', None))
    )
    if not has_llm_cfg:
        return False

    # Guard against placeholder keys that will always fail auth.
    # - If Azure is configured, validate AZURE_OPENAI_API_KEY.
    # - Otherwise validate OPENAI_API_KEY (when calling OpenAI Cloud).
    azure_cfg = bool(getattr(settings, 'AZURE_OPENAI_ENDPOINT', None) or getattr(settings, 'AZURE_OPENAI_API_KEY', None))
    if azure_cfg:
        if _looks_like_placeholder_key(getattr(settings, 'AZURE_OPENAI_API_KEY', None)):
            return False
    else:
        base_url = (getattr(settings, 'OPENAI_BASE_URL', None) or '').strip()
        # If using OpenAI cloud (no base_url), placeholder keys should disable LLM.
        if not base_url and _looks_like_placeholder_key(settings.OPENAI_API_KEY):
            return False
    try:
        from openai import OpenAI  # type: ignore
        _ = OpenAI
        # Azure client is optional; only needed when AZURE_* is configured
        if getattr(settings, 'AZURE_OPENAI_ENDPOINT', None) or getattr(settings, 'AZURE_OPENAI_API_KEY', None):
            from openai import AzureOpenAI  # type: ignore
            _ = AzureOpenAI
        return True
    except Exception:
        return False


def _parse_json_object_env(name: str, value: str | None) -> Dict[str, Any] | None:
    """Parse a JSON object from an env-var-like string.

    We keep these settings as strings in Pydantic (instead of dict) so that:
    - `.env` editing is straightforward
    - we can provide a clear error message when JSON is invalid
    """

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


def _base_url() -> str:
    return (getattr(settings, "OPENAI_BASE_URL", None) or "").strip()


def _is_dashscope_provider() -> bool:
    """Detect Alibaba Cloud Model Studio / DashScope OpenAI-compatible endpoints."""

    bu = _base_url().lower()
    return bool(bu and "dashscope" in bu)


def _is_ollama_provider() -> bool:
    """Detect Ollama (OpenAI-compatible) endpoints.

    Ollama's OpenAI compatibility is strongest with /v1/chat/completions.
    The newer Responses API may be missing or behave differently across
    versions, so we prefer chat.completions when base_url looks like Ollama.
    """

    bu = _base_url().lower()
    return bool(bu and ("ollama" in bu or "11434" in bu))


def _merge_dicts(*dicts: Dict[str, Any] | None) -> Dict[str, Any] | None:
    out: Dict[str, Any] = {}
    for d in dicts:
        if not d:
            continue
        out.update(d)
    return out or None


def _dashscope_extra_body_defaults() -> Dict[str, Any] | None:
    """Non-standard params for DashScope (only applied when base_url contains "dashscope").

    - Qwen3/Qwen3.5 hybrid-thinking models support:
        enable_thinking (bool)
        thinking_budget (int)

    Ref: Alibaba Cloud Model Studio OpenAI-compatible Chat Completions docs.
    """

    if not _is_dashscope_provider():
        return None

    extra: Dict[str, Any] = {}

    # Default for this project: disable thinking for *JSON* calls for stability.
    # Users can override via env.
    enable_thinking = getattr(settings, "QWEN_ENABLE_THINKING", None)
    if enable_thinking is None:
        enable_thinking = False
    extra["enable_thinking"] = bool(enable_thinking)

    thinking_budget = getattr(settings, "QWEN_THINKING_BUDGET", None)
    if thinking_budget is not None:
        try:
            extra["thinking_budget"] = int(thinking_budget)
        except Exception:
            pass

    return extra or None


def _get_client():
    global _client
    if _client is not None:
        return _client

    # Provider selection priority:
    # 1) Azure OpenAI (if AZURE_OPENAI_ENDPOINT is set)
    # 2) OpenAI-compatible gateway/local (OPENAI_BASE_URL)
    # 3) OpenAI Cloud (OPENAI_API_KEY)

    azure_endpoint = (getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or "").strip() or None
    azure_key = (getattr(settings, "AZURE_OPENAI_API_KEY", None) or "").strip() or None
    azure_api_version = (getattr(settings, "AZURE_OPENAI_API_VERSION", None) or "").strip() or "2024-02-15-preview"

    base_url = (getattr(settings, "OPENAI_BASE_URL", None) or "").strip() or None
    api_key = (settings.OPENAI_API_KEY or '').strip() or None

    # Optional provider-specific headers/query params (JSON strings in .env)
    default_headers = _parse_json_object_env("OPENAI_EXTRA_HEADERS_JSON", getattr(settings, "OPENAI_EXTRA_HEADERS_JSON", None))
    default_query = _parse_json_object_env("OPENAI_EXTRA_QUERY_JSON", getattr(settings, "OPENAI_EXTRA_QUERY_JSON", None))

    # Guard against placeholder keys (e.g. 'Your MegaLLM API Key')
    if _looks_like_placeholder_key(azure_key):
        raise RuntimeError(
            'Azure API key looks like a placeholder. Please replace AZURE_OPENAI_API_KEY in backend/.env with your real Azure OpenAI key.'
        )
    # Only validate OPENAI_API_KEY placeholder when we are NOT using Azure.
    if not azure_endpoint and _looks_like_placeholder_key(api_key):
        raise RuntimeError(
            'API key looks like a placeholder. Please replace OPENAI_API_KEY in backend/.env with your real OpenAI/MegaLLM key or your provider key.'
        )

    # If using Azure OpenAI, require endpoint + key.
    if azure_endpoint:
        if not azure_key:
            raise RuntimeError(
                "Azure OpenAI is selected (AZURE_OPENAI_ENDPOINT is set) but AZURE_OPENAI_API_KEY is missing."
            )

    # If using a local OpenAI-compatible server, a dummy key is fine.
    if not api_key and base_url:
        api_key = "ollama"

    if not api_key and not azure_endpoint:
        raise RuntimeError(
            "LLM is not configured. Set OPENAI_API_KEY (OpenAI) or OPENAI_BASE_URL (Ollama/LM Studio) or AZURE_OPENAI_ENDPOINT+AZURE_OPENAI_API_KEY (Azure OpenAI) in backend/.env"
        )

    try:
        from openai import OpenAI  # type: ignore
        from openai import AzureOpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "openai package is not installed. Install backend requirements to enable LLM generation."
        ) from e

    if azure_endpoint:
        # Azure OpenAI client (model param should be your deployment name)
        # Note: OpenAI SDK uses an HTTP client underneath (httpx). `timeout` is seconds.
        timeout = float(getattr(settings, "OPENAI_HTTP_TIMEOUT_SEC", 120))
        max_retries = int(getattr(settings, "OPENAI_MAX_RETRIES", 1))
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

    # OpenAI python SDK supports base_url for OpenAI-compatible servers.
    timeout = float(getattr(settings, "OPENAI_HTTP_TIMEOUT_SEC", 120))
    max_retries = int(getattr(settings, "OPENAI_MAX_RETRIES", 1))
    if base_url:
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
        )
    else:
        _client = OpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
        )
    return _client


def ping_model(
    model: str,
    prompt: str = 'Return ONLY JSON: {"ok": true}',
    timeout_sec: float | None = None,
    max_tokens: int | None = None,
) -> Dict[str, Any]:
    """Lightweight connectivity/latency test for a single model.

    Goals:
    - Fast enough for the UI healthcheck
    - Robust JSON parsing (handles <think> blocks, markdown fences)
    - Detect model-mismatch on gateways (requested model != returned model)

    This function never raises on normal failures.
    """

    timeout_sec = float(timeout_sec or getattr(settings, "OPENAI_STATUS_TEST_TIMEOUT_SEC", 12))
    max_tokens = max(256, int(max_tokens or getattr(settings, "OPENAI_STATUS_TEST_MAX_TOKENS", 256)))

    # Provider-specific extra_body (e.g., DashScope/Qwen).
    extra_body_cfg = _parse_json_object_env(
        "OPENAI_EXTRA_BODY_JSON",
        getattr(settings, "OPENAI_EXTRA_BODY_JSON", None),
    )
    extra_body = _merge_dicts(_dashscope_extra_body_defaults(), extra_body_cfg)

    # Stronger instruction to reduce "reasoning" preambles
    system = (
        "You are a strict JSON generator. "
        "Output exactly one JSON object and nothing else. "
        "Do not include explanations, markdown fences, or <think> blocks."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    try:
        client = _get_client()
        t0 = time.time()

        raw_text = ""
        finish_reason = None
        returned_model = None
        used_api = None

        prefer_chat = _is_ollama_provider()

        # Prefer Responses API when available (some gateways/models behave better here).
        # However, for Ollama we prefer chat.completions for maximum compatibility.
        if (not prefer_chat) and hasattr(client, "responses") and hasattr(client.responses, "create"):
            used_api = "responses"
            try:
                resp = client.responses.create(
                    model=model,
                    input=messages,
                    text={"format": {"type": "json_object"}},
                    max_output_tokens=int(max_tokens),
                    timeout=float(timeout_sec),
                )
                returned_model = getattr(resp, "model", None)
                raw_text = _extract_response_text(resp) or ""
                # Responses API doesn't always expose finish_reason consistently
                finish_reason = getattr(resp, "finish_reason", None)
            except Exception:
                # Fall back to chat completions
                used_api = None

        if used_api is None:
            used_api = "chat.completions"
            def _call_chat(use_json_mode: bool):
                kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": int(max_tokens),
                    "timeout": float(timeout_sec),
                }
                if extra_body:
                    kwargs["extra_body"] = extra_body
                if use_json_mode and (not _is_ollama_provider()):
                    # Some OpenAI-compatible servers mis-handle response_format.
                    # For Ollama, we prefer plain chat responses + strict instruction.
                    kwargs["response_format"] = {"type": "json_object"}
                return client.chat.completions.create(**kwargs)

            # Try JSON mode first (except Ollama), then retry without if content is empty.
            try:
                res = _call_chat(True)
            except Exception:
                res = _call_chat(False)
            returned_model = getattr(res, "model", None)
            finish_reason = getattr(res.choices[0], "finish_reason", None)
            raw_text = _extract_chat_completion_text(res)
            if not str(raw_text or "").strip():
                # Some providers return empty content when response_format is present.
                try:
                    res2 = _call_chat(False)
                    returned_model = getattr(res2, "model", returned_model)
                    finish_reason = getattr(res2.choices[0], "finish_reason", finish_reason)
                    raw_text = _extract_chat_completion_text(res2)
                except Exception:
                    pass

        dt = time.time() - t0
        raw_text = str(raw_text or "")
        cleaned = _preprocess_llm_text(raw_text)
        head_raw = raw_text.strip()[:160]
        head_clean = cleaned[:160]
        head = head_clean if head_clean else head_raw

        json_parse_ok = False
        ok_value = None
        try:
            # Prefer cleaned text for parsing (removes <think> blocks / fences)
            obj = _safe_json_loads(cleaned or raw_text)
            json_parse_ok = True
            ok_value = obj.get("ok")
            # Normalize common variants
            if isinstance(ok_value, str):
                if ok_value.strip().lower() in {"true", "1", "yes", "ok"}:
                    ok_value = True
                elif ok_value.strip().lower() in {"false", "0", "no"}:
                    ok_value = False
        except Exception:
            json_parse_ok = False

        # Some gateways return fully qualified IDs; use a loose mismatch heuristic.
        req = (model or "").strip()
        ret = (returned_model or "").strip()
        model_mismatch = bool(req and ret and (req != ret) and (req not in ret) and (ret not in req))

        return {
            "ok": True,
            "latency_sec": round(dt, 3),
            "requested_model": model,
            "returned_model": returned_model,
            "finish_reason": finish_reason,
            "api": used_api,
            "content_head_raw": head_raw,
            "content_head_clean": head_clean,
            "content_head": head,
            "json_parse_ok": json_parse_ok,
            "ok_value": ok_value,
            "model_mismatch": model_mismatch,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
            "timeout_sec": timeout_sec,
            "requested_model": model,
        }


_THINK_RE = re.compile(r"<\s*(think|analysis)\s*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```", re.IGNORECASE)


def _preprocess_llm_text(s: str) -> str:
    """Normalize common "messy JSON" wrappers.

    Many reasoning models (e.g., DeepSeek-R1) emit <think>...</think> blocks.
    Some models wrap JSON in markdown fences.
    """
    s = (s or "").strip()
    if not s:
        return ""
    s = _THINK_RE.sub("", s).strip()
    # remove markdown fences if present
    if "```" in s:
        s = _FENCE_RE.sub("", s).strip()
    return s


def _extract_last_json_object(s: str) -> Dict[str, Any] | None:
    """Return the last valid JSON object found in text, or None."""
    s = _preprocess_llm_text(s)
    if not s:
        return None

    dec = json.JSONDecoder()
    last_obj: Dict[str, Any] | None = None
    i = 0
    while True:
        i = s.find("{", i)
        if i < 0:
            break
        try:
            obj, end = dec.raw_decode(s[i:])
            if isinstance(obj, dict):
                last_obj = obj
            i = i + max(1, end)
        except Exception:
            i += 1
    return last_obj


def _safe_json_loads(s: str) -> Dict[str, Any]:
    s2 = _preprocess_llm_text(s)
    if not s2:
        raise ValueError("Empty LLM response (expected JSON).")

    def _try_json(text: str) -> Dict[str, Any] | None:
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def _fix_trailing_commas(text: str) -> str:
        # Common LLM mistake: trailing commas before '}' or ']'
        return re.sub(r",\s*([}\]])", r"\1", text)

    # 1) Fast path: exact JSON
    obj = _try_json(s2)
    if obj is not None:
        return obj

    # 2) Fix common syntax issues and retry
    s3 = _fix_trailing_commas(s2)
    obj = _try_json(s3)
    if obj is not None:
        return obj

    # 3) Robust path: scan for the last valid JSON object
    obj2 = _extract_last_json_object(s3)
    if obj2 is not None:
        return obj2

    # 4) Last resort: Python literal parser for quasi-JSON (single quotes, True/False/None)
    # This is safe (no code execution) and helps with some Qwen/LLM outputs.
    def _try_literal(text: str) -> Dict[str, Any] | None:
        try:
            lit = ast.literal_eval(text)
            return lit if isinstance(lit, dict) else None
        except Exception:
            return None

    # Try direct literal_eval first
    lit_obj = _try_literal(s3)
    if lit_obj is not None:
        return lit_obj

    # Try literal_eval with JSON token normalization
    s4 = re.sub(r"\bnull\b", "None", s3, flags=re.IGNORECASE)
    s4 = re.sub(r"\btrue\b", "True", s4, flags=re.IGNORECASE)
    s4 = re.sub(r"\bfalse\b", "False", s4, flags=re.IGNORECASE)
    lit_obj = _try_literal(s4)
    if lit_obj is not None:
        return lit_obj

    raise ValueError(f"Could not parse JSON from LLM output. Head={s2[:200]!r}")


def _should_auto_json_formatter(model_id: str) -> bool:
    mid = (model_id or "").lower()
    # Heuristic: reasoning models frequently emit chain-of-thought wrappers.
    return any(tok in mid for tok in ["deepseek", "-r1", "reasoning", "grok-"])


def _format_to_json(
    *,
    client: Any,
    raw_output: str,
    original_messages: List[Dict[str, str]],
    formatter_model: str,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    """Use a second model to reformat/extract strict JSON.

    This is the most reliable approach for models that include <think> blocks or drift from JSON.
    """

    # Keep the formatter prompt short but unambiguous.
    payload = {
        "original_messages": original_messages,
        "model_output": raw_output,
    }
    instr = (
        "You are a strict JSON extractor/formatter. "
        "Return ONLY a single valid JSON object and nothing else. "
        "If MODEL_OUTPUT contains one or more JSON objects, extract the best final JSON object. "
        "Otherwise, produce the JSON object that satisfies the constraints/schema described in ORIGINAL_MESSAGES."
    )

    messages = [
        {"role": "system", "content": instr},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    # Try with JSON mode first; retry without for broad compatibility.
    try:
        res = client.chat.completions.create(
            model=formatter_model,
            messages=messages,
            temperature=0,
            max_tokens=int(max_tokens),
            response_format={"type": "json_object"},
        )
    except Exception:
        res = client.chat.completions.create(
            model=formatter_model,
            messages=messages,
            temperature=0,
            max_tokens=int(max_tokens),
        )
    txt = (_extract_chat_completion_text(res) or "").strip()
    return _safe_json_loads(txt)


def _extract_response_text(resp: Any) -> str:
    """Best-effort extraction of text from a Responses API object."""
    # Newer SDKs expose output_text
    if hasattr(resp, "output_text"):
        try:
            return (resp.output_text or "").strip()
        except Exception:
            pass

    # Fallback: traverse output items
    try:
        out = getattr(resp, "output", None)
        if isinstance(out, list):
            parts: list[str] = []
            for item in out:
                # item may be dict-like or object-like
                it_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
                if it_type and str(it_type) != "message":
                    continue
                content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else None)
                if not isinstance(content, list):
                    continue
                for c in content:
                    c_type = getattr(c, "type", None) or (c.get("type") if isinstance(c, dict) else None)
                    if str(c_type) in {"output_text", "text"}:
                        val = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else None)
                        if isinstance(val, str) and val.strip():
                            parts.append(val.strip())
            if parts:
                return "\n".join(parts).strip()
    except Exception:
        pass

    # Last resort
    return ""


def _extract_chat_completion_text(res: Any) -> str:
    """Best-effort extraction of assistant text from a Chat Completions response.

    Some OpenAI-compatible servers return:
    - message.content as a STRING (classic OpenAI chat.completions)
    - message.content as a LIST of content parts (OpenAI-style content blocks)
    - message.content empty but put text into non-standard fields like reasoning_content/thinking
    - legacy choices[0].text

    We handle these variations and fall back to model_dump()/model_dump_json().
    """

    def _parts_to_text(parts):
        out = []
        if isinstance(parts, str):
            return parts
        if not isinstance(parts, list):
            return ""
        for p in parts:
            # Part may be str / dict / pydantic object
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
                continue
            p_text = None
            if isinstance(p, dict):
                p_text = p.get('text') or p.get('content')
            else:
                p_text = getattr(p, 'text', None) or getattr(p, 'content', None)

            if isinstance(p_text, str) and p_text.strip():
                out.append(p_text.strip())
                continue

            if isinstance(p_text, dict):
                t = p_text.get('text') or p_text.get('value')
                if isinstance(t, str) and t.strip():
                    out.append(t.strip())
        return "\n".join(out).strip()

    def _msg_to_text(msg):
        if msg is None:
            return ""

        # Standard field: content
        try:
            content = msg.get('content') if isinstance(msg, dict) else getattr(msg, 'content', None)
            if isinstance(content, str) and content.strip():
                return content.strip()
            t = _parts_to_text(content)
            if t:
                return t
        except Exception:
            pass

        # Non-standard fields sometimes used by reasoning models/providers
        for key in ('reasoning_content', 'reasoning', 'thinking', 'thought', 'analysis'):
            try:
                val = msg.get(key) if isinstance(msg, dict) else getattr(msg, key, None)
                if isinstance(val, str) and val.strip():
                    return val.strip()
                t = _parts_to_text(val)
                if t:
                    return t
            except Exception:
                continue

        return ""

    # 1) Normal SDK object path
    try:
        msg = res.choices[0].message
        t = _msg_to_text(msg)
        if t:
            return t
    except Exception:
        pass

    # 1b) Legacy completions style
    try:
        t = getattr(res.choices[0], 'text', None)
        if isinstance(t, str) and t.strip():
            return t.strip()
    except Exception:
        pass

    # 2) Pydantic model_dump()
    try:
        if hasattr(res, 'model_dump'):
            d = res.model_dump()
            choice0 = (d.get('choices') or [{}])[0]
            msg = choice0.get('message') or {}
            t = _msg_to_text(msg)
            if t:
                return t
            t2 = choice0.get('text')
            if isinstance(t2, str) and t2.strip():
                return t2.strip()
    except Exception:
        pass

    # 3) model_dump_json fallback
    try:
        if hasattr(res, 'model_dump_json'):
            d = json.loads(res.model_dump_json())
            choice0 = (d.get('choices') or [{}])[0]
            msg = choice0.get('message') or {}
            t = _msg_to_text(msg)
            if t:
                return t
            t2 = choice0.get('text')
            if isinstance(t2, str) and t2.strip():
                return t2.strip()
    except Exception:
        pass

    return ""



def chat_json(
    *,
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1200,
    timeout_sec: float | None = None,
) -> Dict[str, Any]:
    """Call an LLM and return a parsed JSON object.

    - Prefer the Responses API (recommended for new projects).
    - Fall back to Chat Completions for broad compatibility.

    We use JSON mode (valid JSON object) to keep the FE stable.

    NOTE: OpenAI-compatible local servers (Ollama/LM Studio) thường chỉ hỗ trợ chat.completions.
    Hàm này đã có fallback nên vẫn chạy tốt.
    """
    client = _get_client()
    m = model or settings.OPENAI_CHAT_MODEL

    # Provider-specific extra_body (e.g., DashScope/Qwen) + user-supplied extra body.
    extra_body_cfg = _parse_json_object_env(
        "OPENAI_EXTRA_BODY_JSON",
        getattr(settings, "OPENAI_EXTRA_BODY_JSON", None),
    )
    extra_body = _merge_dicts(_dashscope_extra_body_defaults(), extra_body_cfg)

    # Some providers (notably DashScope) require that you *explicitly* instruct JSON output
    # when using response_format={"type":"json_object"}. We add a guard system message
    # to make the intent unambiguous.
    json_guard = {
        "role": "system",
        "content": (
            "You are a strict JSON generator. "
            "Output exactly ONE valid JSON object and nothing else. "
            "Do NOT include explanations, markdown fences, or <think>/<analysis> blocks."
        ),
    }
    guarded_messages = [json_guard] + (messages or [])

    req_timeout = float(timeout_sec) if timeout_sec is not None else None

    # Optional "JSON formatter" model (2-step: reasoning -> formatter) for strict JSON stability.
    formatter_model = (getattr(settings, "OPENAI_JSON_MODEL", None) or "").strip() or None
    if not formatter_model and _should_auto_json_formatter(m):
        # A safe, low-cost default for MegaLLM-style gateways.
        formatter_model = "openai-gpt-oss-20b"

    prefer_chat = _is_ollama_provider()

    # 1) Try Responses API (if available in the installed SDK & provider)
    try:
        if (not prefer_chat) and hasattr(client, "responses") and hasattr(client.responses, "create"):
            effort = (getattr(settings, "OPENAI_REASONING_EFFORT", "") or "").strip().lower()
            # IMPORTANT (GPT-5.2+): Some params (temperature/top_p/logprobs) are only
            # supported when reasoning effort is "none".
            # Ref: OpenAI docs (GPT-5.2 parameter compatibility).
            kwargs: Dict[str, Any] = {
                "model": m,
                "input": guarded_messages,
                "text": {"format": {"type": "json_object"}},
                "max_output_tokens": int(max_tokens),
            }
            if extra_body:
                kwargs["extra_body"] = extra_body
            if req_timeout is not None:
                kwargs["timeout"] = req_timeout
            if effort:
                # reasoning.effort is supported by GPT-5.x and newer reasoning-capable models
                kwargs["reasoning"] = {"effort": effort}

            # Only send temperature when effort is unset or explicitly "none".
            if not effort or effort == "none":
                kwargs["temperature"] = float(temperature)

            resp = client.responses.create(**kwargs)
            content = _extract_response_text(resp)
            if content:
                try:
                    return _safe_json_loads(content)
                except Exception:
                    # Fall back to formatter model if configured
                    if formatter_model and formatter_model != m:
                        return _format_to_json(
                            client=client,
                            raw_output=content,
                            original_messages=messages,
                            formatter_model=formatter_model,
                        )
                    raise
    except Exception:
        # fall back to chat.completions
        pass

    # 2) Fallback: Chat Completions API
    # Some OpenAI-compatible providers (including certain gateways) may reject "response_format".
    # We'll try JSON mode first, then retry without it (still expecting JSON by instruction).
    def _call_chat(_messages: List[Dict[str, str]], _max_tokens: int, _temp: float):
        base_kwargs: Dict[str, Any] = {
            "model": m,
            "messages": _messages,
            "temperature": float(_temp),
            "max_tokens": int(_max_tokens),
        }
        if extra_body:
            base_kwargs["extra_body"] = extra_body
        if req_timeout is not None:
            base_kwargs["timeout"] = req_timeout

        # Ollama's OpenAI-compatible API is generally happier without response_format.
        if _is_ollama_provider():
            return client.chat.completions.create(**base_kwargs)

        try:
            return client.chat.completions.create(
                **{
                    **base_kwargs,
                    "response_format": {"type": "json_object"},
                }
            )
        except Exception:
            return client.chat.completions.create(**base_kwargs)

    # First attempt
    res = _call_chat(guarded_messages, int(max_tokens), float(temperature))
    content = (_extract_chat_completion_text(res) or "").strip()
    try:
        return _safe_json_loads(content)
    except Exception:
        # Retry once with stronger guard + more tokens (useful for <think> models)
        guard = {
            "role": "system",
            "content": (
                "CRITICAL: Output ONLY a single valid JSON object. "
                "Do NOT include any <think>/<analysis> text, markdown fences, or explanations."
            ),
        }
        retry_tokens = min(int(max_tokens) * 2, 4096)
        res2 = _call_chat([guard] + guarded_messages, retry_tokens, 0.0)
        content2 = (_extract_chat_completion_text(res2) or "").strip()
        try:
            return _safe_json_loads(content2)
        except Exception:
            # Final fallback: formatter model
            if formatter_model and formatter_model != m:
                return _format_to_json(
                    client=client,
                    raw_output=content2 or content,
                    original_messages=messages,
                    formatter_model=formatter_model,
                )
            raise


def chat_text(
    *,
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1400,
    timeout_sec: float | None = None,
) -> str:
    """Call an LLM and return plain text.

    Use this for long-form outputs (Markdown study guides, lesson notes) where
    strict JSON mode would be brittle.

    - Prefer Chat Completions for Ollama/OpenAI-compatible local servers.
    - Try Responses API when available and provider supports it.
    """

    client = _get_client()
    m = model or settings.OPENAI_CHAT_MODEL

    extra_body_cfg = _parse_json_object_env(
        "OPENAI_EXTRA_BODY_JSON",
        getattr(settings, "OPENAI_EXTRA_BODY_JSON", None),
    )
    extra_body = _merge_dicts(_dashscope_extra_body_defaults(), extra_body_cfg)
    req_timeout = float(timeout_sec) if timeout_sec is not None else None
    prefer_chat = _is_ollama_provider()

    # 1) Responses API (best when available)
    try:
        if (not prefer_chat) and hasattr(client, "responses") and hasattr(client.responses, "create"):
            effort = (getattr(settings, "OPENAI_REASONING_EFFORT", "") or "").strip().lower()
            kwargs: Dict[str, Any] = {
                "model": m,
                "input": messages or [],
                "max_output_tokens": int(max_tokens),
            }
            if extra_body:
                kwargs["extra_body"] = extra_body
            if req_timeout is not None:
                kwargs["timeout"] = req_timeout
            if effort:
                kwargs["reasoning"] = {"effort": effort}
            if not effort or effort == "none":
                kwargs["temperature"] = float(temperature)

            resp = client.responses.create(**kwargs)
            txt = _extract_response_text(resp)
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
    except Exception:
        pass

    # 2) Chat Completions fallback (broad compatibility)
    kwargs2: Dict[str, Any] = {
        "model": m,
        "messages": messages or [],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    if extra_body:
        kwargs2["extra_body"] = extra_body
    if req_timeout is not None:
        kwargs2["timeout"] = req_timeout
    res = client.chat.completions.create(**kwargs2)
    txt = _extract_chat_completion_text(res)
    return (txt or "").strip()


def compact_ws(text: str) -> str:
    return " ".join((text or "").split())


def pack_chunks(
    chunks: List[Dict[str, Any]],
    *,
    max_chunks: int = 6,
    max_chars_per_chunk: int = 900,
    max_total_chars: int = 5200,
) -> List[Dict[str, Any]]:
    """Prepare chunks to be sent to an LLM (keep it short + stable)."""
    out: List[Dict[str, Any]] = []
    total = 0
    for c in (chunks or [])[: max(1, int(max_chunks))]:
        cid = c.get("chunk_id")
        try:
            cid_int = int(cid)
        except Exception:
            continue
        title = c.get("document_title") or c.get("title")
        text = compact_ws(c.get("text") or "")
        text = text[: max_chars_per_chunk]
        if not text:
            continue
        item = {"chunk_id": cid_int, "title": title, "text": text}
        out.append(item)
        total += len(text)
        if total >= max_total_chars:
            break
    return out
