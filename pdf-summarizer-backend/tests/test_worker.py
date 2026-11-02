from unittest.mock import AsyncMock

import pytest

from app.models import PDFDocument
from app.routers.summarizer import process_pdf_worker
from app.services.errors import PDFProcessingError
from app.services.pdf_executor import pdf_executor
from app.services.pdf_processor import ExtractionResult, ExtractedPage


@pytest.mark.anyio
@pytest.mark.parametrize("warnings,expected_status", [([], "completed"), (["Page 2 could not be read."], "partial")])
async def test_worker_indexes_without_summarizing(db_session, monkeypatch, warnings, expected_status):
    record = PDFDocument(filename="test.pdf", status="pending")
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(pdf_executor, "run", AsyncMock(return_value=ExtractionResult("Garden notes", ["Garden notes"], warnings, [ExtractedPage(1, "Garden notes")], [1])))
    index = AsyncMock()
    summary = AsyncMock(side_effect=AssertionError("Ingestion must not generate answers"))
    monkeypatch.setattr("app.routers.summarizer.store_chunks_in_qdrant", index)
    monkeypatch.setattr("app.routers.summarizer.LLMService.summarize_chunks", summary)
    await process_pdf_worker(record.id, "test.pdf", "test.pdf")
    db_session.refresh(record)
    assert record.status == expected_status
    assert record.raw_text == "Garden notes"
    assert record.summary is None and record.error_message is None
    assert record.warning_message == ("\n".join(warnings) or None)
    index.assert_awaited_once()
    summary.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("failure_stage", ["extraction", "indexing"])
async def test_worker_errors_are_separate_from_summary(db_session, monkeypatch, failure_stage):
    record = PDFDocument(filename="test.pdf", status="pending")
    db_session.add(record)
    db_session.commit()
    extract = AsyncMock(return_value=ExtractionResult("Some text", ["Some text"], [], [ExtractedPage(1, "Some text")], [1]))
    index = AsyncMock()
    if failure_stage == "extraction":
        extract.side_effect = PDFProcessingError("Unreadable PDF")
    else:
        index.side_effect = RuntimeError("Index unavailable")
    monkeypatch.setattr(pdf_executor, "run", extract)
    monkeypatch.setattr("app.routers.summarizer.store_chunks_in_qdrant", index)
    await process_pdf_worker(record.id, "test.pdf", "test.pdf")
    db_session.refresh(record)
    assert record.status == "failed"
    assert record.error_message
    assert record.summary is None
