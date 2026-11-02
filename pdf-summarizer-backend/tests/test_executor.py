import asyncio
import time

import pytest

from app.services.errors import PDFProcessingError, ProcessingBusyError
from app.services.pdf_executor import PDFExecutor
from app.services.pdf_processor import PDFProcessorService


@pytest.mark.anyio
async def test_process_work_does_not_block_loop_and_bounds_submissions():
    executor = PDFExecutor(max_workers=1, max_pending=1)
    executor.startup()
    try:
        task = asyncio.create_task(executor.run(time.sleep, 0.3))
        await asyncio.sleep(0.02)
        with pytest.raises(ProcessingBusyError):
            await executor.run(pow, 2, 3)
        for _ in range(3):
            await asyncio.sleep(0.02)
            assert not task.done()
        await task
        assert await executor.run(pow, 2, 3) == 8
    finally:
        await executor.shutdown()


@pytest.mark.anyio
async def test_cancelled_caller_does_not_release_running_process_slot():
    executor = PDFExecutor(max_workers=1, max_pending=1)
    executor.startup()
    try:
        task = asyncio.create_task(executor.run(time.sleep, 0.3))
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessingBusyError):
            await executor.run(pow, 2, 3)
    finally:
        await executor.shutdown()


@pytest.mark.anyio
async def test_real_pdf_extraction_and_error_cross_process_boundary(tmp_path, pdf_bytes):
    executor = PDFExecutor(max_workers=1, max_pending=2)
    executor.startup()
    path = tmp_path / "test.pdf"
    path.write_bytes(pdf_bytes)
    try:
        await executor.run(PDFProcessorService.validate_pdf, str(path))
        result = await executor.run(PDFProcessorService.extract_document, str(path))
        assert "Saturday" in result.text and result.chunks and not result.warnings
        path.write_bytes(b"not a pdf")
        with pytest.raises(PDFProcessingError):
            await executor.run(PDFProcessorService.validate_pdf, str(path))
    finally:
        await executor.shutdown()
