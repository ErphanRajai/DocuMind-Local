import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import fitz
import pytesseract
from PIL import Image

from .errors import PDFProcessingError, PDFPageNotFound

logger = logging.getLogger(__name__)
from .languages import normalize_document_text


@dataclass
class ExtractedPage:
    number: int
    text: str
    label: str = ""


@dataclass
class ExtractionResult:
    text: str
    chunks: List[str]
    warnings: List[str]
    pages: List[ExtractedPage] = field(default_factory=list)
    chunk_pages: List[int] = field(default_factory=list)


class PDFProcessorService:
    @staticmethod
    def ocr_language():
        available = set(pytesseract.get_languages(config=''))
        selected = [language for language in ('eng', 'fas', 'ara') if language in available]
        return '+'.join(selected) or 'eng'

    @staticmethod
    def transcribe_image(content):
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 16_000_000: raise ValueError('Use an image smaller than 16 megapixels.')
            text = pytesseract.image_to_string(image, lang=PDFProcessorService.ocr_language(), timeout=30).strip()
        return {'text': normalize_document_text(text), 'engine': 'Tesseract', 'verified': False,
                'notice': 'Review symbols, superscripts, fractions and diagram labels before solving. OCR is a transcription, not mathematical verification.'}

    @staticmethod
    def validate_pdf(file_path: str) -> None:
        """Inspect structure without extracting text or running OCR."""
        try:
            # Opening from bytes avoids PyMuPDF retaining an OS file handle
            # when its constructor rejects a corrupt PDF (notably on Windows).
            with fitz.open(stream=Path(file_path).read_bytes(), filetype="pdf") as doc:
                if not doc.is_pdf:
                    raise PDFProcessingError("The uploaded file is not a PDF.")
                if doc.needs_pass:
                    raise PDFProcessingError("Password-protected PDFs are not supported. Upload an unlocked copy.")
                if doc.page_count == 0:
                    raise PDFProcessingError("The PDF has no pages.")
                doc.load_page(0)
        except PDFProcessingError:
            raise
        except Exception as exc:
            raise PDFProcessingError("The PDF is corrupt or cannot be opened.") from exc

    @staticmethod
    def extract_document(file_path: str) -> ExtractionResult:
        """Extract once in a child process; preserve warnings for incomplete pages."""
        pages, warnings = [], []
        try:
            with fitz.open(stream=Path(file_path).read_bytes(), filetype="pdf") as doc:
                if not doc.is_pdf or doc.needs_pass or doc.page_count == 0:
                    raise PDFProcessingError("The PDF cannot be read. Upload a valid, unlocked PDF.")
                for index, page in enumerate(doc):
                    page_text, label = "", ""
                    try:
                        label = page.get_label() or str(index + 1)
                        page_text = page.get_text("text").strip()
                        has_images = bool(page.get_images(full=True))
                        if len(page_text) < 80 and has_images:
                            try:
                                pixmap = page.get_pixmap(dpi=200, alpha=False)
                                with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                                    ocr_text = pytesseract.image_to_string(image, lang=PDFProcessorService.ocr_language(), timeout=60).strip()
                                if len(ocr_text) > len(page_text):
                                    page_text = ocr_text
                            except Exception:
                                warnings.append(f"OCR failed on page {index + 1}; some text may be missing.")
                        if not page_text:
                            blocks = page.get_text("blocks")
                            page_text = "\n".join(
                                b[4] for b in blocks if len(b) > 4 and isinstance(b[4], str)
                            ).strip()
                        if not page_text and has_images:
                            warnings.append(f"No readable text was found on image page {index + 1}.")
                    except Exception:
                        warnings.append(f"Page {index + 1} could not be read.")
                    pages.append(ExtractedPage(index + 1, normalize_document_text(page_text), label))
        except PDFProcessingError:
            raise
        except Exception as exc:
            raise PDFProcessingError("The PDF could not be extracted.") from exc

        text = "\n\n".join(page.text for page in pages if page.text).strip()
        if not text:
            raise PDFProcessingError("No readable text could be extracted. Try a clearer scan or a PDF with selectable text.")

        # Page boundaries survive chunking, including blank / unreadable pages.
        chunks, chunk_pages = [], []
        for page in pages:
            page_chunks = PDFProcessorService.structured_chunks(page.text)
            chunks.extend(page_chunks)
            chunk_pages.extend([page.number] * len(page_chunks))
        return ExtractionResult(text, chunks, warnings, pages, chunk_pages)

    @staticmethod
    def structured_chunks(text):
        """Keep paragraphs and question/heading boundaries when possible."""
        import re
        units = re.split(r'\n\s*\n|\n(?=(?:\d+[.)]|Question\s+\d|Theorem\b|Definition\b|Example\b))', text)
        chunks, current = [], ''
        for unit in units:
            if not unit.strip(): continue
            if len(unit) > 2000:
                if current: chunks.append(current); current = ''
                chunks.extend(PDFProcessorService.chunk_text(unit, 2000, 200))
            elif len(current) + len(unit) + 2 > 2000:
                chunks.append(current)
                current = unit
            else:
                current += ('\n\n' if current else '') + unit
        if current: chunks.append(current)
        return chunks

    @staticmethod
    def page_geometry(file_path, number, search=''):
        with fitz.open(file_path) as document:
            if not 1 <= number <= len(document): raise PDFPageNotFound('That PDF page does not exist.')
            page = document[number - 1]
            width, height = page.rect.width, page.rect.height
            words = [{'text': normalize_document_text(w[4]), 'x': w[0]/width, 'y': w[1]/height, 'w': (w[2]-w[0])/width, 'h': (w[3]-w[1])/height} for w in page.get_text('words')[:12000]]
            marks = [{'x': r.x0/width, 'y': r.y0/height, 'w': r.width/width, 'h': r.height/height} for r in page.search_for(search[:150])[:40]] if search else []
            if search and not marks:
                needle = normalize_document_text(search).casefold()
                marks = [{key:word[key] for key in ('x','y','w','h')} for word in words if needle in word['text'].casefold()][:40]
            return {'page': number, 'width': width, 'height': height, 'text': normalize_document_text(page.get_text('text')), 'words': words, 'highlights': marks}

    @staticmethod
    def page_count(file_path: str) -> int:
        try:
            with fitz.open(stream=Path(file_path).read_bytes(), filetype="pdf") as document:
                if document.needs_pass:
                    raise PDFProcessingError("The PDF is password-protected.")
                return len(document)
        except PDFProcessingError:
            raise
        except Exception as exc:
            raise PDFProcessingError("The PDF could not be opened.") from exc

    @staticmethod
    def render_page(file_path: str, number: int) -> bytes:
        try:
            with fitz.open(stream=Path(file_path).read_bytes(), filetype="pdf") as document:
                if number < 1 or number > len(document):
                    raise PDFPageNotFound("That PDF page does not exist.")
                page = document.load_page(number - 1)
                scale = min(1.7, 1800 / max(page.rect.width, page.rect.height))
                return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB).tobytes("png")
        except PDFProcessingError:
            raise
        except Exception as exc:
            raise PDFProcessingError("The PDF page could not be displayed.") from exc

    @staticmethod
    def extract_text(file_path: str) -> str:
        """Compatibility helper for scripts; the worker uses extract_document."""
        return PDFProcessorService.extract_document(file_path).text

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 4000, chunk_overlap: int = 300) -> List[str]:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Require chunk_size > 0 and 0 <= chunk_overlap < chunk_size")
        if not text or not text.strip():
            return []
        text = text.strip()
        chunks = []
        for start in range(0, len(text), chunk_size - chunk_overlap):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
        return chunks
