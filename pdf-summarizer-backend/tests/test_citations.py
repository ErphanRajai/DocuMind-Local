import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import fitz
import pytest

from app.models import PDFDocument, PDFPage
from app.services import citations, documents, vector_db
from app.services.context_budget import TokenCounter, build_prompt
from app.services.llm_service import LLMService
from app.services.pdf_processor import PDFProcessorService

path = Path(__file__).resolve().parents[2] / "pdf-summarizer-frontend" / "citations.py"
spec = importlib.util.spec_from_file_location("frontend_citations", path)
frontend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend)


@pytest.fixture
def multipage_pdf():
    with fitz.open() as doc:
        for text in ["Garden project overview.", "Workshop starts Saturday at ten. Budget: 240 dollars.", "", "References: Garden handbook, section 9."]:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        return doc.tobytes()


def upload(client, content):
    response = client.post("/summarizer/upload", files=[("files", ("garden.pdf", content, "application/pdf"))])
    assert response.status_code == 201
    return response.json()[0]["id"]


def events(response):
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines()]


def test_page_extraction_keeps_blank_pages_and_references(tmp_path, multipage_pdf):
    path = tmp_path / "pages.pdf"
    path.write_bytes(multipage_pdf)
    result = PDFProcessorService.extract_document(str(path))
    assert [page.number for page in result.pages] == [1, 2, 3, 4]
    assert result.pages[2].text == ""
    assert result.chunk_pages == [1, 2, 4]
    assert "References" in result.text
    assert all(chunk in result.pages[number - 1].text for chunk, number in zip(result.chunks, result.chunk_pages))


def test_page_viewer_and_original_pdf(client, multipage_pdf, db_session):
    pdf_id = upload(client, multipage_pdf)
    status = client.get(f"/summarizer/documents/{pdf_id}").json()
    assert status["page_count"] == 4 and status["source_version"] == 1
    assert db_session.query(PDFPage).filter_by(pdf_id=pdf_id).count() == 4
    url = f"/summarizer/documents/{pdf_id}"
    view = client.get(url + "/view?page=2")
    assert "PDF page 2 of 4" in view.text and 'src="pages/2.png"' in view.text
    assert 'href="?page=1"' in view.text and 'href="?page=3"' in view.text
    assert "default-src 'none'" in view.headers["content-security-policy"]
    image = client.get(url + "/pages/2.png")
    assert image.headers["content-type"] == "image/png" and image.content.startswith(b"\x89PNG")
    pixmap = fitz.Pixmap(image.content)
    assert max(pixmap.width, pixmap.height) <= 1800
    pdf = client.get(url + "/file")
    assert pdf.content == multipage_pdf and pdf.headers["content-disposition"].startswith("inline")
    assert "private" in pdf.headers["cache-control"]
    assert client.get(url + "/view?page=0").status_code == 422
    for suffix in ["/view?page=5", "/pages/0.png", "/pages/5.png"]:
        assert client.get(url + suffix).status_code == 404
    assert client.get("/summarizer/documents/999999/file").status_code == 404


def test_viewer_never_serves_file_outside_uploads(client, db_session, tmp_path, multipage_pdf):
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(multipage_pdf)
    record = PDFDocument(filename="outside.pdf", file_path=str(outside), status="completed")
    db_session.add(record)
    db_session.commit()
    for suffix in ["/file", "/view", "/pages/1.png"]:
        assert client.get(f"/summarizer/documents/{record.id}" + suffix).status_code == 404


def test_viewer_escapes_filename(client, db_session, multipage_pdf):
    pdf_id = upload(client, multipage_pdf)
    documents.update_document(pdf_id, filename='<script>alert("bad")</script>.pdf')
    html = client.get(f"/summarizer/documents/{pdf_id}/view").text
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_chat_citations_reuse_text_and_persist_page_metadata(client, multipage_pdf, monkeypatch):
    pdf_id = upload(client, multipage_pdf)
    monkeypatch.setattr(PDFProcessorService, "extract_document", Mock(side_effect=AssertionError("Already extracted")))
    monkeypatch.setattr("app.routers.summarizer.search_page_sources", AsyncMock(return_value=([
        {"pdf_id": pdf_id, "page": 2, "text": "Workshop starts Saturday at ten. Budget: 240 dollars."}], 12.5)))
    async def generate(messages, **kwargs):
        assert "[S1] garden.pdf" in messages[0]["content"]
        assert "untrusted data" in messages[0]["content"]
        yield "The workshop starts Saturday at ten. [S"
        yield "1]"
    monkeypatch.setattr(LLMService, "stream_messages", generate)
    result = events(client.post("/summarizer/chat", json={"pdf_ids": [pdf_id], "question": "When is the workshop?"}))
    source = result[0]["sources"][0]
    assert source["pdf_id"] == pdf_id and source["page"] == 2 and source["id"] == "S1"
    assert source["excerpt"].startswith("Workshop")
    assert result[-1]["type"] == "done" and result[-1]["metrics"]["sources"] == [source]
    answer = "".join(event.get("content", "") for event in result)
    assert f"/documents/{pdf_id}/view?page=2" in frontend.cited_markdown(answer, [source], "http://backend")


@pytest.mark.parametrize("answer,last_type", [("Invented citation [S99]", "error"), ("No inline references.", "done")])
def test_unknown_citation_rejected_and_missing_citations_disclosed(client, multipage_pdf, monkeypatch, answer, last_type):
    pdf_id = upload(client, multipage_pdf)
    async def generate(*args, **kwargs):
        yield answer
    monkeypatch.setattr(LLMService, "stream_messages", generate)
    result = events(client.post("/summarizer/summary/stream", json={"pdf_ids": [pdf_id]}))
    assert result[-1]["type"] == last_type
    if last_type == "error":
        assert not any(event["type"] == "done" for event in result)
    else:
        assert "no inline citations" in result[-1]["metrics"]["citation_warning"]


def test_sources_budget_returns_only_excerpts_model_saw():
    sources = [{"id": f"S{n}", "pdf_id": n, "page": 2, "filename": "test.pdf", "title": f"[S{n}] test.pdf page 2", "text": "long source " * 4000} for n in range(1, 4)]
    plan = build_prompt(TokenCounter(), citations.GROUNDED_SYSTEM, "Compare them", sources=sources)
    assert len(plan.metadata["sources"]) == 3
    for source in plan.metadata["sources"]:
        assert source["excerpt"] in plan.messages[0]["content"]
        assert len(source["excerpt"]) < len(sources[0]["text"])
    assert plan.metadata["budgeted_input_tokens"] <= 8192 - 512 - 512


def test_summary_notice_counts_sources_after_budgeting(client, multipage_pdf, monkeypatch):
    pdf_id = upload(client, multipage_pdf)
    original = LLMService.prepare_prompt
    async def limited_plan(*args, **kwargs):
        # Simulate the planner excluding page excerpts that do not fit.
        kwargs["sources"] = kwargs["sources"][:1]
        return await original(*args, **kwargs)
    async def generate(*args, **kwargs):
        yield "Garden project overview. [S1]"
    monkeypatch.setattr(LLMService, "prepare_prompt", limited_plan)
    monkeypatch.setattr(LLMService, "stream_messages", generate)
    result = events(client.post("/summarizer/summary/stream", json={"pdf_ids": [pdf_id]}))
    assert len(result[0]["sources"]) == 1
    assert "1 of 3 readable pages" in result[0]["source_notice"]


def test_bind_sources_rejects_outside_document_or_page():
    records = [{"id": 1, "page_count": 2, "filename": "real.pdf"}]
    hits = [{"pdf_id": 2, "page": 1, "text": "other"}, {"pdf_id": 1, "page": 3, "text": "invalid"},
            {"pdf_id": 1, "page": 2, "text": "real"}]
    sources = citations.bind_sources(hits, records)
    assert len(sources) == 1 and sources[0]["title"] == "[S1] real.pdf — PDF page 2"


def test_frontend_uses_verified_metadata_and_leaves_code_alone():
    sources = [{"id": "S1", "pdf_id": 7, "page": 2, "filename": "garden.pdf"}]
    answer = "Fact [S1]. Unknown [S999]. Code `[S1]`.\n```text\n[S1]\n```"
    rendered = frontend.cited_markdown(answer, sources, "http://localhost:8888")
    assert rendered.count("/view?page=2") == 1
    assert "[S999]" in rendered and "`[S1]`" in rendered and "```text\n[S1]\n```" in rendered
    assert frontend.source_map([{"id": "S2", "pdf_id": "../etc", "page": -1}]) == {}


def test_citation_check_does_not_claim_semantic_verification():
    sources = [{"id": "S1"}]
    assert citations.citation_warning("Unsupported assertion [S1]", sources) == ""
    assert citations.citation_warning("Example `[S999]`", sources).startswith("This answer")


@pytest.mark.anyio
async def test_legacy_upgrade_runs_once_for_concurrent_requests(client, db_session, multipage_pdf, monkeypatch):
    pdf_id = upload(client, multipage_pdf)
    documents.update_document(pdf_id, source_version=0)
    records = documents.read_documents([pdf_id], include_text=True)
    index = AsyncMock()
    extract = Mock(wraps=PDFProcessorService.extract_document)
    monkeypatch.setattr(citations, "store_chunks_in_qdrant", index)
    monkeypatch.setattr(PDFProcessorService, "extract_document", extract)
    await asyncio.gather(citations.ensure_page_index(records), citations.ensure_page_index(records))
    assert extract.call_count == 1 and index.await_count == 1
    assert documents.read_documents([pdf_id])[0]["source_version"] == 1


@pytest.mark.anyio
async def test_legacy_failed_index_is_retryable(client, multipage_pdf, monkeypatch):
    pdf_id = upload(client, multipage_pdf)
    documents.update_document(pdf_id, source_version=0)
    records = documents.read_documents([pdf_id])
    index = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr(citations, "store_chunks_in_qdrant", index)
    with pytest.raises(Exception) as caught:
        await citations.ensure_page_index(records)
    assert caught.value.status_code == 503
    assert documents.read_documents([pdf_id])[0]["source_version"] == 0
    index.side_effect = None
    await citations.ensure_page_index(records)
    assert documents.read_documents([pdf_id])[0]["source_version"] == 1


@pytest.mark.anyio
async def test_retrieval_keeps_page_payload_and_represents_each_pdf(monkeypatch):
    class Array(list):
        def tolist(self): return list(self)
    sparse = SimpleNamespace(indices=Array([1]), values=Array([1.0]))
    monkeypatch.setattr(LLMService, "get_embedding", AsyncMock(return_value=[0.1]))
    monkeypatch.setattr(vector_db, "sparse_model", SimpleNamespace(embed=Mock(return_value=iter([sparse]))))
    requests = []
    def query(**kwargs):
        requests.append(kwargs)
        pdf_id = kwargs["query_filter"].must[0].match.value
        return SimpleNamespace(points=[SimpleNamespace(payload={"page_number": 2, "text": f"PDF {pdf_id}"}, score=.5)])
    monkeypatch.setattr(vector_db.qdrant_client, "query_points", query)
    sources, elapsed = await vector_db.search_page_sources([1, 2], "Compare")
    assert {source["pdf_id"] for source in sources} == {1, 2} and all(source["page"] == 2 for source in sources)
    assert elapsed >= 0 and len(requests) == 2
    assert all(request["query_filter"].must[1].match.value == 1 for request in requests)


@pytest.mark.anyio
async def test_index_writes_page_locations_before_removing_legacy_chunks(monkeypatch):
    class Array(list):
        def tolist(self): return list(self)
    sparse = SimpleNamespace(indices=Array([1]), values=Array([1.0]))
    monkeypatch.setattr(LLMService, "get_embeddings", AsyncMock(return_value=[[0.1], [0.2]]))
    monkeypatch.setattr(vector_db, "sparse_model", SimpleNamespace(embed=Mock(return_value=iter([sparse, sparse]))))
    calls = []
    monkeypatch.setattr(vector_db.qdrant_client, "upsert", lambda **kwargs: calls.append(("upsert", kwargs)))
    monkeypatch.setattr(vector_db.qdrant_client, "delete", lambda **kwargs: calls.append(("delete", kwargs)))
    await vector_db.store_chunks_in_qdrant(7, ["first", "second"], "garden.pdf", page_numbers=[1, 2])
    assert [name for name, _ in calls] == ["upsert", "delete"]
    assert [point.payload["page_number"] for point in calls[0][1]["points"]] == [1, 2]
    assert all(point.payload["source_version"] == 1 for point in calls[0][1]["points"])
