from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
import app.routers.summarizer as summarizer_module
from app.database import Base, get_db
from app.main import app

# Shared in-memory SQLite database for all test threads & worker sessions
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session(monkeypatch):
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    # Point SessionLocal in both modules to the test engine
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(summarizer_module, "SessionLocal", TestingSessionLocal)

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Mock vector DB initialization on startup to avoid getaddrinfo delays
    with patch("app.main.init_vector_db", new_callable=AsyncMock):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()