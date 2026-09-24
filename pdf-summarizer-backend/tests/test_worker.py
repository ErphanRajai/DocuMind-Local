import pytest
from unittest.mock import patch, AsyncMock
from app import models
from app.routers.summarizer import process_pdf_worker


@pytest.mark.anyio
@patch("app.routers.summarizer.LLMService.summarize_chunks", new_callable=AsyncMock)
@patch("app.routers.summarizer.store_chunks_in_qdrant", new_callable=AsyncMock)
@patch("app.routers.summarizer.PDFProcessorService.extract_text")
@patch("app.routers.summarizer.PDFProcessorService.chunk_text")
async def test_process_pdf_worker_success(
    mock_chunk,
    mock_extract,
    mock_qdrant,
    mock_llm,
    db_session
):
    # 1. Create a pending record in the test database
    doc = models.PDFDocument(
        filename="research_paper.pdf",
        file_path="uploaded_pdfs/dummy.pdf",
        status="pending"
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 2. Configure mock behaviors
    mock_extract.return_value = "Extracted document body text."
    mock_chunk.return_value = ["Extracted document body text."]
    mock_llm.return_value = "### 💎 Executive Synthesis\nTest Summary Output."

    # 3. Execute the background worker directly
    await process_pdf_worker(pdf_id=doc.id, file_path="uploaded_pdfs/dummy.pdf")

    # 4. Assert the final database state
    db_session.refresh(doc)
    assert doc.status == "completed"
    assert doc.raw_text == "Extracted document body text."
    assert "Executive Synthesis" in doc.summary
    assert mock_qdrant.called
    assert mock_llm.called


@pytest.mark.anyio
@patch("app.routers.summarizer.PDFProcessorService.extract_text", side_effect=RuntimeError("Corrupt PDF stream"))
async def test_process_pdf_worker_extraction_failure(mock_extract, db_session):
    # 1. Seed a pending document
    doc = models.PDFDocument(
        filename="broken.pdf",
        file_path="uploaded_pdfs/broken.pdf",
        status="pending"
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 2. Run the worker
    await process_pdf_worker(pdf_id=doc.id, file_path="uploaded_pdfs/broken.pdf")

    # 3. Assert fallback error status
    db_session.refresh(doc)
    assert doc.status == "failed"
    assert "Corrupt PDF stream" in doc.summary