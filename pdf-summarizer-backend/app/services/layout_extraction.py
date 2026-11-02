"""Opt-in Docling conversion, normalized to the existing page-aware contract."""
from pathlib import Path
from .pdf_processor import PDFProcessorService, ExtractedPage, ExtractionResult
from .errors import PDFProcessingError


def extract_with_docling(path):
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ImportError as exc:
        raise PDFProcessingError('The optional layout parser is not installed. Install requirements-docling.txt or use standard extraction.') from exc
    options = PdfPipelineOptions(do_table_structure=True, do_formula_enrichment=True)
    result = DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options)}).convert(Path(path))
    count = PDFProcessorService.page_count(path)
    pages = [ExtractedPage(number, result.document.export_to_markdown(page_no=number), str(number)) for number in range(1,count+1)]
    chunks,numbers=[],[]
    for page in pages:
        values=PDFProcessorService.structured_chunks(page.text);chunks.extend(values);numbers.extend([page.number]*len(values))
    text='\n\n'.join(page.text for page in pages)
    if not text.strip(): raise PDFProcessingError('The layout parser returned no readable text.')
    return ExtractionResult(text,chunks,['Layout/formula interpretation is machine-generated; verify mathematical symbols against the original page.'],pages,numbers)
