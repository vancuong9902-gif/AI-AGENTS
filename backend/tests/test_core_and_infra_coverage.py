import logging
import types

from fastapi import FastAPI

from app.core import logging as core_logging
from app.core import observability
from app.infra import cache, event_bus, queue


class _DummyClient:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


_CACHE_CLIENT = _DummyClient()


class _DummyRedisModule:
    class Redis:
        @staticmethod
        def from_url(url, decode_responses=True):
            return _CACHE_CLIENT


class _ExplodingRedisModule:
    class Redis:
        @staticmethod
        def from_url(url, decode_responses=True):
            raise RuntimeError("boom")


def test_json_log_formatter_includes_optional_fields():
    formatter = core_logging.JsonLogFormatter()
    try:
        raise ValueError("bad")
    except ValueError:
        record = logging.LogRecord(
            name="unit-test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=__import__("sys").exc_info(),
        )
    record.request_id = "rid-1"
    out = formatter.format(record)
    assert '"message": "hello world"' in out
    assert '"request_id": "rid-1"' in out
    assert '"exception"' in out


def test_configure_logging_idempotent(monkeypatch):
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    for h in list(root.handlers):
        root.removeHandler(h)

    monkeypatch.setenv("LOG_LEVEL", "debug")
    core_logging.configure_logging()
    handler_count = len(root.handlers)
    core_logging.configure_logging()

    assert len(root.handlers) == handler_count
    assert root.level == logging.DEBUG

    for h in list(root.handlers):
        root.removeHandler(h)
    for h in old_handlers:
        root.addHandler(h)
    root.setLevel(old_level)


def test_setup_observability_disabled(monkeypatch):
    monkeypatch.setattr(observability.settings, "OTEL_ENABLED", False)
    app = FastAPI()
    observability.setup_observability(app)


def test_setup_observability_import_error_logs_exception(monkeypatch):
    monkeypatch.setattr(observability.settings, "OTEL_ENABLED", True)
    calls = []
    monkeypatch.setattr(observability.logger, "exception", lambda msg: calls.append(msg))

    original_import = __import__

    def broken_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", broken_import)
    observability.setup_observability(FastAPI())
    assert calls == ["Failed to initialize OpenTelemetry instrumentation"]


def test_cache_get_set_json_success_and_failures(monkeypatch):
    monkeypatch.setattr(cache, "redis", _DummyRedisModule)
    assert cache.set_json("k", {"v": 1}, ttl_seconds=3) is True
    assert cache.get_json("k") == {"v": 1}

    monkeypatch.setattr(cache, "redis", None)
    assert cache.get_json("k") is None
    assert cache.set_json("k", {"v": 1}) is False

    monkeypatch.setattr(cache, "redis", _ExplodingRedisModule)
    assert cache._get_client() is None


def test_queue_sync_async_and_fetch(monkeypatch):
    monkeypatch.setattr(queue, "_RQ_AVAILABLE", False)
    result = queue.enqueue(lambda a, b: a + b, 1, 2)
    assert result["result"] == 3 and result["sync_executed"] is True

    monkeypatch.setattr(queue, "_RQ_AVAILABLE", True)
    monkeypatch.setattr(queue.settings, "ASYNC_QUEUE_ENABLED", True)

    fake_job = types.SimpleNamespace(id="job-1")

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            pass

        def enqueue(self, fn, *args, **kwargs):
            return fake_job

    monkeypatch.setattr(queue, "Queue", FakeQueue)
    monkeypatch.setattr(queue, "get_redis_conn", lambda: object())
    out = queue.enqueue(lambda: "ok")
    assert out == {"job_id": "job-1", "queued": True, "sync_executed": False}

    class FakeJob:
        @staticmethod
        def fetch(job_id, connection):
            return {"job_id": job_id, "conn": connection}

    monkeypatch.setattr(queue, "Job", FakeJob)
    assert queue.fetch_job("abc")["job_id"] == "abc"


def test_queue_error_paths(monkeypatch):
    monkeypatch.setattr(queue, "_RQ_AVAILABLE", False)
    monkeypatch.setattr(queue, "redis", None)
    with __import__("pytest").raises(RuntimeError):
        queue.get_redis_conn()
    with __import__("pytest").raises(RuntimeError):
        queue.get_queue()
    with __import__("pytest").raises(RuntimeError):
        queue.fetch_job("x")


def test_event_bus_publish_consume_ack_and_pending(monkeypatch):
    calls = {}

    class FakeClient:
        def xadd(self, key, event):
            calls["xadd"] = (key, event)

        def xreadgroup(self, *args, **kwargs):
            return [["stream", ["id-1", {"type": "t"}]]]

        def xgroup_create(self, *args, **kwargs):
            calls["xgroup_create"] = True

        def xack(self, *args, **kwargs):
            calls["xack"] = args

        def xlen(self, *args, **kwargs):
            return 7

    fake_redis = types.SimpleNamespace(
        Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: FakeClient()),
        ResponseError=RuntimeError,
    )
    monkeypatch.setattr(event_bus, "redis", fake_redis)

    bus = event_bus.RedisEventBus("redis://fake")
    event_id = bus.publish("evt", {"a": 1}, user_id="u1")
    assert event_id == calls["xadd"][1]["event_id"]
    assert bus.consume("g", "c")

    bus.ack("g", "id-1")
    assert calls["xack"][1] == "g"
    assert bus.pending_count() == 7


def test_event_bus_consume_group_creation_and_pending_error(monkeypatch):
    calls = {"xgroup": 0}

    class FakeClient:
        def xreadgroup(self, *args, **kwargs):
            raise event_bus.redis.ResponseError("missing")

        def xgroup_create(self, *args, **kwargs):
            calls["xgroup"] += 1

        def xlen(self, *args, **kwargs):
            raise RuntimeError("down")

    fake_redis = types.SimpleNamespace(
        Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: FakeClient()),
        ResponseError=RuntimeError,
    )
    monkeypatch.setattr(event_bus, "redis", fake_redis)

    bus = event_bus.RedisEventBus("redis://fake")
    assert bus.consume("g", "c") == []
    assert calls["xgroup"] == 1
    assert bus.pending_count() == 0
