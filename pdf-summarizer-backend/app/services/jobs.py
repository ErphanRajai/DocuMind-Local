"""Bounded single-process tasks with durable replay and explicit restart failures."""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException


@dataclass
class Job:
    id: str
    kind: str
    events: list = field(default_factory=list)
    state: str = "preparing"
    updated: float = field(default_factory=time.monotonic)
    signal: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    def emit(self, value):
        self.events.append(value)
        self.updated = time.monotonic()
        self.signal.set()


class JobManager:
    def __init__(self, max_active=4, max_retained=32, ttl=1800, persist=False):
        self.jobs = {}
        self.max_active, self.max_retained, self.ttl = max_active, max_retained, ttl
        self.persist = persist

    async def recover(self):
        if self.persist:
            from . import job_journal
            for record in await asyncio.to_thread(job_journal.recover):
                self.jobs[record['id']] = Job(**record)

    async def checkpoint(self, job):
        if self.persist:
            from . import job_journal
            try:
                await asyncio.to_thread(job_journal.save, job)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Job journal checkpoint failed')

    def prune(self):
        for key, job in list(self.jobs.items()):
            if job.state in {"completed", "failed", "cancelled"} and time.monotonic() - job.updated > self.ttl:
                del self.jobs[key]
        terminal = sorted((j for j in self.jobs.values() if j.state in {"completed", "failed", "cancelled"}), key=lambda j: j.updated)
        while len(self.jobs) >= self.max_retained and terminal:
            del self.jobs[terminal.pop(0).id]

    def get(self, job_id):
        self.prune()
        if job_id not in self.jobs:
            raise HTTPException(404, "This generation has expired or the backend restarted. Retry your question.")
        return self.jobs[job_id]

    def start(self, kind, factory):
        self.prune()
        if sum(j.state not in {"completed", "failed", "cancelled"} for j in self.jobs.values()) >= self.max_active:
            raise HTTPException(429, "Too many answers are in progress. Stop one or try again shortly.", headers={"Retry-After": "2"})
        job = Job(uuid.uuid4().hex, kind)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self.run(job, factory))
        return job

    async def run(self, job, factory):
        response = None
        job.emit({"type": "status", "phase": "preparing", "message": "Preparing document sources"})
        await self.checkpoint(job)
        checkpoint = time.monotonic()
        try:
            response = await factory()
            job.state = "waiting"
            job.emit({"type": "status", "phase": "waiting", "message": "Model preparing answer"})
            buffer = ""
            async for part in response.body_iterator:
                buffer += part.decode() if isinstance(part, bytes) else part
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line:
                        continue
                    value = json.loads(line)
                    if value["type"] in {"text", "replace_text"}:
                        job.state = "generating"
                    elif value["type"] == "done":
                        job.state = "completed"
                    elif value["type"] == "error":
                        job.state = "failed"
                    job.emit(value)
                    if time.monotonic() - checkpoint > 1:
                        await self.checkpoint(job)
                        checkpoint = time.monotonic()
            if job.state not in {"completed", "failed"}:
                raise RuntimeError("Incomplete generation stream")
        except asyncio.CancelledError:
            job.state = "cancelled"
            job.emit({"type": "cancelled", "message": "Generation stopped. The draft is incomplete."})
        except Exception as exc:
            job.state = "failed"
            message = exc.detail if isinstance(exc, HTTPException) else "Generation failed. Retry your request."
            job.emit({"type": "error", "message": message})
        finally:
            if response is not None and hasattr(response.body_iterator, "aclose"):
                await response.body_iterator.aclose()
            await self.checkpoint(job)

    async def cancel(self, job_id):
        job = self.get(job_id)
        if job.task and not job.task.done() and job.state not in {"completed", "failed", "cancelled"}:
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)
            # Cancellation before the coroutine's first instruction needs an
            # explicit terminal event too.
            if job.state != "cancelled":
                job.state = "cancelled"
                job.emit({"type": "cancelled", "message": "Generation stopped."})
            await self.checkpoint(job)
        return job

    async def events(self, job, after=0):
        index = after
        while True:
            while index < len(job.events):
                yield json.dumps({**job.events[index], "sequence": index + 1}, ensure_ascii=False) + "\n"
                index += 1
            if job.state in {"completed", "failed", "cancelled"}:
                return
            job.signal.clear()
            try:
                await asyncio.wait_for(job.signal.wait(), timeout=10)
            except TimeoutError:
                yield json.dumps({"type": "heartbeat", "phase": job.state}) + "\n"

    async def shutdown(self):
        tasks = [j.task for j in self.jobs.values() if j.task and not j.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


jobs = JobManager(persist=True)
