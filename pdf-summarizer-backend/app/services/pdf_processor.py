import io
import logging
import re
from typing import List

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


class PDFProcessorService:
    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Extract selectable text page by page and OCR image pages with little text.
        Rendering only sparse pages avoids holding a full scanned PDF in memory
        and handles mixed text/scanned documents.
        """
        raw_text_parts = []

        try:
            doc = fitz.open(file_path)
            for page in doc:
                page_text = page.get_text("text").strip()
                if len(page_text) < 80 and page.get_images(full=True):
                    try:
                        pixmap = page.get_pixmap(dpi=200, alpha=False)
                        with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                            ocr_text = pytesseract.image_to_string(image).strip()
                        if len(ocr_text) > len(page_text):
                            page_text = ocr_text
                    except Exception as ocr_err:
                        logger.warning("OCR failed on a page in %s: %s", file_path, ocr_err)

                if not page_text:
                    # Fallback for complex layouts not represented in text mode.
                    blocks = page.get_text("blocks")
                    page_text = "\n".join(
                        b[4] for b in blocks if len(b) > 4 and isinstance(b[4], str)
                    ).strip()
                if page_text:
                    raw_text_parts.append(page_text)
        except Exception as e:
            logger.warning(f"PyMuPDF parser warning on {file_path}: {e}")

        extracted_content = "\n\n".join(raw_text_parts).strip()

        # Clean academic/trailing bibliography if present in the latter 60% of text
        ref_patterns = [
            r"\nReferences\s*\n",
            r"\nREFERENCES\s*\n",
            r"\nBibliography\s*\n",
        ]

        split_pos = -1
        for pattern in ref_patterns:
            match = re.search(pattern, extracted_content)
            if match:
                split_pos = match.start()
                break

        if split_pos != -1 and split_pos > (len(extracted_content) * 0.4):
            return extracted_content[:split_pos].strip()

        return extracted_content.strip()

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 4000, chunk_overlap: int = 300) -> List[str]:
        """Splits extracted text into chunks optimized for semantic search and LLM context."""
        if not text or not text.strip():
            return []

        clean_text = text.strip()
        if len(clean_text) <= chunk_size:
            return [clean_text]

        chunks = []
        start = 0
        text_len = len(clean_text)

        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk = clean_text[start:end]
            chunks.append(chunk)

            if end == text_len:
                break
            start += chunk_size - chunk_overlap

        return chunks
