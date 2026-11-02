"""Portable workspace archives: PDFs, page text, annotations and exam checkpoints.

Imports create new IDs, never overwrite existing work, never restore executable settings.
"""
import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path
from fastapi import HTTPException
from ..models import PDFDocument, PDFPage, StudyItem, WorkspaceRecord, ExamRun
from . import documents, study_store

LIMIT=500*1024*1024

def export_archive(key):
    with documents.SessionLocal() as db:
        w=db.get(WorkspaceRecord,key)
        if not w:raise HTTPException(404,'Workspace not found.')
        workspace=json.loads(w.payload)
        items=[{'kind':i.kind,'data':json.loads(i.payload)} for i in db.query(StudyItem).filter_by(workspace_id=key).all()]
        runs=[{'id':r.id,'data':json.loads(r.payload)} for r in db.query(ExamRun).filter_by(workspace_id=key).all()]
        ids=set()
        def collect(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k in {'pdf_id','exam_pdf_id'} and type(v) is int:ids.add(v)
                    elif k in {'pdf_ids','reference_pdf_ids'} and isinstance(v,list):ids.update(x for x in v if type(x) is int)
                    elif k=='documents' and isinstance(v,list):ids.update(x['id'] for x in v if isinstance(x,dict) and type(x.get('id')) is int)
                    collect(v)
            elif isinstance(value,list):
                for v in value:collect(v)
        collect([workspace,items,runs])
        manifest={'format':'documind-workspace-2','workspace':workspace,'items':items,'runs':runs,'documents':[]}
        output=io.BytesIO();total=0
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for pdf_id in sorted(ids):
                record=db.get(PDFDocument,pdf_id)
                if not record:raise HTTPException(409,'A referenced document was removed. Resolve missing references before making a complete backup.')
                path,_=documents.document_file(pdf_id)
                blob=Path(path).read_bytes();total+=len(blob)
                if total>LIMIT:raise HTTPException(413,'Split the workspace; archive content exceeds 500 MB.')
                member=f'pdfs/{pdf_id}.pdf';archive.writestr(member,blob)
                pages=[{'page':p.number,'label':p.label,'text':p.text} for p in db.query(PDFPage).filter_by(pdf_id=pdf_id).order_by(PDFPage.number).all()]
                manifest['documents'].append({'id':pdf_id,'filename':record.filename,'member':member,'sha256':hashlib.sha256(blob).hexdigest(),'pages':pages})
            archive.writestr('manifest.json',study_store.encoded(manifest,30_000_000))
        data=output.getvalue()
        if len(data)>200*1024*1024:raise HTTPException(413,'Split this workspace; its compressed archive exceeds the 200 MB restore limit.')
        return data

def prepare_archive(blob):
    staged=[]
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos=archive.infolist()
            if len(infos)>502 or sum(i.file_size for i in infos)>LIMIT:raise ValueError('Archive exceeds the file or expanded-size limit.')
            names=[i.filename for i in infos]
            if len(names)!=len(set(names)):raise ValueError('Duplicate archive members are not allowed.')
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size>30_000_000:raise ValueError('Missing or oversized archive manifest.')
            manifest=json.loads(archive.read('manifest.json'))
            study_store.encoded(manifest,30_000_000)
            if manifest.get('format')!='documind-workspace-2':raise ValueError('Use a DocuMind complete workspace ZIP.')
            docs=manifest.get('documents',[])
            if not isinstance(docs,list) or len(docs)>500:raise ValueError('Invalid document list.')
            allowed={'manifest.json'};seen=set()
            root=Path(documents.UPLOAD_DIR);root.mkdir(parents=True,exist_ok=True)
            for d in docs:
                old=d['id'];member=f'pdfs/{old}.pdf'
                if type(old) is not int or old<1 or old in seen or d['member']!=member:raise ValueError('Invalid document ID/member.')
                seen.add(old);allowed.add(member)
                if not isinstance(d['filename'],str) or len(d['filename'])>255 or any(c in d['filename'] for c in '\\ /\0'.replace(' ','')) or not d['filename'].lower().endswith('.pdf'):raise ValueError('Invalid PDF display name.')
                data=archive.read(member)
                if len(data)>documents.MAX_UPLOAD_BYTES or hashlib.sha256(data).hexdigest()!=d['sha256']:raise ValueError('PDF checksum mismatch or oversized PDF.')
                pages=d['pages']
                if len(pages)>5000 or [p['page'] for p in pages]!=list(range(1,len(pages)+1)) or any(not isinstance(p['text'],str) for p in pages):raise ValueError('Invalid saved page text.')
                path=root/(uuid.uuid4().hex+'.pdf')
                path.write_bytes(data);staged.append(str(path))
            if set(names)!=allowed:raise ValueError('Unexpected archive member; only listed PDFs and manifest are accepted.')
        return manifest,staged
    except Exception:
        documents._remove_staged(staged)
        raise

def commit_archive(manifest,staged):
    new_key=uuid.uuid4().hex
    mapping={};runmap={r['id']:uuid.uuid4().hex for r in manifest.get('runs',[])}
    def remap(value,key=''):
        if isinstance(value,dict):return {k:remap(v,k) for k,v in value.items()}
        if isinstance(value,list):return [remap(v,'pdf_id' if key in {'pdf_ids','reference_pdf_ids'} else key) for v in value]
        if type(value) is int and key in {'id','pdf_id','exam_pdf_id'}:return mapping.get(value,value)
        if isinstance(value,str) and value in runmap:return runmap[value]
        return value
    try:
        with documents.SessionLocal() as db:
            for d,path in zip(manifest['documents'],staged):
                record=PDFDocument(filename=d['filename'],file_path=path,status='completed',raw_text='\n\n'.join(p['text'] for p in d['pages']),page_count=len(d['pages']),source_version=1,warning_message='Restored from archive; search index rebuilds on first use.')
                db.add(record);db.flush();mapping[d['id']]=record.id
                db.add_all(PDFPage(pdf_id=record.id,number=p['page'],label=p.get('label'),text=p['text']) for p in d['pages'])
            workspace=remap(manifest['workspace']);workspace['id']=new_key;workspace['title']=str(workspace.get('title','Restored workspace'))[:230]+' (restored)'
            db.add(WorkspaceRecord(id=new_key,payload=study_store.encoded(workspace),revision=1))
            for item in manifest.get('items',[]):
                value=remap(item['data'])
                itemkey=f"exam-{value['run_id']}-{value['question_index']}" if item['kind']=='exam_answer' and 'run_id' in value and 'question_index' in value else uuid.uuid4().hex
                db.add(StudyItem(id=itemkey,workspace_id=new_key,kind=item['kind'],payload=study_store.encoded(value,150_000)))
            for run in manifest.get('runs',[]):
                value=remap(run['data']);value['request']['workspace_id']=new_key
                versions=[]
                for pdf_id in sorted(value['request']['reference_pdf_ids']):
                    r=db.get(PDFDocument,pdf_id);versions.append({'id':pdf_id,'sha256':hashlib.sha256((r.raw_text or '').encode()).hexdigest()})
                exam=value['request']['exam_pdf_id']
                # Match the canonical read_pages shape used by resume validation.
                d=next(d for d in manifest['documents'] if mapping[d['id']]==exam)
                pages=[{'pdf_id':exam,'page':p['page'],'label':p.get('label'),'text':p['text']} for p in d['pages']]
                versions.append({'id':exam,'sha256':hashlib.sha256(json.dumps(pages,sort_keys=True).encode()).hexdigest()});value['versions']=versions
                db.add(ExamRun(id=runmap[run['id']],workspace_id=new_key,payload=study_store.encoded(value,8_000_000),state='interrupted'))
            db.commit()
        return {'workspace_id':new_key,'documents':len(mapping),'notice':'Restored as a new workspace. Search indexes rebuild from saved page text on first use.'}
    except Exception:
        documents._remove_staged(staged)
        raise
