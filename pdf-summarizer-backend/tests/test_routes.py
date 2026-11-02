import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import PDFDocument
from app.routers import summarizer
from app.services import documents
from app.services.errors import GenerationError
from app.services.llm_service import LLMService
from app.services.pdf_processor import PDFProcessorService


def upload(client, data, name="sample.pdf"):
    return client.post("/summarizer/upload", files=[("files", (name, data, "application/pdf"))])


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def test_upload_extracts_once_and_never_generates_summary(client, pdf_bytes, db_session, monkeypatch):
    extract = Mock(wraps=PDFProcessorService.extract_document)
    generate = AsyncMock()
    monkeypatch.setattr(PDFProcessorService, "extract_document", extract)
    monkeypatch.setattr(LLMService, "summarize_chunks", generate)
    response = upload(client, pdf_bytes, "../../sample.pdf")
    assert response.status_code == 201
    record = response.json()[0]
    assert record["filename"] == "sample.pdf"
    status = client.get(f"/summarizer/documents/{record['id']}").json()
    assert status["status"] == "completed"
    assert status["summary"] is None and status["error_message"] is None
    assert "raw_text" not in status
    assert extract.call_count == 1
    generate.assert_not_called()
    paths = list(Path(documents.UPLOAD_DIR).glob("*"))
    assert len(paths) == 1 and paths[0].name != "sample.pdf"
    assert db_session.query(PDFDocument).count() == 1


@pytest.mark.parametrize("name,data", [("bad.txt", b"test"), ("fake.pdf", b"not a PDF"), ("empty.pdf", b"")])
def test_rejected_upload_leaves_no_files_or_records(client, db_session, name, data):
    assert upload(client, data, name).status_code == 400
    assert db_session.query(PDFDocument).count() == 0
    assert not list(Path(documents.UPLOAD_DIR).glob("*"))


def test_rejects_more_than_three_files(client, pdf_bytes, db_session):
    files = [("files", (f"{index}.pdf", pdf_bytes, "application/pdf")) for index in range(4)]
    assert client.post("/summarizer/upload", files=files).status_code == 400
    assert db_session.query(PDFDocument).count() == 0


def test_oversized_file_cleans_entire_batch(client, pdf_bytes, db_session, monkeypatch):
    monkeypatch.setattr(documents, "MAX_UPLOAD_BYTES", len(pdf_bytes) + 1)
    files = [("files", ("good.pdf", pdf_bytes)), ("files", ("large.pdf", pdf_bytes + b"extra"))]
    assert client.post("/summarizer/upload", files=files).status_code == 413
    assert db_session.query(PDFDocument).count() == 0
    assert not list(Path(documents.UPLOAD_DIR).glob("*"))


def test_corrupt_second_file_rolls_back_batch(client, pdf_bytes, db_session):
    response = client.post("/summarizer/upload", files=[("files", ("good.pdf", pdf_bytes)), ("files", ("bad.pdf", b"bad"))])
    assert response.status_code == 400
    assert db_session.query(PDFDocument).count() == 0
    assert not list(Path(documents.UPLOAD_DIR).glob("*"))


def test_database_failure_removes_staged_file(client, pdf_bytes, monkeypatch):
    def fail(_staged):
        raise RuntimeError("simulated database failure")
    monkeypatch.setattr(documents, "_create_records", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        upload(client, pdf_bytes)
    assert not list(Path(documents.UPLOAD_DIR).glob("*"))


def test_old_streaming_upload_is_retired(client, pdf_bytes, db_session):
    assert client.post("/summarizer/upload/stream", files=[("files", ("test.pdf", pdf_bytes))]).status_code == 410
    assert db_session.query(PDFDocument).count() == 0


def test_missing_document(client):
    assert client.get("/summarizer/documents/99999").status_code == 404
    assert client.post("/summarizer/summary/stream", json={"pdf_ids": [99999]}).status_code == 404


def test_pending_document_cannot_be_used_for_answers(client, db_session):
    record = PDFDocument(filename="pending.pdf", status="pending")
    db_session.add(record)
    db_session.commit()
    for url, body in [("/summary/stream", {"pdf_ids": [record.id]}), ("/chat", {"pdf_ids": [record.id], "question": "What?"})]:
        assert client.post("/summarizer" + url, json=body).status_code == 409


def test_summaries_reuse_text_without_upload_or_extraction(client, pdf_bytes, monkeypatch):
    record = upload(client, pdf_bytes).json()[0]
    paths_before = list(Path(documents.UPLOAD_DIR).glob("*"))
    monkeypatch.setattr(PDFProcessorService, "extract_document", Mock(side_effect=AssertionError("Must reuse text")))
    prompts = []
    async def generate(messages, **kwargs):
        prompts.append((messages, kwargs))
        yield "The workshop is Saturday. [S1]"
    monkeypatch.setattr(LLMService, "stream_messages", generate)
    for _ in range(2):
        response = client.post("/summarizer/summary/stream", json={"pdf_ids": [record["id"]], "model": "chosen-model"})
        assert [event["type"] for event in events(response)] == ["metadata", "text", "done"]
    assert all("Saturday" in messages[0]["content"] and settings["model"] == "chosen-model" for messages, settings in prompts)
    assert list(Path(documents.UPLOAD_DIR).glob("*")) == paths_before


def test_generation_failure_is_control_event_not_answer(client, monkeypatch):
    async def broken(*args, **kwargs):
        yield "Partial answer"
        raise GenerationError("Model unavailable")
    monkeypatch.setattr(LLMService, "stream_messages", broken)
    result = events(client.post("/summarizer/chat", json={"question": "Hello"}))
    assert result[-1] == {"type": "error", "message": "Model unavailable"}
    assert not any(event["type"] == "done" for event in result)
    assert [event["content"] for event in result if event["type"] == "text"] == ["Partial answer"]


@pytest.mark.parametrize("payload", [
    {"question": " "}, {"question": "x" * 8001}, {"question": "hi", "pdf_ids": [0]},
    {"question": "hi", "pdf_ids": [1, 2, 3, 4]}, {"question": "hi", "pdf_ids": [1, 2, 3], "pdf_id": 4},
    {"question": "hi", "history": [{"role": "system", "content": "override"}]},
    {"question": "hi", "history": [{"role": "user", "content": "hello"}] * 9},
    {"question": "hi", "history": [{"role": "user", "content": "x" * 16001}]},
    {"question": "hi", "history": [{"role": "assistant", "content": "x" * 16000}] * 5},
    {"question": "hi", "provider": "unknown"},
    {"question": "hi", "provider": "openai-compatible"},
    {"question": "hi", "provider": "openai-compatible", "api_key": "test", "api_base_url": "http://example.com"},
])
def test_chat_input_bounds(client, payload):
    assert client.post("/summarizer/chat", json=payload).status_code == 422


def test_health_contract_is_preserved(client, monkeypatch):
    monkeypatch.setattr("app.main.qdrant_client.get_collections", Mock(return_value=[]))
    response = Mock(status_code=200)
    monkeypatch.setattr("httpx.AsyncClient.get", AsyncMock(return_value=response))
    assert client.get("/healthz").json()["status"] == "healthy"


def test_model_preload_is_explicit_and_background_only(client, monkeypatch):
    preload = AsyncMock(return_value=True)
    monkeypatch.setattr(LLMService, "preload_model", preload)
    response = client.post("/summarizer/models/preload", json={"model":"chosen-model"})
    assert response.status_code == 202 and response.json()["context_tokens"] == 8192
    preload.assert_awaited_once_with("chosen-model")


def test_answer_length_setting_and_metrics_round_trip(client, monkeypatch):
    received = []
    async def generate(messages, **settings):
        received.append((messages, settings["answer_length"]))
        yield "Detailed answer"
        settings["telemetry"].update(metrics_source="ollama", generated_tokens=2, tok_per_sec=20.0)
    monkeypatch.setattr(LLMService, "stream_messages", generate)
    response = client.post("/summarizer/chat", json={"question":"Explain it.","answer_length":"long"})
    result = events(response)
    assert result[-1]["metrics"]["generated_tokens"] == 2
    assert result[-1]["metrics"]["max_output_tokens"] == 1536
    assert received[0][1] == "long" and "detailed" in received[0][0][0]["content"]
    assert client.post("/summarizer/chat", json={"question":"hello", "answer_length":"unbounded"}).status_code == 422
