from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..schemas import JobRequest
from ..services.jobs import jobs
from .summarizer import chat_with_pdf_or_general, summarize_documents

router = APIRouter(prefix="/summarizer/jobs", tags=["Generation jobs"])


@router.post("", status_code=202)
async def create_job(request: JobRequest):
    handler = chat_with_pdf_or_general if request.kind == "chat" else summarize_documents
    job = jobs.start(request.kind, lambda: handler(request.payload))
    return {"id": job.id, "state": job.state}


@router.get("/{job_id}")
async def job_status(job_id: str):
    job = jobs.get(job_id)
    return {"id": job.id, "state": job.state, "events": len(job.events)}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = await jobs.cancel(job_id)
    return {"id": job.id, "state": job.state}


@router.get("/{job_id}/events")
async def job_events(job_id: str, after: int = Query(0, ge=0)):
    job = jobs.get(job_id)
    return StreamingResponse(jobs.events(job, after), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
