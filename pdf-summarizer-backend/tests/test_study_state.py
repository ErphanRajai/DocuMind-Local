import json
import pytest
from fastapi import HTTPException
from app.services import study_store as store
from app.services import job_journal
from app.services.jobs import Job
from app.services.math_engine import MathRequest
from app.services.study_assistant import StudyRequest, study_events


def workspace(): return {'id':'test-space','title':'Study','documents':[],'messages':[],'updated':123}


def test_workspace_conflict_export_remove_and_secret_rejection(client):
    value=workspace()
    response=client.put('/summarizer/workspaces/test-space',json={'workspace':value})
    assert response.json()['revision']==1
    assert client.put('/summarizer/workspaces/test-space',json={'workspace':value}).status_code==409
    assert client.put('/summarizer/workspaces/test-space',json={'workspace':value,'revision':1}).json()['revision']==2
    assert client.get('/summarizer/workspaces').json()[0]['title']=='Study'
    assert client.get('/summarizer/workspaces/test-space/export').json()['format']=='documind-study-1'
    value['messages']=[{'api_key':'do-not-store'}]
    assert client.put('/summarizer/workspaces/test-space',json={'workspace':value,'revision':2}).status_code==422
    assert client.delete('/summarizer/workspaces/test-space').status_code==200
    assert 'test-space' in client.get('/summarizer/workspaces/deleted').json()
    assert client.put('/summarizer/workspaces/test-space',json={'workspace':workspace()}).status_code==409
    assert client.get('/summarizer/workspaces/missing/export').status_code==404


def test_items_review_scope_and_cache(client):
    value=client.post('/summarizer/study/items',json={'workspace_id':'w','kind':'mistake','data':{'question':'x^2=4'}}).json()
    key=value['id']
    assert len(client.get('/summarizer/study/items/w').json())==1
    assert client.post('/summarizer/study/items',json={'workspace_id':'other','kind':'mistake','id':key,'data':{}}).status_code==409
    reviewed=client.post(f'/summarizer/study/items/{key}/review',json={'workspace_id':'w','correct':True}).json()
    assert reviewed['data']['interval_days']==1
    reviewed=client.post(f'/summarizer/study/items/{key}/review',json={'workspace_id':'w','correct':True}).json()
    assert reviewed['data']['interval_days']==2
    assert client.post(f'/summarizer/study/items/{key}/review',json={'workspace_id':'other','correct':True}).status_code==404
    assert client.get('/summarizer/study/storage').json()['study_items']==1
    assert client.post('/summarizer/study/cache/trim').json()['removed']==0
    assert client.delete('/summarizer/study/cache').status_code==200
    assert client.delete(f'/summarizer/study/items/{key}?workspace_id=w').status_code==200


def test_journal_recovery_does_not_claim_restart_completion(db_session):
    job=Job('journal-test','study',state='generating',events=[{'type':'text','content':'unfinished'}])
    job_journal.save(job)
    restored=job_journal.recover()[0]
    assert restored['state']=='failed' and restored['events'][-1]['type']=='error'
    assert 'restarted' in restored['events'][-1]['message']


@pytest.mark.anyio
async def test_explicit_study_calculation_and_missing_interpretation(monkeypatch):
    from app.services import study_assistant as assistant
    from app.services.math_engine import calculate
    async def solve(request): return calculate(request.model_dump())
    monkeypatch.setattr(assistant,'solve_bounded',solve)
    event=lambda kind,**values:json.dumps({'type':kind,**values})+'\n'
    result=[json.loads(v) async for v in study_events(StudyRequest(question='Solve',math=MathRequest(expression='x=3')),event)]
    assert result[-1]['type']=='done' and any('3' in row.get('content','') for row in result)
    async def missing(*args,**kwargs): return {'missing':['What is the initial velocity?'],'math':None},{}
    monkeypatch.setattr(assistant,'structured',missing)
    result=[json.loads(v) async for v in study_events(StudyRequest(question='How far does it go?'),event)]
    assert 'initial velocity' in ''.join(v.get('content','') for v in result)


def test_study_capabilities_and_calculator_api(client,monkeypatch):
    from app.routers import study
    from app.services.math_engine import calculate
    async def solve(request): return calculate(request.model_dump())
    monkeypatch.setattr(study,'solve_bounded',solve)
    assert client.post('/summarizer/study/solve',json={'expression':'x=7'}).json()['result']=='{7}'
    assert client.post('/summarizer/study/solve',json={'expression':'open("x")'}).status_code==422
    assert client.get('/summarizer/study/capabilities').json()['proof_checker'] is False
    assert client.get('/summarizer/study/papers/9999').status_code==404
    assert client.post('/summarizer/documents/9999/reindex').status_code==404
    assert client.patch('/summarizer/documents/9999',json={'filename':'new.pdf'}).status_code==404


def test_storage_bounds():
    with pytest.raises(HTTPException): store.encoded({'text':'x'*20},limit=10)
    with pytest.raises(HTTPException): store.encoded({'nested':{'password':'hidden'}})
