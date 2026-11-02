import asyncio
import io
import threading

import pytest
from fastapi import UploadFile

from app.models import PDFDocument
from app.services import documents


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["copy", "commit"])
async def test_cancelled_batch_waits_for_writers_then_cleans_up(db_session, monkeypatch, pdf_bytes, stage):
    entered = threading.Event()
    release = threading.Event()
    name = "_copy_upload" if stage == "copy" else "_create_records"
    original = getattr(documents, name)

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    async def inline_validation(function, *args):
        return function(*args)

    monkeypatch.setattr(documents, name, delayed)
    monkeypatch.setattr(documents.pdf_executor, "run", inline_validation)
    upload = UploadFile(file=io.BytesIO(pdf_bytes), filename="test.pdf")
    task = asyncio.create_task(documents.ingest_uploads([upload]))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert db_session.query(PDFDocument).count() == 0
        from pathlib import Path
        assert not list(Path(documents.UPLOAD_DIR).glob("*"))
    finally:
        release.set()
