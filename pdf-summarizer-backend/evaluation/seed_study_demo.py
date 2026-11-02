"""Create public synthetic study fixtures and a real saved demo workspace."""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import fitz
import httpx
from PIL import Image, ImageDraw, ImageFont


def fixtures(output):
    output.mkdir(parents=True,exist_ok=True)
    pages=[
        ('Algebra, with the evidence kept close.',
         'Synthetic study notes for DocuMind verification.\n\n'
         'For a quadratic equation a*x^2+b*x+c=0, the quadratic formula is\nx=(-b +/- sqrt(b^2-4*a*c))/(2*a), with a nonzero.\n\n'
         'Example: x^2-5*x+6=0 factors as (x-2)*(x-3)=0.\nThe solutions are x=2 and x=3. Substitute each value to check it.\n\n'
         'Domain restrictions matter. Dividing x^2=x by x loses the root x=0.\nThe original equation has roots x=0 and x=1.'),
        ('Calculus and units.',
         'The power rule is d/dx(a*x^n)=a*n*x^(n-1).\nExample: the derivative of x^3 is 3*x^2.\n\n'
         'An indefinite integral includes an arbitrary constant C.\nThe integral of 2*x is x^2+C. Differentiating checks the result.\n\n'
         'One kilometre equals 1000 metres; one hour equals 3600 seconds.\nTherefore 36 km/h equals 10 m/s.\n\n'
         'For a rectangle, perimeter P=2*(length+width).\nIf P=30 m and width=5 m, then length=10 m.'),
        ('A short practice paper.',
         'Synthetic questions, not a real examination. Show your working.\n\n'
         'Question 1 Solve x^2-5*x+6=0 over the real numbers. [3 marks]\n(a) Factor the expression.\n(b) Check both roots.\n\n'
         'Question 2 Differentiate x^3 with respect to x. [2 marks]\n\n'
         'Question 3 Convert 36 km/h to m/s. [2 marks]\n\n'
         'Question 4 A rectangle has perimeter 30 m and width 5 m.\nFind its length. [3 marks]')]
    path=output/'documind-study-examples.pdf'
    with fitz.open() as pdf:
        for title,text in pages:
            page=pdf.new_page(width=595,height=842)
            page.insert_text((50,70),title,fontsize=20,color=(.07,.32,.23))
            page.insert_textbox(fitz.Rect(50,110,545,780),text,fontsize=12,lineheight=1.6)
        pdf.save(path)
    image=Image.new('RGB',(1000,650),'white');draw=ImageDraw.Draw(image)
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(font_path),32) if font_path.exists() else ImageFont.load_default(size=32)
    draw.text((55,40),'Find the perimeter of this rectangle.',font=font,fill='black')
    draw.rectangle((180,180,780,480),outline='black',width=4)
    draw.text((430,120),'10 m',font=font,fill='black');draw.text((800,305),'5 m',font=font,fill='black')
    draw.text((55,565),'Public synthetic diagram for testing DocuMind.',font=font,fill='black')
    image.save(output/'study-diagram.png')
    return path


def seed(base,output):
    path=fixtures(output)
    with httpx.Client(base_url=base,timeout=120) as client:
        response=client.post('/summarizer/upload',files={'files':(path.name,path.read_bytes(),'application/pdf')});response.raise_for_status();record=response.json()[0]
        for _ in range(60):
            record=client.get(f"/summarizer/documents/{record['id']}").json()
            if record['status'] in {'completed','partial'}:break
            if record['status']=='failed':raise RuntimeError(record['error_message'])
            time.sleep(1)
        else:raise RuntimeError('Synthetic document indexing did not finish.')
        workspace={'id':'study-demo-'+uuid.uuid4().hex[:8],'title':'Algebra & calculus','documents':[record],'messages':[],'updated':int(time.time()*1000)}
        response=client.put('/summarizer/workspaces/'+workspace['id'],json={'workspace':workspace});response.raise_for_status()
        result=client.post('/summarizer/study/solve',json={'expression':'x^2=x'});result.raise_for_status()
        note={'workspace_id':workspace['id'],'kind':'mistake','data':{'question':'Why does dividing by x lose a root?','answer':'For $x^2=x$, the original roots are $x=0$ and $x=1$. Dividing by $x$ requires $x\\ne0$ and loses the first root.','result':result.json(),'origin':'Public synthetic demo note','due':datetime.now(timezone.utc).isoformat()}}
        client.post('/summarizer/study/items',json=note).raise_for_status()
        client.post('/summarizer/study/practice',json={'workspace_id':workspace['id'],'topic':'quadratic','count':3}).raise_for_status()
        report={'workspace_id':workspace['id'],'pdf_id':record['id'],'frontend_url':'http://127.0.0.1:4317/study?workspace='+workspace['id']}
        (output/'study-demo.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8888');parser.add_argument('--output',default='../output');args=parser.parse_args();seed(args.base,Path(args.output))
