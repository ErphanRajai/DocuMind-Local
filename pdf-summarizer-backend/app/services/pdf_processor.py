import logging
import os
import re
from typing import List

import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract

logger = logging.getLogger(__name__)


class PDFProcessorService:
    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Robust text extraction pipeline:
        1. Direct PyMuPDF text & block extraction.
        2. Automatic OCR fallback with pdf2image + pytesseract if text density is low.
        """
        raw_text_parts = []

        try:
            doc = fitz.open(file_path)
            for page in doc:
                text = page.get_text("text")
                if text and text.strip():
                    raw_text_parts.append(text.strip())
                else:
                    # Fallback to block-level extraction for complex layouts
                    blocks = page.get_text("blocks")
                    block_text = "\n".join([b[4] for b in blocks if len(b) > 4 and isinstance(b[4], str)])
                    if block_text.strip():
                        raw_text_parts.append(block_text.strip())
        except Exception as e:
            logger.warning(f"PyMuPDF parser warning on {file_path}: {e}")

        extracted_content = "\n\n".join(raw_text_parts).strip()

        # If extracted text is empty or sparse (< 80 characters), execute Tesseract OCR
        if len(extracted_content) < 80:
            logger.info(f"Low text density ({len(extracted_content)} chars). Running OCR fallback on {file_path}...")
            try:
                images = convert_from_path(file_path, dpi=200)
                ocr_results = []
                for img in images:
                    page_ocr = pytesseract.image_to_string(img)
                    if page_ocr.strip():
                        ocr_results.append(page_ocr.strip())
                extracted_content = "\n\n".join(ocr_results).strip()
            except Exception as ocr_err:
                logger.error(f"OCR fallback error on {file_path}: {ocr_err}")

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