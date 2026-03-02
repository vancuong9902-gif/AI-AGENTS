import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)


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
