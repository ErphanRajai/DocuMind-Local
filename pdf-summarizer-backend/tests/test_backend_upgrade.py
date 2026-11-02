import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.services.retrieval_context import retrieval_query
from app.services.citations import check_quotes
from app.services.complete_review import segment_text, review_key
from app.services.jobs import JobManager
from app.services.llm_service import LLMService


@pytest.mark.parametrize("question,expected",[("Who approved it?",True),("What about their budget?",True),("Explain the second option",True),("What is the budget?",False)])
def test_followup_search_uses_user_context_only(question,expected):
    query, contextual = retrieval_query(question,[{"role":"user","content":"Compare garden funding proposals"},{"role":"assistant","content":"Invented secret fact"}])
    assert contextual is expected and "Invented secret fact" not in query
    assert ("funding proposals" in query) is expected


def test_no_history_and_assistant_only_do_not_rewrite():
    assert retrieval_query("Why?",[]) == ("Why?",False)
    assert retrieval_query("Why?",[{"role":"assistant","content":"unsupported"}]) == ("Why?",False)


@pytest.mark.parametrize("text",["word "*2000,"中文文档"*1000,"café 🌱 "*1000,"short"])
def test_every_character_is_covered_with_bounded_unicode_segments(text):
    segments=list(segment_text(text))
    assert all(len(s.encode())<=1800 for s in segments)
    # Overlaps allow every original position to occur in at least one segment.
    covered=set();start=0
    for segment in segments:
        position=text.find(segment,start)
        assert position>=0
        covered.update(range(position,position+len(segment)))
        start=position+max(1,len(segment)-min(120,len(segment)//4))
    assert len(covered)==len(text.strip())


@pytest.mark.parametrize("quote,verified",[("The supplies budget is 240 dollars.",True),("The supplies budget is 999 dollars.",False)])
def test_quote_checks_match_actual_cited_excerpt(quote,verified):
    checks=check_quotes(f'It says "{quote}" [S1]',[{"id":"S1","excerpt":"The supplies budget is 240 dollars."}])
    assert checks[0]["verified"] is verified


def test_quote_from_wrong_source_or_without_citation_is_flagged():
    sources=[{"id":"S1","excerpt":"A workshop on Saturday."},{"id":"S2","excerpt":"The supplies budget is 240 dollars."}]
    assert not check_quotes('"The supplies budget is 240 dollars." [S1]',sources)[0]["verified"]
    assert not check_quotes('"The supplies budget is 240 dollars."',sources)[0]["verified"]
    assert check_quotes('`"The supplies budget is 240 dollars."` [S1]',sources)==[]


def test_review_cache_invalidates_on_evidence_model_and_directive():
    key=review_key({"text":"one"},{"model":"a"},"summary")
    assert key!=review_key({"text":"two"},{"model":"a"},"summary")
    assert key!=review_key({"text":"one"},{"model":"b"},"summary")
    assert key!=review_key({"text":"one"},{"model":"a"},"decisions")


@pytest.mark.anyio
async def test_jobs_complete_replay_and_failures():
    manager=JobManager()
    async def factory():
        async def body():
            yield json.dumps({"type":"text","content":"answer"})+"\n"
            yield '{"type":"done","metrics":{}}\n'
        return StreamingResponse(body())
    job=manager.start("chat",factory)
    await job.task
    assert job.state=="completed"
    replay=[json.loads(line) async for line in manager.events(job,after=2)]
    assert [event["type"] for event in replay]==["text","done"]
    async def failure(): raise HTTPException(409,"PDF still processing")
    failed=manager.start("chat",failure);await failed.task
    assert failed.state=="failed" and failed.events[-1]["message"]=="PDF still processing"


@pytest.mark.anyio
async def test_cancel_releases_running_generator_and_capacity():
    manager=JobManager(max_active=1)
    entered,closed=asyncio.Event(),asyncio.Event()
    async def factory():
        async def body():
            try:
                entered.set();await asyncio.Event().wait();yield ""
            finally:closed.set()
        return StreamingResponse(body())
    job=manager.start("chat",factory);await entered.wait()
    with pytest.raises(HTTPException) as limit:manager.start("chat",factory)
    assert limit.value.status_code==429
    await manager.cancel(job.id)
    assert job.state=="cancelled" and closed.is_set()
    assert job.events[-1]["type"]=="cancelled"
    next_job=manager.start("chat",factory);await manager.cancel(next_job.id)
    assert next_job.state=="cancelled"


def test_expired_job_has_clear_retry_error():
    manager=JobManager(ttl=0)
    with pytest.raises(HTTPException) as missing:manager.get("missing")
    assert missing.value.status_code==404


def test_complete_review_covers_every_page_and_reuses_cached_segments(client,pdf_bytes,monkeypatch):
    pdf_id=client.post("/summarizer/upload",files=[("files",("garden.pdf",pdf_bytes))]).json()[0]["id"]
    calls=[]
    async def generate(messages,**kwargs):
        calls.append(messages)
        yield "The workshop is Saturday. [S1]"
    monkeypatch.setattr(LLMService,"stream_messages",generate)
    body={"pdf_ids":[pdf_id],"mode":"complete"}
    first=[json.loads(line) for line in client.post("/summarizer/summary/stream",json=body).text.splitlines()]
    second=[json.loads(line) for line in client.post("/summarizer/summary/stream",json=body).text.splitlines()]
    assert first[-1]["metrics"]["pages_reviewed"]==1
    assert second[-1]["metrics"]["cache_hits"]==1 and len(calls)==1


def test_job_api_validates_kind_payload_and_does_not_leak_secrets(client,monkeypatch):
    async def generate(*args,**kwargs):yield "Hello"
    monkeypatch.setattr(LLMService,"stream_messages",generate)
    response=client.post("/summarizer/jobs",json={"kind":"chat","payload":{"question":"Hello"}})
    assert response.status_code==202
    job_id=response.json()["id"]
    result=client.get(f"/summarizer/jobs/{job_id}/events").text
    assert '"done"' in result
    assert client.get(f"/summarizer/jobs/{job_id}").json()["state"]=="completed"
    assert client.post("/summarizer/jobs",json={"kind":"chat","payload":{"pdf_ids":[1]}}).status_code==422
    assert client.post("/summarizer/jobs",json={"kind":"unknown","payload":{"question":"hi"}}).status_code==422


def test_unverified_quote_fails_stream(client,monkeypatch,pdf_bytes):
    pdf_id=client.post("/summarizer/upload",files=[("files",("garden.pdf",pdf_bytes))]).json()[0]["id"]
    async def generate(*args,**kwargs):yield 'It says "The workshop is cancelled forever." [S1]'
    monkeypatch.setattr(LLMService,"stream_messages",generate)
    result=[json.loads(line) for line in client.post("/summarizer/summary/stream",json={"pdf_ids":[pdf_id]}).text.splitlines()]
    assert result[-1]["type"]=="error" and "quotation" in result[-1]["message"]


def test_complete_review_maps_each_local_source_to_its_actual_page(client,monkeypatch):
    import fitz
    with fitz.open() as doc:
        for text in ["The workshop is Saturday.","The supplies budget is 240 dollars."]:
            doc.new_page().insert_text((72,72),text)
        content=doc.tobytes()
    pdf_id=client.post("/summarizer/upload",files=[("files",("pages.pdf",content))]).json()[0]["id"]
    async def generate(messages,**kwargs):
        assert "[S1] pages.pdf" in messages[0]["content"]
        yield "A finding from this page. [S1]"
    monkeypatch.setattr(LLMService,"stream_messages",generate)
    result=[json.loads(line) for line in client.post("/summarizer/summary/stream",json={"pdf_ids":[pdf_id],"mode":"complete"}).text.splitlines()]
    text="".join(event.get("content","") for event in result)
    assert "[S1]" in text and "[S2]" in text
    assert result[-1]["metrics"]["pages_reviewed"]==2
