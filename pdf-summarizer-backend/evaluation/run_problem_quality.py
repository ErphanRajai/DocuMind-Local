"""Real model interpretation + calculator evaluation on synthetic problems.

Use --models llama3.2:3b qwen2.5-coder:7b to compare installed models serially.
No model is downloaded or changed as the app's default by this script.
"""
import argparse
import json
import time
from pathlib import Path
import httpx

CASES=[
    ('quadratic','Find all real x satisfying x^2 - 5*x + 6 = 0.','{2, 3}'),
    ('derivative','Differentiate x^3 with respect to x.','3*x**2'),
    ('integral','Find the indefinite integral of 2*x with respect to x.','x**2'),
    ('system','Solve x+y=5 and x-y=1 for real x and y.','{(3, 2)}'),
    ('units','Convert 36 km/h to m/s.','10 m/s'),
    ('matrix','Find the determinant of the matrix [[1,2],[3,4]].','-2'),
    ('real_domain','Solve x^2+1=0 over real numbers.','EmptySet'),
    ('missing','How far did the object travel? Neither its speed nor its travel time is provided.',None),
]
HOLDOUT=[
    ('linear','Find the real number x such that 5*x+10=0.','{-2}'),
    ('power_rule','Find the derivative of 5*t^4 with respect to t.','20*t**3'),
    ('antiderivative','Find an indefinite integral of 3*z^2 with respect to z.','z**3'),
    ('new_system','Solve 2*x+y=8 and x-y=1 for real x and y.','{(3, 2)}'),
    ('new_units','Convert 90 km/h into m/s.','25 m/s'),
    ('new_matrix','Calculate the determinant of [[2,1],[1,2]].','3'),
    ('complex_domain','Find all complex roots of x^2+4=0.','{-2*I, 2*I}'),
    ('word_problem','A rectangular garden has perimeter 30 metres and width 5 metres. Find its length in metres.','{10}'),
    ('ambiguous','A projectile is launched at 20 m/s. Find its horizontal range; the launch angle is not specified.',None),
]


def assess(expected,metadata,terminal):
    if terminal!='done':return False
    if expected is None:return bool((metadata.get('interpretation') or {}).get('missing')) and not metadata.get('math')
    return (metadata.get('math') or {}).get('result')==expected


def run(base,models,cases=CASES):
    reports=[]
    with httpx.Client(base_url=base,timeout=240) as client:
        # An unavailable service is an infrastructure failure, not model accuracy.
        response=client.get('/healthz');response.raise_for_status()
        for model in models:
            rows=[]
            for name,question,expected in cases:
                started=time.perf_counter();metadata={};terminal='error';text='';first=None
                try:
                    response=client.post('/summarizer/study/jobs',json={'question':question,'model':model,'task':'problem','mode':'explain','approve_calculation':True})
                    response.raise_for_status();key=response.json()['id']
                    with client.stream('GET',f'/summarizer/jobs/{key}/events') as stream:
                        stream.raise_for_status()
                        for line in stream.iter_lines():
                            if not line:continue
                            event=json.loads(line)
                            if event['type']=='metadata':metadata.update(event)
                            if event['type']=='text':
                                if first is None:first=round((time.perf_counter()-started)*1000,1)
                                text+=event.get('content','')
                            if event['type'] in {'done','error','cancelled'}:
                                terminal=event['type'];metadata.update(event.get('metrics',{}))
                                if terminal=='error':text=event.get('message','')
                except Exception as exc:text=str(exc)
                rows.append({'case':name,'expected':expected,'actual':(metadata.get('math') or {}).get('result'),
                    'passed':assess(expected,metadata,terminal),'terminal':terminal,'first_text_ms':first,
                    'total_ms':round((time.perf_counter()-started)*1000,1),'interpretation':metadata.get('interpretation'),
                    'model_metrics':metadata.get('interpretation_metrics',{}), 'answer':text})
                print(model,name,'PASS' if rows[-1]['passed'] else 'FAIL',flush=True)
            reports.append({'model':model,'passed':sum(row['passed'] for row in rows),'total':len(rows),'cases':rows})
    return {'models':reports,'limitations':'Eight synthetic problems, fixed exact result checks. Not a general exam accuracy score; explanation quality, OCR and arbitrary proofs require separate review.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8888');parser.add_argument('--models',nargs='+',default=['llama3.2:3b']);parser.add_argument('--suite',choices=['regression','holdout'],default='regression');parser.add_argument('--output',default='../output/problem-quality.json');args=parser.parse_args()
    report=run(args.base,args.models,HOLDOUT if args.suite=='holdout' else CASES);report['suite']=args.suite;Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Report:',args.output)
