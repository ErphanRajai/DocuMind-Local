import os
from collections import OrderedDict
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Importing tests must never open the user's document database or download a model.
os.environ["DB_URL"] = "sqlite://"
with patch("fastembed.SparseTextEmbedding"), patch("qdrant_client.QdrantClient"):
    import app.database as database
    import app.main as main_module
    import app.services.documents as documents
    from app.main import app
    from app.services.context_budget import TokenCounter
    from app.services.llm_service import LLMService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_generation_state(monkeypatch):
    monkeypatch.setattr(LLMService, "_profiles", OrderedDict())
    monkeypatch.setattr(LLMService, "_profile_lock", None)
    monkeypatch.setattr(LLMService, "_generation_lock", None)


@pytest.fixture
def pdf_bytes():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "DocuMind test document. The garden workshop is on Saturday at ten. " * 3)
        return document.tobytes()


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine)
    database.Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(documents, "SessionLocal", factory)
    monkeypatch.setattr(documents, "UPLOAD_DIR", str(tmp_path / "uploads"))
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(main_module, "init_vector_db", lambda: None)
    monkeypatch.setattr(LLMService, "model_profile", AsyncMock(return_value={"counter": TokenCounter(), "can_disable_thinking": False}))

    async def inline_pdf_work(function, *args):
        return function(*args)

    async def index(*args, **kwargs):
        return None

    monkeypatch.setattr(main_module.pdf_executor, "run", inline_pdf_work)
    monkeypatch.setattr("app.routers.summarizer.store_chunks_in_qdrant", index)
    with TestClient(app) as test_client:
        yield test_client
