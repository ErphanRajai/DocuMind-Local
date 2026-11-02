import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.schemas import ChatRequest
from app.services.languages import detect_language, normalize_digits, language_instruction
from app.services.study_assistant import paper_questions, calculation_markdown
from app.services.math_engine import calculate
from app.services.exam_assistant import ExamRequest, exam_events


def test_persian_digits_and_language_do_not_need_network():
    assert normalize_digits('۱۲٫۵ + ٣') == '12.5 + 3'
    assert detect_language('پرسش فارسی چیست؟') == 'fa'
    assert calculate({'expression':'x^۲ - ۵*x + ۶ = ۰'})['result'] == '{2, 3}'
    assert 'Persian' in language_instruction('auto','این یک پرسش است')


def test_persian_paper_questions_keep_original_text_and_marks():
    rows=paper_questions([{'pdf_id':8,'page':1,'text':'آزمون فارسی\nسؤال ۱. انرژی چیست؟ [۲ نمره]\nسؤال ۲. معادله x^2=4 را حل کنید. [۳ نمره]'}])
    assert len(rows)==2 and rows[0]['number']=='1' and rows[1]['marks']==3
    assert 'انرژی' in rows[0]['text']
    broken=paper_questions([{'pdf_id':8,'page':1,'text':'سؤال ۱\n. انرژی چیست؟ ]۲\n نمره['}])
    assert len(broken)==1 and broken[0]['marks']==2


def test_real_persian_fixture_extraction_and_question_boundaries():
    from app.services.pdf_processor import PDFProcessorService
    root=Path(__file__).resolve().parents[2]
    fixture=root/'docs/examples/persian/exam-fa.pdf'
    if not fixture.exists(): pytest.skip('Run the public Persian fixture generator first')
    extracted=PDFProcessorService.extract_document(str(fixture))
    rows=paper_questions([{'pdf_id':1,'page':p.number,'text':p.text} for p in extracted.pages])
    assert len(rows)==4 and rows[2]['marks']==2 and 'x^2' in rows[2]['text']


def test_persian_calculation_has_native_headings_and_math():
    answer=calculation_markdown(calculate({'expression':'x^2-5*x+6=0'}),language='fa')
    assert 'نتیجهٔ محاسبه' in answer and '$$' in answer and 'Calculated result' not in answer


def test_explicit_equation_is_preserved_without_model_reinterpretation():
    from app.services.study_assistant import explicit_equation
    value=explicit_equation('معادلهٔ زیر را حل کنید.\nx^۲ − ۵*x + ۶ = ۰')
    assert value['operation']=='solve' and value['equations']==['x^2 - 5*x + 6 = 0']
    assert explicit_equation('Differentiate this equation:\nx^2=4') is None
    assert explicit_equation('Solve the following two equations:\nx=2\nx=3') is None


def test_local_only_rejects_hosted_provider_before_request(monkeypatch):
    monkeypatch.setenv('DOCUMIND_LOCAL_ONLY','1')
    with pytest.raises(ValueError,match='local-only'):
        ChatRequest(question='test',provider='openai-compatible',api_key='not-a-real-key',api_base_url='https://example.test/v1')
    with pytest.raises(ValueError,match='Cloud-backed'):
        ChatRequest(question='test',model='some-model:cloud')
    from app.services.llm_service import LLMService
    from app.services.errors import GenerationError
    with pytest.raises(GenerationError,match='only to this computer'):
        LLMService.require_local_endpoint('https://example.test/api/chat')
    LLMService.require_local_endpoint('http://host.docker.internal:21434/api/chat')


def test_persian_quotation_must_match_its_reference():
    from app.services.citations import check_quotes
    sources=[{'id':'S1','text':'انرژی توانایی انجام کار است.'}]
    assert check_quotes('«انرژی توانایی انجام کار است.» [S1]', sources)[0]['verified']
    assert not check_quotes('«انرژی مقدار دمای آب در آغاز است.» [S1]', sources)[0]['verified']
    from app.services.citations import canonical_citations, citation_warning
    assert canonical_citations('جواب [س۱] و `[س۱]`') == 'جواب [S1] و `[س۱]`'
    assert canonical_citations('جواب [ S1 ] و [ س ۱ ]') == 'جواب [S1] و [S1]'
    assert citation_warning('جواب [س۱]',sources)==''
    assert citation_warning('جواب [س۹۹]',sources)=='invalid'


def test_exam_cannot_use_question_paper_as_evidence():
    with pytest.raises(ValueError,match='separately'):
        ExamRequest(workspace_id='w',exam_pdf_id=2,reference_pdf_ids=[2])


@pytest.mark.anyio
async def test_exam_uses_only_references_and_saves_per_question(monkeypatch,db_session):
    import app.services.exam_assistant as module
    monkeypatch.setattr(module,'classify_question',AsyncMock(return_value=module.QuestionRoute(category='concept',missing_visual=False)))
    monkeypatch.setattr('app.routers.summarizer._ready_documents',AsyncMock(return_value=[]))
    monkeypatch.setattr(module.documents,'read_pages',lambda _: [{'pdf_id':2,'page':1,'text':'سؤال ۱. انرژی چیست؟'}])
    saved=[]
    monkeypatch.setattr(module.study_store,'save_item',lambda *args: saved.append(args))
    async def answer(request,event):
        assert request.pdf_ids == [1] and request.answer_language=='fa'
        yield event('metadata',interpretation=None,sources=[{'id':'S1','pdf_id':1,'page':1,'filename':'notes.pdf','excerpt':'انرژی توانایی انجام کار است.'}])
        yield event('text',content='انرژی توانایی انجام کار است. [S1]')
        yield event('done',metrics={})
    monkeypatch.setattr(module,'study_events',answer)
    event=lambda kind,**data:json.dumps({'type':kind,**data})+'\n'
    rows=[json.loads(line) async for line in exam_events(ExamRequest(workspace_id='w',exam_pdf_id=2,reference_pdf_ids=[1]),event)]
    question=next(row for row in rows if row['type']=='question')
    assert question['sources'][0]['pdf_id']==1 and len(saved)==1
    assert rows[-1]['metrics']['failed_questions']==0


@pytest.mark.anyio
async def test_exam_preserves_missing_information_status_and_counts(monkeypatch,db_session):
    import app.services.exam_assistant as module
    monkeypatch.setattr(module,'classify_question',AsyncMock(return_value=module.QuestionRoute(category='concept',missing_visual=False)))
    monkeypatch.setattr('app.routers.summarizer._ready_documents',AsyncMock(return_value=[]))
    monkeypatch.setattr(module.documents,'read_pages',lambda _: [{'pdf_id':2,'page':1,'text':'Question 1. Name the lab'}])
    monkeypatch.setattr(module.study_store,'save_item',lambda *args:None)
    async def answer(request,event):
        yield event('text',content='The lab name is absent.')
        yield event('done',metrics={'evidence_status':'needs_information'})
    monkeypatch.setattr(module,'study_events',answer)
    event=lambda kind,**data:json.dumps({'type':kind,**data})+'\n'
    rows=[json.loads(line) async for line in exam_events(ExamRequest(workspace_id='w',exam_pdf_id=2,reference_pdf_ids=[1]),event)]
    assert next(r for r in rows if r['type']=='question')['status']=='needs_information'
    assert rows[-1]['metrics']['review_required']==1 and not rows[-1]['metrics']['exam_complete']


def test_installer_preserves_unrelated_settings_and_is_repeatable(tmp_path):
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('setup_documind',root/'setup_documind.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'.env';path.write_text('# comment\nPRIVATE_SETTING=keep\nOLLAMA_CHAT_MODEL=old\n')
    module.update_environment(path,{'OLLAMA_CHAT_MODEL':'new','EMBED_VECTOR_DIM':'1024'})
    first=path.read_text();module.update_environment(path,{'OLLAMA_CHAT_MODEL':'new','EMBED_VECTOR_DIM':'1024'})
    assert path.read_text()==first and 'PRIVATE_SETTING=keep' in first and '# comment' in first


@pytest.mark.anyio
async def test_failed_exam_question_is_reported_without_losing_completed_answers(monkeypatch,db_session):
    import app.services.exam_assistant as module
    monkeypatch.setattr(module,'classify_question',AsyncMock(return_value=module.QuestionRoute(category='concept',missing_visual=False)))
    monkeypatch.setattr('app.routers.summarizer._ready_documents',AsyncMock(return_value=[]))
    monkeypatch.setattr(module.documents,'read_pages',lambda _: [{'pdf_id':2,'page':1,'text':'سؤال ۱. انرژی چیست؟\nسؤال ۲. دما چیست؟'}])
    saved=[];monkeypatch.setattr(module.study_store,'save_item',lambda *args:saved.append(args))
    async def answer(request,event):
        if 'دما' in request.question: raise ValueError('Model unavailable')
        yield event('text',content='انرژی توانایی انجام کار است.')
        yield event('done',metrics={})
    monkeypatch.setattr(module,'study_events',answer)
    event=lambda kind,**data:json.dumps({'type':kind,**data})+'\n'
    rows=[json.loads(line) async for line in exam_events(ExamRequest(workspace_id='w',exam_pdf_id=2,reference_pdf_ids=[1]),event)]
    assert [r['status'] for r in rows if r['type']=='question']==['answered','failed']
    assert rows[-1]['metrics']['failed_questions']==1 and not rows[-1]['metrics']['exam_complete'] and len(saved)==2


def test_read_only_installer_check_never_downloads_or_changes_settings(tmp_path,monkeypatch):
    from unittest.mock import MagicMock
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('setup_check',root/'setup_documind.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setattr(module,'ROOT',tmp_path);monkeypatch.setattr(module.sys,'argv',['setup_documind.py','--check'])
    monkeypatch.setattr(module.shutil,'which',lambda name:name)
    monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:MagicMock(returncode=0))
    monkeypatch.setattr(module.urllib.request,'urlopen',MagicMock(side_effect=OSError('Not running')))
    def forbidden(*args,**kwargs): raise AssertionError('Read-only check attempted a mutation')
    monkeypatch.setattr(module,'pull_model',forbidden);monkeypatch.setattr(module,'update_environment',forbidden);monkeypatch.setattr(module,'run',forbidden)
    assert module.main()==1
