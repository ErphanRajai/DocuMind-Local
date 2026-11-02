"""Public Persian fixture: real PDF extraction, retrieval, local model and checked math."""
import argparse
import html
import json
from pathlib import Path
import time
import uuid
import unicodedata
import fitz
import httpx

ROOT=Path(__file__).resolve().parents[2]
EXAMPLES=ROOT/'docs'/'examples'/'persian'
NOTES=[
    'یادداشت‌های نمونهٔ فارسی؛ فقط برای آزمایش نرم‌افزار داکیومایند.',
    'در این درس، انرژی توانایی انجام کار است.',
    'در آزمایش کلاس، دمای آب در آغاز ۲۰ درجهٔ سلسیوس و در پایان ۳۰ درجهٔ سلسیوس بود. مدت آزمایش ۵ دقیقه بود.',
    'برای حل معادلهٔ درجهٔ دوم، ابتدا عبارت را تجزیه می‌کنیم. جواب‌های معادلهٔ نمونهٔ زیر ۲ و ۳ هستند. هر جواب باید در معادلهٔ اصلی جای‌گذاری و بررسی شود.',
    'x^2 − 5*x + 6 = 0',
    'نام آزمایشگاه در این جزوه ذکر نشده است. دادهٔ دیگری برای نام آن وجود ندارد.',
]
QUESTIONS=[
    'سؤال ۱. بر اساس جزوه، انرژی چیست؟ [۱ نمره]',
    'سؤال ۲. در آغاز آزمایش، دمای آب چند درجهٔ سلسیوس بود؟ [۱ نمره]',
    'سؤال ۳. معادلهٔ زیر را در اعداد حقیقی حل کنید و جواب‌ها را بررسی کنید. [۲ نمره]\nx^2 − 5*x + 6 = 0',
    'سؤال ۴. نام آزمایشگاهی که آزمایش در آن انجام شد چیست؟ [۱ نمره]',
]


def make_pdf(path,title,paragraphs):
    pieces=[]
    for text in paragraphs:
        for line in text.splitlines():
            direction='rtl' if any('\u0600' <= char <= '\u06ff' for char in line) else 'ltr'
            pieces.append(f'<p dir="{direction}">'+html.escape(line)+'</p>')
    content='<html dir="rtl" lang="fa"><body><h1>'+html.escape(title)+'</h1>'+''.join(pieces)+'</body></html>'
    font_dir=Path('C:/Windows/Fonts')
    css="@font-face{font-family:Persian;src:url(tahoma.ttf)}body{font-family:Persian;direction:rtl;font-size:16px;line-height:2}h1{font-size:23px}p{margin:18px 0}"
    with fitz.open() as document:
        page=document.new_page(width=595,height=842)
        spare,scale=page.insert_htmlbox(fitz.Rect(45,45,550,790),content,css=css,archive=fitz.Archive(str(font_dir)))
        if spare<0 or scale<0.8: raise RuntimeError('Persian fixture does not fit legibly.')
        document.save(path)
        page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(path.with_suffix('.png'))
        extracted=unicodedata.normalize('NFKC', page.get_text())
        if 'سؤال' not in extracted and 'انرژی' not in extracted: raise RuntimeError('Persian text did not survive native PDF extraction.')


def generate():
    EXAMPLES.mkdir(parents=True,exist_ok=True)
    make_pdf(EXAMPLES/'study-fa.pdf','جزوهٔ مطالعهٔ فارسی',NOTES)
    make_pdf(EXAMPLES/'exam-fa.pdf','آزمون نمونهٔ فارسی',QUESTIONS)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--generate',action='store_true');parser.add_argument('--base',default='http://127.0.0.1:8888');parser.add_argument('--model',default='qwen3:4b-instruct-2507-q4_K_M');args=parser.parse_args()
    if args.generate: generate();return
    with httpx.Client(base_url=args.base,timeout=300) as client:
        for attempt in range(60):
            try:
                if client.get('/healthz',timeout=3).json().get('status')=='healthy': break
            except (httpx.HTTPError,ValueError): pass
            time.sleep(1)
        else: raise RuntimeError('Local services did not become healthy; no model accuracy result was recorded.')
        documents=[]
        for name in ['study-fa.pdf','exam-fa.pdf']:
            with (EXAMPLES/name).open('rb') as stream:
                response=client.post('/summarizer/upload',files={'files':(name,stream,'application/pdf')});response.raise_for_status();record=response.json()[0]
            for attempt in range(120):
                record=client.get(f"/summarizer/documents/{record['id']}").json()
                if record['status'] in ['completed','partial','failed']:break
                time.sleep(1)
            if record['status'] not in ['completed','partial']: raise RuntimeError(f"Public fixture failed: {record.get('error_message',record['status'])}")
            documents.append(record)
        workspace='persian-demo-'+uuid.uuid4().hex[:8]
        response=client.put('/summarizer/workspaces/'+workspace,json={'workspace':{'id':workspace,'title':'آزمون فارسی — نمونهٔ عمومی','documents':[documents[0]],'messages':[],'updated':int(time.time()*1000)}});response.raise_for_status()
        paper=client.get(f"/summarizer/study/papers/{documents[1]['id']}");paper.raise_for_status()
        if len(paper.json()['questions'])!=4: raise RuntimeError(f"Expected four Persian questions; got {len(paper.json()['questions'])}.")
        payload={'workspace_id':workspace,'exam_pdf_id':documents[1]['id'],'reference_pdf_ids':[documents[0]['id']], 'model':args.model,'answer_language':'auto','approve_calculations':True}
        start=time.perf_counter();created=client.post('/summarizer/study/exams/jobs',json=payload);created.raise_for_status();rows=[]
        with client.stream('GET',f"/summarizer/jobs/{created.json()['id']}/events") as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                if line: rows.append(json.loads(line))
        answers=[row for row in rows if row['type']=='question']
        checks={
            'four_questions':len(answers)==4,
            'questions_processed':len(answers)==4 and all(row['status'] in {'answered','needs_information'} for row in answers),
            'persian_answers':len(answers)==4 and all(any(char in row['answer'] for char in 'پچگکی') for row in answers),
            'definition':bool(answers) and 'انرژی' in answers[0]['answer'] and 'کار' in answers[0]['answer'],
            'initial_temperature':len(answers)>1 and any(value in answers[1]['answer'] for value in ('۲۰','20')) and not any(value in answers[1]['answer'] for value in ('۳۰','30')),
            'checked_roots':len(answers)>2 and (answers[2].get('metrics',{}).get('math') or {}).get('result')=='{2, 3}' and bool((answers[2]['metrics'].get('math') or {}).get('verified')),
            'automatic_latex':len(answers)>2 and '$$' in answers[2]['answer'],
            'missing_evidence':len(answers)>3 and any(value in answers[3]['answer'] for value in ('ذکر نشده','وجود ندارد','مشخص نیست','ارائه نشده','نیامده','نامشخص','نمی‌توان')),
            'missing_information_status':len(answers)>3 and answers[3]['status']=='needs_information',
            'citations_only_references':bool(answers) and all(source['pdf_id']==documents[0]['id'] for row in answers for source in row.get('sources',[])),
        }
        report={'model':args.model,'workspace':workspace,'reference_pdf_id':documents[0]['id'],'exam_pdf_id':documents[1]['id'],'seconds':round(time.perf_counter()-start,1),'checks':checks,'answers':answers,'terminal':rows[-1], 'limitations':'One public synthetic Persian exam. Diagnostic auto-calculation was explicitly approved. Not an accuracy estimate for arbitrary exams or handwriting.'}
        output=ROOT/'output'/'persian-exam.json';output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'checks':checks,'workspace':workspace,'seconds':report['seconds']},ensure_ascii=True))
        if not all(checks.values()): raise SystemExit(1)


if __name__=='__main__':main()
