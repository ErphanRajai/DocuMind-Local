import asyncio
import json
import re

import pytest

from app.services.question_batches import numbered_questions, remap_citations, CitationStream
from app.services.citations import check_quotes
from app.services.errors import GenerationError
from app.services.llm_service import LLMService
from app.routers import summarizer


def rendered(events):
    result = ''
    for event in events:
        if event['type']=='text':result+=event.get('content','')
        elif event['type']=='replace_text':result=event.get('content','')
    return result


@pytest.mark.parametrize('digits',['123','۱۲۳','١٢٣'])
@pytest.mark.parametrize('separator',['. ',') ',': '])
def test_inline_multilingual_question_boundaries_preserve_text(digits,separator):
    text='پاسخ فارسی. '+ ' '.join(f'{n}{separator}موضوع {i} چیست؟' for i,n in enumerate(digits,1))
    parts=numbered_questions(text)
    assert [p['number'] for p in parts]==[1,2,3]
    assert parts[-1]['text']=='موضوع 3 چیست؟'
    assert all(p['directive']=='پاسخ فارسی.' for p in parts)


@pytest.mark.parametrize('text',['What is 1.25 times 2.5?', '1. 100\n2. 200', '2. Explain this\n4. Explain that',
                               '1. One question only', '```\n1. print a\n2. print b\n```'])
def test_non_question_numbering_does_not_create_a_batch(text):
    assert numbered_questions(text)==[]


def test_question_limit_never_silently_drops_questions():
    with pytest.raises(GenerationError,match='20 numbered'):
        numbered_questions('\n'.join(f'{i}. Explain topic {i}?' for i in range(1,22)))


def test_citation_remapping_keeps_code_and_math_and_blocks_unknown_ids():
    assert remap_citations('[S1] [S9] `[S1]` $[S1]$',{'S1':'S4'})=='[S4] [unverified source] `[S1]` $[S1]$'


def test_persian_terminology_is_not_a_direct_source_quotation():
    text='منظور از «توحید موزه‌ای» این است که ' + 'توضیح ' * 40 + '[S1]'
    assert check_quotes(text,[{'id':'S1','excerpt':'Other evidence'}])==[]
    assert not check_quotes(text,[{'id':'S1','excerpt':'Other evidence'}],strict=True)[0]['verified']
    assert not check_quotes('The text says "false label" [S1]',[{'id':'S1','excerpt':'True label'}])[0]['verified']
    term='«اتصاف به صفات الهی»'
    assert check_quotes('منظور از '+term+' این است که ... [S1]',[{'id':'S1','excerpt':'Other evidence'}],question='منظور از '+term+' چیست؟')==[]
    assert not check_quotes('متن می‌گوید '+term+' [S1]',[{'id':'S1','excerpt':'Other evidence'}],question='منظور از '+term+' چیست؟')[0]['verified']
    label='«وحدت در تمام بخش های زندگی انسان»'
    assert check_quotes(label+' به این مفهوم اشاره دارد. [S1]',[{'id':'S1','excerpt':'Other evidence'}])==[]
    assert not check_quotes('"USD 999" [S1]',[{'id':'S1','excerpt':'USD 240'}])[0]['verified']


@pytest.mark.anyio
async def test_output_cutoff_emits_error_with_actual_metrics_not_done():
    async def tokens(): yield 'Unfinished sentence'
    events=[json.loads(e) async for e in summarizer._answer_events(tokens(),{}, {'done_reason':'length','generated_tokens':512})]
    assert events[-1]['type']=='error'
    assert 'output limit' in events[-1]['message']
    assert events[-1]['metrics']['generated_tokens']==512
    assert not any(e['type']=='done' for e in events)


def install_batch_fakes(client, pdf_bytes, monkeypatch, fail_number=None):
    pdf_id=client.post('/summarizer/upload',files={'files':('fixture.pdf',pdf_bytes)}).json()[0]['id']
    calls=[]
    async def search(ids,query):
        number=int(re.search(r'topic (\d+)',query)[1]);calls.append(number)
        return [{'pdf_id':pdf_id,'page':1,'text':f'Fact for topic {number}.','score':1}],1
    async def generate(messages,**kwargs):
        number=int(re.search(r'topic (\d+)',messages[-1]['content'])[1])
        assert 'at most' in messages[0]['content']
        yield f'Fact {number}. [S'
        yield '1]'
        kwargs['telemetry'].update(done_reason='length' if number==fail_number else 'stop',generated_tokens=20,generation_ms=100)
    monkeypatch.setattr(summarizer,'search_page_sources',search)
    monkeypatch.setattr(LLMService,'stream_messages',generate)
    return pdf_id,calls


@pytest.mark.parametrize('length',['short','long'])
def test_ten_questions_search_independently_and_keep_all_citations(client,pdf_bytes,monkeypatch,length):
    pdf_id,calls=install_batch_fakes(client,pdf_bytes,monkeypatch)
    question=' '.join(f'{i}. Explain topic {i}?' for i in range(1,11))
    response=client.post('/summarizer/chat',json={'pdf_ids':[pdf_id],'question':question,'answer_length':length})
    events=[json.loads(e) for e in response.text.splitlines()]
    assert calls==list(range(1,11))
    assert sum(e['type']=='done' for e in events)==1 and events[-1]['type']=='done'
    metrics=events[-1]['metrics']
    assert metrics['questions_completed']==10 and metrics['generated_tokens']==200
    assert metrics['context_tokens_per_question']==8192
    assert len(metrics['sources'])==10
    answer=''.join(e.get('content','') for e in events)
    for i in range(1,11):
        assert f'### Question {i}\n' in answer and f'Fact {i}. [S{i}]' in answer
        assert metrics['sources'][i-1]['excerpt']==f'Fact for topic {i}.'


def test_failed_question_does_not_stop_later_answers_or_claim_complete(client,pdf_bytes,monkeypatch):
    pdf_id,calls=install_batch_fakes(client,pdf_bytes,monkeypatch,fail_number=2)
    question='1. Explain topic 1?\n2. Explain topic 2?\n3. Explain topic 3?'
    events=[json.loads(e) for e in client.post('/summarizer/chat',json={'pdf_ids':[pdf_id],'question':question}).text.splitlines()]
    assert calls==[1,2,3]
    assert events[-1]['type']=='error' and events[-1]['metrics']['failed_questions']==1
    assert events[-1]['metrics']['questions_completed']==2
    assert not any(e['type']=='done' for e in events)
    assert 'Fact 3.' in ''.join(e.get('content','') for e in events)
    assert events[-1]['metrics']['question_results'][1]['attempts']==2


def test_cutoff_retries_once_with_same_evidence_and_counts_actual_work(client,pdf_bytes,monkeypatch):
    pdf_id,searches=install_batch_fakes(client,pdf_bytes,monkeypatch)
    calls=[]
    async def generate(messages,**kwargs):
        number=int(re.search(r'topic (\d+)',messages[-1]['content'])[1])
        calls.append((number,kwargs['answer_length']))
        retry=number==1 and sum(n==1 for n,_ in calls)==2
        yield 'Completed fact. [S1]' if number==2 or retry else 'Unfinished draft'
        kwargs['telemetry'].update(done_reason='stop' if number==2 or retry else 'length',generated_tokens=30,generation_ms=100)
    monkeypatch.setattr(LLMService,'stream_messages',generate)
    events=[json.loads(e) for e in client.post('/summarizer/chat',json={'pdf_ids':[pdf_id],'question':'1. Explain topic 1? 2. Explain topic 2?'}).text.splitlines()]
    assert searches==[1,2] and calls==[(1,'short'),(1,'long'),(2,'short')]
    assert events[-1]['type']=='done' and events[-1]['metrics']['generated_tokens']==90
    assert 'Unfinished draft' not in rendered(events)
    assert any(e['type']=='replace_text' for e in events)


def test_unverifiable_long_draft_falls_back_to_checked_short_answer(client,pdf_bytes,monkeypatch):
    pdf_id,searches=install_batch_fakes(client,pdf_bytes,monkeypatch)
    calls=[]
    async def generate(messages,**kwargs):
        number=int(re.search(r'topic (\d+)',messages[-1]['content'])[1])
        calls.append((number,kwargs['answer_length']))
        yield 'It says "This is an invented source quotation." [S1]' if kwargs['answer_length']=='long' else 'A brief fact. [S1]'
        kwargs['telemetry'].update(done_reason='stop',generated_tokens=30,generation_ms=100)
    monkeypatch.setattr(LLMService,'stream_messages',generate)
    events=[json.loads(e) for e in client.post('/summarizer/chat',json={'pdf_ids':[pdf_id],'question':'1. Explain topic 1? 2. Explain topic 2?','answer_length':'long'}).text.splitlines()]
    assert searches==[1,2] and calls==[(1,'long'),(1,'short'),(2,'long'),(2,'short')]
    assert events[-1]['type']=='done' and events[-1]['metrics']['shortened_questions']==2
    answer=rendered(events)
    assert 'invented source quotation' not in answer
    assert answer.count('detailed draft did not pass validation')==2


@pytest.mark.parametrize('text',[
    'A cited fact [S12] and more.',
    'شاهد [ س ۱۲ ] و توضیح فارسی.',
    'Literal `[S12]` and $[S12]$; real [S12].',
    '```text\n[S12]\n```\nEvidence [S12].',
    'Unknown [S9], unfinished [S',
])
def test_streaming_citations_match_final_render_for_every_chunk_boundary(text):
    from app.services.citations import canonical_citations
    expected=remap_citations(canonical_citations(text),{'S12':'S4'})
    for cut in range(len(text)+1):
        writer=CitationStream({'S12':'S4'});visible=''
        for chunk in [text[:cut],text[cut:]]:
            update=writer.feed(chunk)
            if update:
                value,replace=update;visible=value if replace else visible+value
        update=writer.feed(final=True)
        if update:
            value,replace=update;visible=value if replace else visible+value
        assert visible==expected


@pytest.mark.anyio
async def test_numbered_long_answer_streams_before_model_finishes(monkeypatch):
    from app.schemas import ChatRequest
    from fastapi.responses import StreamingResponse
    closed=asyncio.Event()
    async def response(*args,**kwargs):
        async def body():
            try:
                yield summarizer._event('metadata',sources=[{'id':'S1','pdf_id':1,'page':1,'filename':'test.pdf','excerpt':'Evidence'}])
                yield summarizer._event('text',content='First visible words ')
                await asyncio.Event().wait()
            finally:closed.set()
        return StreamingResponse(body())
    monkeypatch.setattr(summarizer,'_document_chat',response)
    request=ChatRequest(question='1. Explain one? 2. Explain two?',pdf_ids=[1],answer_length='long')
    stream=summarizer._question_batch_events(request,[],numbered_questions(request.question))
    events=[]
    while not any(e['type']=='text' for e in events):
        events.append(json.loads(await asyncio.wait_for(anext(stream),timeout=1)))
    assert 'First visible words' in events[-1]['content']
    assert events[-2]['sources'][0]['id']=='S1'
    assert not closed.is_set()  # The model is still waiting, not finished.
    await stream.aclose()
    assert closed.is_set()


@pytest.mark.anyio
async def test_cancel_batch_stops_before_next_question(monkeypatch):
    from app.schemas import ChatRequest
    from fastapi.responses import StreamingResponse
    entered,closed=asyncio.Event(),asyncio.Event()
    calls=[]
    async def response(*args,**kwargs):
        calls.append(1)
        async def body():
            try:
                entered.set(); await asyncio.Event().wait(); yield ''
            finally: closed.set()
        return StreamingResponse(body())
    monkeypatch.setattr(summarizer,'_document_chat',response)
    request=ChatRequest(question='1. Explain one? 2. Explain two?',pdf_ids=[1])
    async def consume():
        async for _ in summarizer._question_batch_events(request,[],numbered_questions(request.question)): pass
    task=asyncio.create_task(consume());await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert closed.is_set() and calls==[1]
