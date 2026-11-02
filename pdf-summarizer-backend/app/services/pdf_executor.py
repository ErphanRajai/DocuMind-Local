"""Bound PDF work by both process count and outstanding submissions."""

import asyncio
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

from .errors import ProcessingBusyError


class PDFExecutor:
    def __init__(self, max_workers=2, max_pending=8):
        if max_workers < 1 or max_pending < max_workers:
            raise ValueError("PDF limits require 1 <= workers <= pending operations")
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._pool = None
        self._pending = 0

    def startup(self):
        self._slots = asyncio.Semaphore(self.max_workers)
        self._pending = 0
        self._pool = ProcessPoolExecutor(
            max_workers=self.max_workers,
            mp_context=multiprocessing.get_context("spawn"),
        )

    async def run(self, function, *args):
        if self._pool is None:
            raise RuntimeError("PDF executor has not started")
        if self._pending >= self.max_pending:
            raise ProcessingBusyError("PDF processing is busy. Please try again shortly.")
        self._pending += 1
        try:
            await self._slots.acquire()
        except BaseException:
            self._pending -= 1
            raise
        try:
            future = asyncio.wrap_future(self._pool.submit(function, *args))
        except BaseException:
            self._slots.release()
            self._pending -= 1
            raise

        def finished(_future):
            self._slots.release()
            self._pending -= 1

        # A cancelled HTTP request cannot stop a running process: reserve its
        # capacity until the actual work finishes, even if the caller leaves.
        future.add_done_callback(finished)
        return await asyncio.shield(future)

    async def shutdown(self):
        if self._pool is not None:
            await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)
            self._pool = None


pdf_executor = PDFExecutor(
    max_workers=int(os.getenv("PDF_PROCESS_WORKERS", "2")),
    max_pending=int(os.getenv("PDF_MAX_PENDING", "8")),
)
