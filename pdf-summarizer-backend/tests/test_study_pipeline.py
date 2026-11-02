import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest

from app.services import advanced_retrieval as retrieval, study_assistant as assistant, synthesis
from app.services.math_engine import MathRequest, calculate
from app.services.context_budget import TokenCounter
from app.services.llm_service import LLMService
from app.services.errors import GenerationError

event=lambda kind,**data:json.dumps({'type':kind,**data})+'\n'


@pytest.mark.anyio
async def test_deep_search_reranks_and_keeps_document_coverage_and_neighbors(monkeypatch):
    async def search(ids,query,per_document=3):
        return [{'pdf_id':doc,'page':1,'text':'The governing formula','score':.1} for doc in ids],1
    monkeypatch.setattr(retrieval,'search_page_sources',search)
    monkeypatch.setattr(retrieval,'rerank',lambda q,h:list(reversed(h)))
    monkeypatch.setattr(retrieval,'read_pages',lambda ids:[{'pdf_id':1,'page':2,'text':'Continued example'}])
    hits,metrics=await retrieval.retrieve([1,2],'Find the formula; also explain the assumptions')
    assert {h['pdf_id'] for h in hits}=={1,2} and any(h['page']==2 for h in hits)
    assert metrics['reranker']=='cross-encoder' and metrics['search_queries']<=3
    monkeypatch.setattr(retrieval,'rerank',lambda *a:(_ for _ in ()).throw(ValueError()))
    assert 'unavailable' in (await retrieval.retrieve([1],'Find formula'))[1]['reranker']
    assert (await retrieval.retrieve([1],'Find formula',use_reranker=False))[1]['reranker']=='disabled'


@pytest.mark.anyio
async def test_structured_interpretation_is_validated_and_uses_bounded_context(monkeypatch):
    bodies=[]
    def response(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':'{"math":{"operation":"solve","equations":["2*x=8"],"variables":["x"]},"missing":[]}'},'done_reason':'stop'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        monkeypatch.setattr(LLMService,'_http_client',client)
        monkeypatch.setattr(LLMService,'model_profile',AsyncMock(return_value={'counter':TokenCounter(),'can_disable_thinking':True}))
        data,_=await assistant.structured(assistant.StudyRequest(question='Solve 2x=8'),'Translate','Solve 2x=8',assistant.ProblemPlan.model_json_schema())
        assert assistant.ProblemPlan.model_validate(data).calculator().expression=='2*x=8'
    assert bodies[0]['options']['num_ctx']==8192 and bodies[0]['think'] is False
    with pytest.raises(GenerationError):
        await assistant.structured(assistant.StudyRequest(question='x',provider='openai-compatible',api_base_url='https://example.test',api_key='test'),'','','')


@pytest.mark.anyio
async def test_interpreted_problem_calls_calculator_not_model_arithmetic(monkeypatch):
    async def structured(*args,**kwargs):return {'math':{'operation':'solve','equations':['2*x=8'],'variables':['x']},'missing':[],'assumptions':['Real domain']},{}
    async def solve(request):return calculate(request.model_dump())
    monkeypatch.setattr(assistant,'structured',structured);monkeypatch.setattr(assistant,'solve_bounded',solve)
    events=[json.loads(v) async for v in assistant.study_events(assistant.StudyRequest(question='Twice a number is eight',approve_calculation=True),event)]
    assert next(row for row in events if row['type']=='metadata' and row.get('math'))['math']['result']=='{4}'
    pending=[json.loads(v) async for v in assistant.study_events(assistant.StudyRequest(question='Twice a number is eight'),event)]
    assert pending[-1]['metrics']['awaiting_interpretation'] is True


@pytest.mark.anyio
async def test_question_paper_reports_structured_missing_evidence(monkeypatch):
    source={'id':'S1','pdf_id':1,'page':1,'filename':'notes.pdf','text':'The lab name is not recorded.'}
    monkeypatch.setattr('app.routers.summarizer._ready_documents',AsyncMock(return_value=[{'id':1,'raw_text':source['text']}]))
    monkeypatch.setattr(assistant,'retrieve',AsyncMock(return_value=([source],{})))
    monkeypatch.setattr(assistant,'bind_sources',lambda *args:[source])
    async def response(request,system,question,schema,sources=None):
        assert sources and 'needs_information' in system
        return {'status':'needs_information','answer':'The lab name is not recorded. [S1]'}, {'sources':[{**source,'excerpt':source['text']}]}
    monkeypatch.setattr(assistant,'structured',response)
    rows=[json.loads(v) async for v in assistant.study_events(assistant.StudyRequest(question='Name the lab',task='notes',pdf_ids=[1],question_origin='question-paper'),event)]
    assert rows[-1]['metrics']['evidence_status']=='needs_information'
    assert rows[-1]['metrics']['sources'][0]['pdf_id']==1


@pytest.mark.anyio
async def test_note_answers_preserve_actual_prompt_sources_and_check_quotes(monkeypatch):
    source={'id':'S1','pdf_id':1,'page':1,'filename':'notes.pdf','text':'A triangle has three sides.'}
    async def ready(ids):return [{'id':1,'raw_text':source['text']}]
    monkeypatch.setattr('app.routers.summarizer._ready_documents',ready)
    monkeypatch.setattr(assistant,'retrieve',AsyncMock(return_value=([{'pdf_id':1,'page':1,'text':source['text']}],{'retrieval_ms':1})))
    monkeypatch.setattr(assistant,'bind_sources',lambda *args:[source])
    metadata={'sources':[{**source,'excerpt':source['text']}],'excerpts_shortened':0}
    monkeypatch.setattr(LLMService,'prepare_prompt',AsyncMock(return_value=SimpleNamespace(messages=[],metadata=metadata)))
    async def stream(*a,**k):yield 'A triangle has three sides. [S1]'
    monkeypatch.setattr(LLMService,'stream_messages',stream)
    events=[json.loads(v) async for v in assistant.study_events(assistant.StudyRequest(question='Explain triangles',task='notes',pdf_ids=[1],mode='hint',working='Three',rubric='One mark'),event)]
    assert events[-1]['type']=='done' and events[-1]['metrics']['sources'][0]['id']=='S1'
    async def bad(*a,**k):yield 'A triangle has seven sides. [S99]'
    monkeypatch.setattr(LLMService,'stream_messages',bad)
    with pytest.raises(GenerationError):
        _=[v async for v in assistant.study_events(assistant.StudyRequest(question='Explain',task='notes',pdf_ids=[1]),event)]


@pytest.mark.anyio
async def test_synthesis_reviews_all_segments_then_reduces(monkeypatch):
    async def review(*args):
        yield event('metadata',sources=[{'id':'S1','excerpt':'Fact'}])
        yield event('status',message='Reviewing')
        yield event('text',content='A documented fact. [S1]')
        yield event('text',content='A second documented fact. [S1]')
        yield event('done',metrics={'segments_reviewed':2})
    monkeypatch.setattr(synthesis,'review_events',review)
    monkeypatch.setattr(LLMService,'prepare_prompt',AsyncMock(return_value=SimpleNamespace(messages=[])))
    async def stream(*args,**kwargs):yield 'Consolidated facts. [S1]'
    monkeypatch.setattr(LLMService,'stream_messages',stream)
    rows=[json.loads(v) async for v in synthesis.synthesis_events(assistant.StudyRequest(question='Main findings',pdf_ids=[1]),[],event)]
    assert rows[-1]['metrics']['segments_synthesized']==2 and rows[-1]['metrics']['reduction_rounds']==1
    async def bad(*args,**kwargs):yield 'Unknown [S99]'
    monkeypatch.setattr(LLMService,'stream_messages',bad)
    with pytest.raises(GenerationError):_=[v async for v in synthesis.synthesis_events(assistant.StudyRequest(question='Main findings',pdf_ids=[1]),[],event)]


def test_checked_practice_api_stores_separate_answers(client,monkeypatch):
    from app.routers import study
    async def solve(request):return calculate(request.model_dump())
    monkeypatch.setattr(study,'solve_bounded',solve)
    for topic in ['linear','quadratic','derivative','integral']:
        response=client.post('/summarizer/study/practice',json={'workspace_id':'practice','count':1,'topic':topic})
        assert response.status_code==200 and response.json()['items'][0]['data']['checked']


def test_pdf_text_geometry_and_structured_chunks(client,pdf_bytes):
    from app.services.pdf_processor import PDFProcessorService
    uploaded=client.post('/summarizer/upload',files={'files':('geometry.pdf',pdf_bytes,'application/pdf')}).json()[0]
    geometry=client.get(f"/summarizer/documents/{uploaded['id']}/pages/1/text?search=garden").json()
    assert geometry['words'] and geometry['highlights']
    assert all(0<=box['x']<=1 for box in geometry['words'])
    chunks=PDFProcessorService.structured_chunks('Definition\n\n'+'x'*5000+'\nQuestion 2 Solve this.\n\nFinal sentence.')
    assert all(len(chunk)<=2000 for chunk in chunks) and 'Final sentence.' in chunks[-1]


def test_duplicate_upload_reuses_ready_record(client,pdf_bytes):
    first=client.post('/summarizer/upload',files={'files':('same.pdf',pdf_bytes,'application/pdf')}).json()[0]
    again=client.post('/summarizer/upload',files={'files':('renamed.pdf',pdf_bytes,'application/pdf')}).json()[0]
    assert again['id']==first['id']
    assert client.post('/summarizer/upload',files=[('files',('a.pdf',pdf_bytes,'application/pdf')),('files',('b.pdf',pdf_bytes,'application/pdf'))]).status_code==400


def test_invalid_image_and_optional_layout_parser_are_actionable(client,monkeypatch):
    assert client.post('/summarizer/study/transcribe',files={'image':('bad.png',b'bad','image/png')}).status_code==422
    assert client.post('/summarizer/study/vision',json={'model':'fake','image_base64':'not-base64'}).status_code==422
    from app.services.layout_extraction import extract_with_docling
    monkeypatch.setitem(__import__('sys').modules,'docling.document_converter',None)
    from app.services.errors import PDFProcessingError
    with pytest.raises(PDFProcessingError,match='not installed'):extract_with_docling('none.pdf')


@pytest.mark.parametrize('plan,operation',[
    ({'operation':'units','magnitude':36,'from_unit':'km/h','to_unit':'m/s'},'units'),
    ({'operation':'matrix','matrix':[[1,2],[3,4]]},'matrix'),
    ({'operation':'differentiate','expression':'x^3','variable':'x'},'differentiate'),
    ({'operation':'solve','equations':['x+y=5','x-y=1'],'variables':['x','y']},'solve'),
])
def test_operation_specific_plans_do_not_invent_student_working(plan,operation):
    parsed=assistant.ProblemPlan.model_validate({'math':plan,'missing':[]})
    request=parsed.calculator()
    assert request.operation==operation and request.working==[]
    assert parsed.public()['math']['operation']==operation


def test_sqlite_backup_and_library_metadata(client,pdf_bytes):
    created=client.post('/summarizer/upload',files={'files':('library.pdf',pdf_bytes,'application/pdf')}).json()[0]
    assert client.get('/summarizer/library').json()[0]['id']==created['id']
    versions=client.get(f"/summarizer/study/document-versions?ids={created['id']}").json()
    assert len(versions[0]['text_sha256'])==64
    backup=client.post('/summarizer/study/backup').json()
    response=client.get(backup['download'])
    assert response.content.startswith(b'SQLite format 3')
    assert client.get('/summarizer/study/backups/bad.sqlite').status_code==404
