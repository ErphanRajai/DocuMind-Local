import io
from unittest.mock import Mock

import fitz
import pytest
from PIL import Image

from app.services.errors import PDFProcessingError
from app.services.pdf_processor import PDFProcessorService


def test_unreadable_pdf_is_failure_not_empty_success(tmp_path):
    path = tmp_path / "blank.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(path)
    with pytest.raises(PDFProcessingError, match="No readable text"):
        PDFProcessorService.extract_document(str(path))


def test_ocr_failure_preserves_readable_text_with_warning(tmp_path, monkeypatch):
    path = tmp_path / "mixed.pdf"
    image_bytes = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image_bytes, format="PNG")
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Readable text on the first page.")
        page = document.new_page()
        page.insert_image(page.rect, stream=image_bytes.getvalue())
        document.save(path)
    monkeypatch.setattr("app.services.pdf_processor.pytesseract.image_to_string", Mock(side_effect=RuntimeError("OCR unavailable")))
    result = PDFProcessorService.extract_document(str(path))
    assert "Readable text" in result.text
    assert any("page 2" in warning.lower() for warning in result.warnings)


def test_password_protected_pdf_is_rejected(tmp_path):
    path = tmp_path / "locked.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="test-password", owner_pw="test-owner")
    with pytest.raises(PDFProcessingError, match="Password-protected"):
        PDFProcessorService.validate_pdf(str(path))


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, -1)])
def test_invalid_chunk_settings_cannot_loop_forever(size, overlap):
    with pytest.raises(ValueError):
        PDFProcessorService.chunk_text("Example", size, overlap)
