"""Compare the standard parser with the optional Docling parser on YOUR fixture.

Print only coverage/character/timing diagnostics, never private extracted text.
Run: python evaluation/compare_extraction.py path/to/public-fixture.pdf
"""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.pdf_processor import PDFProcessorService
from app.services.layout_extraction import extract_with_docling


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('pdf');parser.add_argument('--docling',action='store_true');args=parser.parse_args()
    results=[]
    engines=[('standard',PDFProcessorService.extract_document)]+([('docling',extract_with_docling)] if args.docling else [])
    for name,extract in engines:
        started=time.perf_counter()
        try:
            result=extract(args.pdf)
            results.append({'engine':name,'pages':len(result.pages),'readable_pages':sum(bool(p.text.strip()) for p in result.pages),'characters':len(result.text),'warnings':len(result.warnings),'ms':round((time.perf_counter()-started)*1000)})
        except Exception as exc:results.append({'engine':name,'error':str(exc)})
    print(json.dumps(results,indent=2))
