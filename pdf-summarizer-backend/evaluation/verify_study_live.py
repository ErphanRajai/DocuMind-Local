"""Live verification uses ONLY fixtures created by seed_study_demo.py."""
import base64
import json
import re
import time
from pathlib import Path
import httpx


def job(client,payload):
    response=client.post('/summarizer/study/jobs',json=payload);response.raise_for_status();key=response.json()['id']
    events=[]
    with client.stream('GET',f'/summarizer/jobs/{key}/events') as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line:events.append(json.loads(line))
    return key,events


if __name__=='__main__':
    output=Path(__file__).resolve().parents[2]/'output';demo=json.loads((output/'study-demo.json').read_text());pdf_id=demo['pdf_id'];report={}
    with httpx.Client(base_url='http://127.0.0.1:8888',timeout=240) as client:
        record=client.get(f'/summarizer/documents/{pdf_id}').json()
        assert record['filename']=='documind-study-examples.pdf','Refusing to inspect a non-synthetic document.'
        report['health']=client.get('/healthz').json()
        geometry=client.get(f'/summarizer/documents/{pdf_id}/pages/2/text',params={'search':'power rule'}).json()
        report['pdf_geometry']={'words':len(geometry['words']),'highlights':len(geometry['highlights'])}
        assert geometry['words'] and geometry['highlights']
        paper=client.get(f'/summarizer/study/papers/{pdf_id}').json()
        report['paper']={'questions':len(paper['questions']),'marks':[q['marks'] for q in paper['questions']]}
        assert len(paper['questions'])==4
        image=(output/'study-diagram.png').read_bytes()
        ocr=client.post('/summarizer/study/transcribe',files={'image':('diagram.png',image,'image/png')});ocr.raise_for_status()
        report['ocr']={'text':ocr.json()['text'],'verified':ocr.json()['verified']}
        vision=client.post('/summarizer/study/vision',json={'model':'qwen3-vl:2b-instruct','image_base64':base64.b64encode(image).decode()});vision.raise_for_status()
        text=vision.json()['text'];report['vision']={'text':text,'verified':vision.json()['verified'],'labels_present':all(word in text.lower() for word in ['10','5','rectangle'])}
        assert report['vision']['labels_present']
        _,events=job(client,{'question':'Find all real x satisfying x^2-5*x+6=0.','model':'llama3.2:3b','task':'problem'})
        metrics=next(row['metrics'] for row in events if row['type']=='done')
        report['interpretation_review']=metrics.get('awaiting_interpretation') is True
        assert report['interpretation_review'] and not any(row.get('math') for row in events)
        _,events=job(client,{'question':'What are the roots in the worked quadratic example? Cite the page.','pdf_ids':[pdf_id],'model':'llama3.2:3b','task':'notes'})
        assert events[-1]['type']=='done',events[-1]
        answer=''.join(row.get('content','') for row in events)
        report['sourced_answer']={'answer':answer,'metrics':events[-1]['metrics']}
        assert re.search(r'\[S\d+\]',answer)
        _,events=job(client,{'question':'Consolidate the main algebra, calculus and unit-conversion findings.','pdf_ids':[pdf_id],'model':'llama3.2:3b','task':'synthesis'})
        assert events[-1]['type']=='done',events[-1]
        report['synthesis']=events[-1]['metrics'];assert report['synthesis']['pages_reviewed']==3
        response=client.post('/summarizer/study/jobs',json={'question':'Explain the notes as a long, detailed tutorial with many worked examples.','pdf_ids':[pdf_id],'task':'notes','model':'llama3.2:3b'})
        response.raise_for_status();key=response.json()['id']
        with client.stream('GET',f'/summarizer/jobs/{key}/events') as stream:
            for line in stream.iter_lines():
                if line and json.loads(line)['type']=='text':
                    report['cancellation']=client.post(f'/summarizer/jobs/{key}/cancel').json()['state'];break
        assert report['cancellation']=='cancelled'
    (output/'study-live.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'checks':'passed','paper_questions':report['paper']['questions'],'vision_labels':report['vision']['labels_present'],'pages_synthesized':report['synthesis']['pages_reviewed'],'cancelled':report['cancellation']}))
