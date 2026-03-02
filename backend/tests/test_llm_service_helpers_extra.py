from app.services import llm_service


def test_placeholder_key_detection():
    assert llm_service._looks_like_placeholder_key("your_api_key") is True
    assert llm_service._looks_like_placeholder_key("sk-real-key") is False
    assert llm_service._looks_like_placeholder_key("xxxx-demo-key") is True


def test_parse_json_object_env():
    obj = llm_service._parse_json_object_env("OPENAI_EXTRA_HEADERS_JSON", '{"x": 1}')
    assert obj == {"x": 1}


def test_parse_json_object_env_invalid_raises():
    try:
        llm_service._parse_json_object_env("OPENAI_EXTRA_HEADERS_JSON", "[]")
    except RuntimeError as exc:
        assert "must be a JSON object" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_provider_detection_and_merge(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1", raising=False)
    assert llm_service._is_dashscope_provider() is True
    monkeypatch.setattr(llm_service.settings, "OPENAI_BASE_URL", "http://localhost:11434/v1", raising=False)
    assert llm_service._is_ollama_provider() is True
    assert llm_service._merge_dicts({"a": 1}, None, {"b": 2}) == {"a": 1, "b": 2}


def test_circuit_breaker_opens_and_recovers(monkeypatch):
    cb = llm_service._CircuitBreaker()
    cb.FAILURE_THRESHOLD = 2
    cb.RECOVERY_TIMEOUT = 0.01

    cb.record_failure()
    assert cb.is_open is False
    cb.record_failure()
    assert cb.is_open is True

    import time

    time.sleep(0.02)
    assert cb.is_open is False
    cb.record_success()
    assert cb.is_open is False
