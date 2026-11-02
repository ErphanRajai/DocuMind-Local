"""File staging and short database operations; no session crosses a thread."""

import asyncio
import logging
import os
import uuid
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

from ..database import SessionLocal
from ..models import PDFDocument, PDFPage, StudyItem
from ..schemas import PDFDocumentResponse
from .errors import PDFProcessingError, ProcessingBusyError
from .pdf_executor import pdf_executor
from .pdf_processor import PDFProcessorService

logger = logging.getLogger(__name__)
UPLOAD_DIR = os.getenv("DOCUMIND_UPLOAD_DIR", "./uploaded_pdfs")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024


def _display_filename(upload):
    name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name or len(name) > 255 or "\x00" in name or not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Every file must have a valid .pdf filename.")
    return name


def _copy_upload(source, destination):
    """Copy with a byte limit in a thread, rather than blocking the API loop."""
    source.seek(0)
    total = 0
    with open(destination, "xb") as target:
        while content := source.read(1024 * 1024):
            total += len(content)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"Each PDF must be at most {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
            target.write(content)
    if total == 0:
        raise HTTPException(400, "Empty files cannot be uploaded.")


def _remove_staged(paths):
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove a rejected staged PDF")


def _create_records(staged):
    with SessionLocal() as db:
        records = []
        seen = set()
        for name, path in staged:
            with open(path, 'rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            key = 'file-sha256-' + digest
            if key in seen: raise HTTPException(400, 'The same PDF appears twice in this upload batch.')
            seen.add(key)
            known = db.get(StudyItem, key)
            previous = db.get(PDFDocument, json.loads(known.payload)['pdf_id']) if known else None
            if previous and previous.status in {'completed', 'partial'} and Path(previous.file_path).is_file():
                records.append(previous)
            else:
                record = PDFDocument(filename=name, file_path=path, status='pending')
                db.add(record); db.flush(); records.append(record)
                db.merge(StudyItem(id=key, workspace_id='_documents', kind='document_hash', payload=json.dumps({'pdf_id':record.id,'sha256':digest})))
        responses = [PDFDocumentResponse.model_validate(record).model_dump() for record in records]
        db.commit()
        return responses


def _discard_records(paths):
    """Compensate if a request is cancelled while its DB commit is finishing."""
    with SessionLocal() as db:
        db.query(PDFDocument).filter(PDFDocument.file_path.in_(paths)).delete(synchronize_session=False)
        db.commit()


async def _finish_thread(function, *args):
    # Python cannot cancel an active filesystem write / DB commit. Wait for it
    # before cleanup so a late writer cannot recreate a rejected batch's data.
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def ingest_uploads(files):
    """Validate the whole batch before committing any rows or scheduling work."""
    staged = []
    creation_started = False
    try:
        if not 1 <= len(files) <= 3:
            raise HTTPException(400, "Upload between one and three PDFs per request.")
        names = [_display_filename(upload) for upload in files]
        await asyncio.to_thread(Path(UPLOAD_DIR).mkdir, parents=True, exist_ok=True)
        for upload, name in zip(files, names):
            # The client filename is display metadata, never part of a disk path.
            path = str(Path(UPLOAD_DIR) / f"{uuid.uuid4().hex}.pdf")
            staged.append((name, path))
            await _finish_thread(_copy_upload, upload.file, path)
            await pdf_executor.run(PDFProcessorService.validate_pdf, path)
        creation_started = True
        records = await _finish_thread(_create_records, staged)
        # Reused records never schedule extraction against the new staged path.
        actual = []
        for record, (name, path) in zip(records, staged):
            if record['status'] in {'completed', 'partial'}:
                await asyncio.to_thread(_remove_staged, [path])
                old_path, old_name = await asyncio.to_thread(document_file, record['id'])
                actual.append((old_name, old_path))
            else:
                actual.append((name, path))
        return records, actual
    except BaseException as exc:
        if creation_started:
            try:
                await asyncio.to_thread(_discard_records, [path for _, path in staged])
            except Exception:
                logger.exception("Could not roll back a rejected upload batch")
        await asyncio.to_thread(_remove_staged, [path for _, path in staged])
        if isinstance(exc, PDFProcessingError):
            raise HTTPException(400, str(exc)) from exc
        if isinstance(exc, ProcessingBusyError):
            raise HTTPException(503, str(exc), headers={"Retry-After": "2"}) from exc
        raise
    finally:
        for upload in files:
            await upload.close()


def update_document(pdf_id, **changes):
    with SessionLocal() as db:
        record = db.get(PDFDocument, pdf_id)
        if record is None:
            return False
        for key, value in changes.items():
            setattr(record, key, value)
        db.commit()
        return True


def read_documents(pdf_ids, include_text=False):
    with SessionLocal() as db:
        records = db.query(PDFDocument).filter(PDFDocument.id.in_(pdf_ids)).all()
        by_id = {}
        for record in records:
            data = PDFDocumentResponse.model_validate(record).model_dump()
            if include_text:
                data["raw_text"] = record.raw_text
            by_id[record.id] = data
        return [by_id[pdf_id] for pdf_id in pdf_ids if pdf_id in by_id]


def document_file(pdf_id):
    """Resolve only a stored file inside the configured upload directory."""
    with SessionLocal() as db:
        record = db.get(PDFDocument, pdf_id)
        if record is None:
            raise HTTPException(404, "Document not found.")
        root = Path(UPLOAD_DIR).resolve()
        path = Path(record.file_path or "").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "The original PDF is unavailable. Upload it again to open its pages.")
        return str(path), record.filename


def save_extracted_pages(pdf_id, result):
    """Replace text and its page map in one transaction; indexing commits separately."""
    if not result.pages or len(result.chunks) != len(result.chunk_pages):
        raise PDFProcessingError("Page locations could not be extracted. Please upload the PDF again.")
    with SessionLocal() as db:
        record = db.get(PDFDocument, pdf_id)
        if record is None:
            raise PDFProcessingError("Document no longer exists.")
        db.query(PDFPage).filter_by(pdf_id=pdf_id).delete()
        db.add_all([PDFPage(pdf_id=pdf_id, number=page.number, label=page.label, text=page.text) for page in result.pages])
        record.raw_text = result.text
        record.page_count = len(result.pages)
        record.warning_message = "\n".join(result.warnings) or None
        db.commit()


def read_pages(pdf_ids):
    with SessionLocal() as db:
        pages = db.query(PDFPage).filter(PDFPage.pdf_id.in_(pdf_ids)).order_by(PDFPage.pdf_id, PDFPage.number).all()
        return [{"pdf_id": page.pdf_id, "page": page.number, "label": page.label, "text": page.text} for page in pages]
