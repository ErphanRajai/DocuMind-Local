"""An uploaded question paper is task data, never evidence for its own answers."""
import asyncio
import json
import re
from pydantic import BaseModel, Field, model_validator
from ..schemas import GenerationSettings
from .languages import detect_language, language_instruction
from .study_assistant import StudyRequest, study_events, paper_questions
from . import documents, study_store
from .citations import canonical_citations


class ExamRequest(GenerationSettings):
    workspace_id: str = Field(min_length=1, max_length=100)
    exam_pdf_id: int = Field(gt=0)
    reference_pdf_ids: list[int] = Field(min_length=1, max_length=3)
    approve_calculations: bool = False

    @model_validator(mode='after')
    def separate_documents(self):
        if self.exam_pdf_id in self.reference_pdf_ids: raise ValueError('Choose study references separately from the question paper.')
        if any(type(value) is not int or value < 1 for value in self.reference_pdf_ids): raise ValueError('Use valid reference document IDs.')
        self.reference_pdf_ids = list(dict.fromkeys(self.reference_pdf_ids))
        return self


def mathematical_question(question):
    return bool(re.search(r'\b(?:solve|differentiate|integrate|convert|determinant|derivative)\b|معادله|مشتق|انتگرال|محیط|مساحت|تبدیل|[a-zA-Z]\s*[=^]', question, re.I))


async def exam_events(request, event):
    from ..routers.summarizer import _ready_documents
    await _ready_documents(request.reference_pdf_ids)
    await _ready_documents([request.exam_pdf_id])
    pages = await asyncio.to_thread(documents.read_pages, [request.exam_pdf_id])
    questions = paper_questions(pages)
    if not questions: raise ValueError('No numbered questions were found. Use Exam paper to edit a question, or transcribe a scanned paper first.')
    if len(questions) > 20: raise ValueError('Split the exam into papers of at most 20 questions. No questions were silently omitted.')
    language = detect_language('\n'.join(p['text'] for p in pages)[:12000]) if request.answer_language == 'auto' else request.answer_language
    yield event('metadata', answer_language=language, question_count=len(questions), exam_pdf_id=request.exam_pdf_id,
                reference_pdf_ids=request.reference_pdf_ids)
    answers, failures = [], 0
    for index, question in enumerate(questions):
        yield event('status', phase='exam', message=f'Question {index + 1} of {len(questions)}', question_index=index)
        text, metadata, terminal = '', {}, False
        try:
            task = StudyRequest(question=question['text'], pdf_ids=request.reference_pdf_ids,
                model=request.model, answer_language=language, provider=request.provider,
                api_key=request.api_key, api_base_url=request.api_base_url, answer_length='long',
                task='problem' if mathematical_question(question['text']) else 'notes',
                question_origin='question-paper',
                approve_calculation=request.approve_calculations)
            async for line in study_events(task, event):
                row = json.loads(line)
                if row['type'] == 'text': text += row.get('content','')
                elif row['type'] == 'metadata': metadata.update({k:v for k,v in row.items() if k != 'type'})
                elif row['type'] == 'done': metadata.update(row.get('metrics',{})); terminal = True
                elif row['type'] == 'error': raise ValueError(row.get('message','Question failed'))
                # Sub-task progress is forwarded; text is emitted only as a complete question result.
                elif row['type'] == 'status': yield event('status', phase=row.get('phase'), message=f"{index + 1}/{len(questions)} · {row.get('message','')}")
            if not terminal or not text.strip(): raise ValueError('The question did not return a completed answer.')
            text = canonical_citations(text)
            status = 'needs_review' if metadata.get('awaiting_interpretation') else 'needs_information' if metadata.get('evidence_status') == 'needs_information' or (metadata.get('interpretation') or {}).get('missing') or metadata.get('clarification_required') else 'answered'
            answer = {'number':question['number'], 'page':question['page'], 'question':question['text'],
                      'answer':text, 'status':status, 'sources':metadata.get('sources',[]), 'metrics':metadata}
        except asyncio.CancelledError: raise
        except Exception:
            failures += 1
            answer = {'number':question['number'], 'page':question['page'], 'question':question['text'],
                      'answer':'پاسخ این سؤال کامل نشد. آن را جداگانه بررسی و دوباره تلاش کنید.' if language == 'fa' else 'This question failed. Review it separately and retry.', 'status':'failed', 'sources':[]}
        answers.append(answer)
        await asyncio.to_thread(study_store.save_item, request.workspace_id, 'exam_answer',
            {**answer, 'title':f"Question {question['number']}", 'exam_pdf_id':request.exam_pdf_id, 'answer_language':language})
        yield event('question', **answer)
        yield event('text', content=f"\n\n### {'سؤال' if language == 'fa' else 'Question'} {question['number']}\n\n{text if answer['status'] != 'failed' else answer['answer']}\n")
    yield event('done', metrics={'answer_language':language, 'question_count':len(answers), 'failed_questions':failures,
                'review_required':sum(a['status'] in {'needs_review','needs_information'} for a in answers), 'exam_complete':all(a['status']=='answered' for a in answers),
                'notice':'Answers require review. Tool checks verify interpreted inputs, not arbitrary exam accuracy.'})
