import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import CompileError, OperationalError
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.db.base import Base


TEST_DATABASE_URL = os.environ["DATABASE_URL"]
TEST_ENGINE = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False} if TEST_DATABASE_URL.startswith("sqlite") else {},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def _create_test_schema() -> None:
    for table in Base.metadata.sorted_tables:
        try:
            table.create(bind=TEST_ENGINE, checkfirst=True)
        except (CompileError, OperationalError):
            # Skip tables that rely on unsupported dialect-specific types in SQLite.
            continue


def _drop_test_schema() -> None:
    for table in reversed(Base.metadata.sorted_tables):
        try:
            table.drop(bind=TEST_ENGINE, checkfirst=True)
        except (CompileError, OperationalError):
            continue


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    _create_test_schema()
    yield
    _drop_test_schema()


@pytest.fixture
def client():
    from app.main import app

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return {"AUTH_DISABLED": "1", "OPENAI_API_KEY": "test-key"}


@pytest.fixture
def mock_rag(monkeypatch):
    from app.services import rag_service

    fake = {"query": "stub", "chunks": [{"text": "fixed context"}], "sources": []}
    monkeypatch.setattr(rag_service, "retrieve_and_log", lambda *args, **kwargs: fake)
    return fake
