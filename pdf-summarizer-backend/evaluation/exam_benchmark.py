"""Generated 50-case bilingual regression suite over 120 source pages.

Oracles are programmatic, not teacher-reviewed. Supply real curriculum cases separately.
"""
import argparse,json,re,time,statistics,uuid,hashlib
from pathlib import Path
import fitz
import httpx

ROOT=Path(__file__).resolve().parents[2]
def reference_code(page):return 'REF-'+hashlib.sha256(('documind-public-topic-'+str(page)).encode()).hexdigest()[:10].upper()

def cases():
    rows=[]
    for i in range(30):
        page=1+(i*37)%120
        fa=i%2==1
        rows.append({'id':f'lookup-{i+1}','language':'fa' if fa else 'en','kind':'lookup',
          'question':f'کد مرجع موضوع {page} در منبع چیست؟' if fa else f'What is the reference code for Topic {page} in the source?',
          'expected':reference_code(page),'source_pages':[page]})
    for i in range(10):
        a,b=i+1,i+3;fa=i%2==1
        rows.append({'id':f'math-{i+1}','language':'fa' if fa else 'en','kind':'math','question':('معادله را در اعداد حقیقی حل کنید.' if fa else 'Solve the equation over the real numbers.')+f'\nx^2 - {a+b}*x + {a*b} = 0','expected':[a,b],'source_pages':[]})
    for i in range(10):
        fa=i%2==1
        rows.append({'id':f'missing-{i+1}','language':'fa' if fa else 'en','kind':'missing','question':f'تاریخ تولد مدرس موضوع {i+1} چیست؟' if fa else f'What is the birth date of the instructor for Topic {i+1}?','expected_status':'needs_information','source_pages':[]})
    return rows

def fixture():
    folder=ROOT/'output/exam-benchmark';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'source-120-pages.pdf'
    with fitz.open() as pdf:
        for n in range(1,121):
            page=pdf.new_page()
            page.insert_textbox(fitz.Rect(50,60,540,750),f'PUBLIC SYNTHETIC COURSE SOURCE\nTopic {n}\nReference code for Topic {n}: {reference_code(n)}\nThis code is an invented lookup fact for software evaluation.\nNo instructor birth dates are provided anywhere in this source.\nAlgebra method: factor a quadratic and substitute each root into the original equation.\nPage {n} of 120.',fontsize=13)
        pdf.save(path)
    return path

def score(case,row):
    text=row.get('answer','');status=row.get('status')
    if case['kind']=='lookup':correct=case['expected'] in text
    elif case['kind']=='missing':correct=status=='needs_information'
    else:
        math=(row.get('metrics') or {}).get('math') or {}
        values=sorted(int(n) for n in re.findall(r'-?\d+',math.get('result','')))
        correct=values==case['expected'] and math.get('verified') is True
    pages={s['page'] for s in row.get('sources',[])}
    # Retrieved evidence is not a citation until the answer actually references it.
    citation_text=re.sub(r'```[\s\S]*?(?:```|$)|`[^`]*`','',text)
    digits=str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')
    cited={'S'+n.translate(digits) for n in re.findall(r'\[\s*[Ssس]\s*([0-9۰-۹٠-٩]+)\s*\]',citation_text)}
    cited_pages={s['page'] for s in row.get('sources',[]) if s['id'] in cited}
    return {'correct':bool(correct),'retrieved_expected_page':None if not case['source_pages'] else bool(pages.intersection(case['source_pages'])),
        'citation_present':bool(cited_pages),'cited_expected_page':None if not case['source_pages'] else bool(cited_pages.intersection(case['source_pages'])),
        'language_matches':bool(re.search('[\u0600-\u06ff]',text)) if case['language']=='fa' else not bool(re.search('[\u0600-\u06ff]',text))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8888');p.add_argument('--limit',type=int,default=50);p.add_argument('--generate',action='store_true');p.add_argument('--cases',type=Path);p.add_argument('--source',type=Path);a=p.parse_args()
    selected=(json.loads(a.cases.read_text(encoding='utf-8')) if a.cases else cases())[:a.limit]
    if not 1<=len(selected)<=50:raise ValueError('Use --limit 1..50.')
    folder=ROOT/'output/exam-benchmark';folder.mkdir(parents=True,exist_ok=True)
    (folder/'cases.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
    source=a.source or fixture()
    if a.generate:print('Generated 120-page source and cases in '+str(folder));return
    # Exercise actual PDF extraction before sending the reviewed per-language cases.
    from persian_exam import make_pdf
    paper=folder/'questions.pdf'
    with fitz.open() as merged:
        for start in range(0,len(selected),5):
            part=folder/f'questions-part-{start}.pdf'
            make_pdf(part,'سؤال — Public bilingual paper',[f'Question {i+1}. '+selected[i]['question'] for i in range(start,min(start+5,len(selected)))])
            with fitz.open(part) as doc:merged.insert_pdf(doc)
            part.unlink()
        merged.save(paper)
    with httpx.Client(base_url=a.base,timeout=600) as client:
        docs=[]
        for path in [source,paper]:
            with path.open('rb') as f:r=client.post('/summarizer/upload',files={'files':(path.name,f,'application/pdf')});r.raise_for_status();record=r.json()[0]
            for _ in range(600):
                record=client.get(f"/summarizer/documents/{record['id']}").json()
                if record['status'] in {'completed','partial','failed'}:break
                time.sleep(1)
            if record['status'] not in {'completed','partial'}:raise RuntimeError('Benchmark source did not index.')
            docs.append(record)
        detected=client.get(f"/summarizer/study/papers/{docs[1]['id']}").json()['questions']
        if len(detected)!=len(selected):raise RuntimeError(f'Question extraction mismatch: expected {len(selected)}, detected {len(detected)}')
        workspace='benchmark-'+uuid.uuid4().hex[:12]
        r=client.put('/summarizer/workspaces/'+workspace,json={'workspace':{'id':workspace,'title':'Public 120-page exam benchmark','documents':[docs[0]],'messages':[],'updated':int(time.time()*1000)}});r.raise_for_status()
        report={'scope':'50 generated bilingual regression cases, not teacher-reviewed curriculum accuracy.','source_pages':docs[0]['page_count'],'detected_questions':len(detected),'workspace':workspace,'results':[]}
        for i,case in enumerate(selected):
            start=time.perf_counter()
            payload={'workspace_id':workspace,'exam_pdf_id':docs[1]['id'],'reference_pdf_ids':[docs[0]['id']],'answer_language':case['language'],'approve_calculations':True,'answer_style':'direct','questions':[{'number':case['id'],'text':detected[i]['text'],'page':detected[i]['page']}]}
            r=client.post('/summarizer/study/exams/jobs',json=payload);r.raise_for_status();job=r.json()
            events=[]
            with client.stream('GET',f"/summarizer/jobs/{job['id']}/events") as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:events.append(json.loads(line))
            row=next((e for e in events if e['type']=='question'),{})
            report['results'].append({'id':case['id'],**score(case,row),'seconds':round(time.perf_counter()-start,2),'status':row.get('status'),'run_id':job.get('run_id'),'answer':row.get('answer'),'source_pages':[s['page'] for s in row.get('sources',[])],'wrong_source_document':any(s['pdf_id']!=docs[0]['id'] for s in row.get('sources',[]))})
            (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:report['results'][-1][k] for k in ['id','correct','retrieved_expected_page','seconds']}),flush=True)
        results=report['results'];retrieval=[r['retrieved_expected_page'] for r in results if r['retrieved_expected_page'] is not None]
        report['summary']={'cases':len(results),'correct':sum(r['correct'] for r in results),'retrieval_hits':sum(retrieval),'retrieval_cases':len(retrieval),'citation_hits':sum(r['cited_expected_page'] is True for r in results),'citation_cases':len(retrieval),'language_matches':sum(r['language_matches'] for r in results),'median_seconds':statistics.median(r['seconds'] for r in results),'wrong_source_document':any(r['wrong_source_document'] for r in results)}
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report['summary']))
if __name__=='__main__':main()
