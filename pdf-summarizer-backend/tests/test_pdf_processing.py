from app.services.pdf_processor import PDFProcessorService


def test_chunk_text_logic():
    sample_text = "A" * 5000
    chunk_size = 1000
    chunk_overlap = 200

    chunks = PDFProcessorService.chunk_text(
        sample_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    assert len(chunks) > 1
    assert len(chunks[0]) == chunk_size
    assert chunks[0][-chunk_overlap:] == chunks[1][:chunk_overlap]

def test_chunk_text_empty():
    assert PDFProcessorService.chunk_text("") == []