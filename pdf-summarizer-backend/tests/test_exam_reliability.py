import asyncio,io,json,zipfile
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from app.services import exam_assistant as exams,exam_runs,study_store,workspace_archive as archives,documents
from app.services.study_assistant import paper_questions
from app.models import PDFDocument,PDFPage

def event(kind,**data):return json.dumps({'type':kind,**data})+'\n'

def test_long_questions_preserved():
    text='Question 1. '+('Long statement '*1000)
    row=paper_questions([{'pdf_id':1,'page':1,'text':text}])[0]
    assert row['text']==text.strip() and row['warnings']

def test_question_limit_is_explicit():
    with pytest.raises(ValueError,match='omitted'):
        paper_questions([{'pdf_id':1,'page':1,'text':'\n'.join(f'Question {n}. Question content' for n in range(1,202))}])

@pytest.mark.anyio
async def test_checkpoint_resume_reuses_completed_questions(monkeypatch,db_session):
    monkeypatch.setattr('app.routers.summarizer._ready_documents',AsyncMock(return_value=[{'id':1,'raw_text':'Public source'}]))
    monkeypatch.setattr(documents,'read_pages',lambda ids:[{'pdf_id':2,'page':1,'text':'Question 1. Define energy\nQuestion 2. Name the lab'}])
    monkeypatch.setattr(exams,'classify_question',AsyncMock(return_value=exams.QuestionRoute(category='concept',missing_visual=False)))
    calls=[]
    async def generate(request,event):
        calls.append(request.question)
        yield event('text',content='Public answer')
        yield event('done',metrics={'evidence_status':'needs_information' if 'lab' in request.question else 'answered'})
    monkeypatch.setattr(exams,'study_events',generate)
    request=exams.ExamRequest(workspace_id='w',exam_pdf_id=2,reference_pdf_ids=[1])
    gen=exams.exam_events(request,event)
    rows=[]
    async for line in gen:
        row=json.loads(line);rows.append(row)
        if row['type']=='question':break
    key=next(r['run_id'] for r in rows if r['type']=='metadata')
    await gen.aclose()
    assert exam_runs.read(key)['state']=='interrupted'
    request.run_id=key
    results=[json.loads(line) async for line in exams.exam_events(request,event)]
    assert len(calls)==2 and next(r for r in results if r['type']=='question')['reused']
    assert len(study_store.items('w','exam_answer'))==2
    assert results[-1]['metrics']['review_required']==1 and not results[-1]['metrics']['exam_complete']
    assert 'api_key' not in json.dumps(exam_runs.read(key))
    monkeypatch.setattr('app.routers.summarizer._ready_documents',AsyncMock(return_value=[{'id':1,'raw_text':'Changed'}]))
    with pytest.raises(HTTPException) as e:await exams.prepare_run(request)
    assert e.value.status_code==409

def test_exclusive_run_claim(db_session):
    key=exam_runs.create('w',{'questions':[],'answers':{},'request':{}})
    exam_runs.claim(key)
    with pytest.raises(HTTPException) as e:exam_runs.claim(key)
    assert e.value.status_code==409

def test_archive_round_trip_preserves_pdfs_and_annotations(client,db_session,pdf_bytes,tmp_path):
    source=Path(documents.UPLOAD_DIR)/'original.pdf';source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(pdf_bytes)
    r=PDFDocument(filename='public-notes.pdf',file_path=str(source),raw_text='public text',page_count=1,source_version=1,status='completed')
    db_session.add(r);db_session.flush();old=r.id
    db_session.add(PDFPage(pdf_id=old,number=1,label='1',text='public text'));db_session.commit()
    study_store.save_workspace('original',{'id':'original','title':'Public workspace','documents':[{'id':old,'filename':'public-notes.pdf'}],'messages':[],'updated':1})
    study_store.save_item('original','annotation',{'pdf_id':old,'answer':'My local note'})
    exported=client.get('/summarizer/workspaces/original/archive');assert exported.status_code==200
    restored=client.post('/summarizer/workspaces/restore',files={'archive':('backup.zip',exported.content,'application/zip')});assert restored.status_code==201,restored.text
    key=restored.json()['workspace_id'];workspace=next(w for w in study_store.workspaces() if w['id']==key)
    new=workspace['documents'][0]['id'];assert new!=old
    assert Path(documents.document_file(new)[0]).read_bytes()==pdf_bytes
    assert study_store.items(key)[0]['data']['pdf_id']==new
    assert next(w for w in study_store.workspaces() if w['id']=='original')['documents'][0]['id']==old

def test_archive_rejects_unlisted_paths_and_cleans_staging(tmp_path,monkeypatch):
    monkeypatch.setattr(documents,'UPLOAD_DIR',str(tmp_path))
    body=io.BytesIO()
    with zipfile.ZipFile(body,'w') as z:
        z.writestr('manifest.json',json.dumps({'format':'documind-workspace-2','documents':[]}));z.writestr('../escape','bad')
    with pytest.raises(ValueError,match='Unexpected'):archives.prepare_archive(body.getvalue())
    assert not list(tmp_path.iterdir())

def test_feedback_does_not_overwrite_answer(db_session):
    key=exam_runs.create('w',{'request':{},'answers':{'0':{'answer':'original'}}})
    exam_runs.feedback(key,0,{'reason':'citation','correction':'Check page 2'})
    assert exam_runs.read(key)['answers']['0']['answer']=='original'
    assert study_store.items('w','answer_feedback')[0]['data']['correction']=='Check page 2'


def test_explicit_heading_lookup_does_not_confuse_12_and_120():
    from app.services.advanced_retrieval import heading_matches
    pages=[{'pdf_id':1,'page':12,'text':'Chapter 12\nFact'}, {'pdf_id':1,'page':120,'text':'Chapter 120\nDifferent fact'}]
    assert [p['page'] for p in heading_matches('در فصل ۱۲ چه آمده است؟',pages)]==[12]
    assert heading_matches('What are the facts?',pages)==[]


def test_soft_hyphen_in_extracted_mathematics_is_normalized():
    from app.services.study_assistant import explicit_equation
    from app.services.math_engine import calculate
    question='Solve the equation.\nx^2 \u00ad 5*x + 6 = 0'
    plan=explicit_equation(question)
    assert plan['equations']==['x^2 - 5*x + 6 = 0']
    assert calculate({'expression':plan['equations'][0]})['result']=='{2, 3}'
    assert paper_questions([{'pdf_id':1,'page':1,'text':'Question 1. '+question}])[0]['warnings']
