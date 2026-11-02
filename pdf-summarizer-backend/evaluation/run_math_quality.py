"""Known-answer tool benchmark; no private PDFs or model accuracy claims.

Run: python evaluation/run_math_quality.py --output ../output/math-quality.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.math_engine import calculate

# Fixed expected answers are independent of the calculator implementation.
CASES = [
    ({'expression':'x+2=5'},'{3}'),({'expression':'3*x=12'},'{4}'),({'expression':'2*x-7=1'},'{4}'),
    ({'expression':'x^2-5*x+6=0'},'{2, 3}'),({'expression':'x^2-9=0'},'{-3, 3}'),
    ({'expression':'x^2+1=0'},'EmptySet'),({'expression':'x^2+1=0','domain':'complex'},'{-I, I}'),
    ({'expression':'x^3-x=0'},'{-1, 0, 1}'),({'expression':'sqrt(x)=4'},'{16}'),
    ({'expression':'x/3=2'},'{6}'),({'expression':'x-0.25=0'},'{1/4}'),
    ({'expression':'\\frac{x}{2}=4'},'{8}'),({'expression':'2x=6'},'{3}'),
    ({'operation':'differentiate','expression':'x^2'},'2*x'),
    ({'operation':'differentiate','expression':'x^3'},'3*x**2'),
    ({'operation':'differentiate','expression':'sin(x)'},'cos(x)'),
    ({'operation':'differentiate','expression':'cos(x)'},'-sin(x)'),
    ({'operation':'differentiate','expression':'exp(x)'},'exp(x)'),
    ({'operation':'differentiate','expression':'log(x)'},'1/x'),
    ({'operation':'differentiate','expression':'7'},'0'),
    ({'operation':'integrate','expression':'2*x'},'x**2'),
    ({'operation':'integrate','expression':'3*x^2'},'x**3'),
    ({'operation':'integrate','expression':'cos(x)'},'sin(x)'),
    ({'operation':'integrate','expression':'sin(x)'},'-cos(x)'),
    ({'operation':'integrate','expression':'x','lower':'0','upper':'2'},'2'),
    ({'operation':'factor','expression':'x^2-1'},'(x - 1)*(x + 1)'),
    ({'operation':'factor','expression':'x^2+2*x+1'},'(x + 1)**2'),
    ({'operation':'factor','expression':'x^2-4'},'(x - 2)*(x + 2)'),
    ({'operation':'simplify','expression':'x+x'},'2*x'),
    ({'operation':'simplify','expression':'sin(x)^2+cos(x)^2'},'1'),
    ({'operation':'simplify','expression':'2+3*4'},'14'),
    ({'operation':'numeric','expression':'1/4'},'0.250000000000'),
    ({'operation':'numeric','expression':'2^3'},'8.00000000000'),
    ({'operation':'units','magnitude':1,'from_unit':'m','to_unit':'cm'},'100 cm'),
    ({'operation':'units','magnitude':36,'from_unit':'km/h','to_unit':'m/s'},'10 m/s'),
    ({'operation':'units','magnitude':2,'from_unit':'kg','to_unit':'g'},'2000 g'),
    ({'operation':'matrix','matrix':[[1,2],[3,4]]},'-2'),
    ({'operation':'matrix','matrix':[[1,0],[0,1]]},'1'),
    ({'operation':'check','expression':'x+x','expected':'2*x'},'0'),
    ({'operation':'check','expression':'x+1','expected':'x'},'1'),
    ({'variables':['x','y'],'equations':['x+y=5','x-y=1']},'{(3, 2)}'),
]
REJECT = ['__import__("os")','x.__class__','open("file")','x[0]','[x for x in range(3)]','1/0','sin(x,y)','x**x','unknown+1']


def run():
    rows=[]
    for data,expected in CASES:
        started=time.perf_counter()
        try:
            result=calculate(data)
            row={'input':data,'expected':expected,'actual':result['result'],'passed':result['result']==expected,'checks':result['checks']}
        except Exception as exc: row={'input':data,'passed':False,'error':str(exc)}
        rows.append({**row,'ms':round((time.perf_counter()-started)*1000,2)})
    for value in REJECT:
        try: calculate({'expression':value}); passed=False
        except Exception: passed=True
        rows.append({'input':value,'expected':'reject','passed':passed})
    return {'passed':sum(row['passed'] for row in rows),'total':len(rows),'cases':rows,
            'limitations':'Synthetic exact-answer tool checks. Not a benchmark of free-form model interpretation, handwriting, arbitrary exams or proof correctness.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='../output/math-quality.json');args=parser.parse_args()
    report=run();Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f"Math benchmark: {report['passed']}/{report['total']} passed")
    sys.exit(0 if report['passed']==report['total'] else 1)
