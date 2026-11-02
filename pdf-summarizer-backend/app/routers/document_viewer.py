"""Small page viewer: render the original PDF, including scans and diagrams."""

import asyncio
import html

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response

from ..services.documents import document_file
from ..services.errors import PDFPageNotFound, PDFProcessingError, ProcessingBusyError
from ..services.pdf_executor import pdf_executor
from ..services.pdf_processor import PDFProcessorService

router = APIRouter(prefix="/summarizer/documents", tags=["Document sources"])
PRIVATE_HEADERS = {"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"}


@router.get('/{pdf_id}/pages/{number}/text')
async def page_text(pdf_id: int, number: int, search: str = Query('', max_length=150)):
    path, _ = await asyncio.to_thread(document_file, pdf_id)
    return await pdf_work(PDFProcessorService.page_geometry, path, number, search)


async def pdf_work(function, *args):
    try:
        return await pdf_executor.run(function, *args)
    except PDFPageNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except PDFProcessingError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ProcessingBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "2"}) from exc


@router.get("/{pdf_id}/file")
async def original_pdf(pdf_id: int):
    path, filename = await asyncio.to_thread(document_file, pdf_id)
    return FileResponse(path, media_type="application/pdf", filename=filename,
                        content_disposition_type="inline", headers=PRIVATE_HEADERS)


@router.get("/{pdf_id}/pages/{number}.png")
async def page_image(pdf_id: int, number: int):
    path, _ = await asyncio.to_thread(document_file, pdf_id)
    image = await pdf_work(PDFProcessorService.render_page, path, number)
    return Response(image, media_type="image/png", headers=PRIVATE_HEADERS)


@router.get("/{pdf_id}/view", response_class=HTMLResponse)
async def view_document(pdf_id: int, page: int = Query(1, ge=1)):
    path, filename = await asyncio.to_thread(document_file, pdf_id)
    count = await pdf_work(PDFProcessorService.page_count, path)
    if page > count:
        raise HTTPException(404, "That PDF page does not exist.")
    title = html.escape(filename)
    previous = f'<a href="?page={page - 1}" rel="prev">Previous page</a>' if page > 1 else '<span aria-disabled="true">Previous page</span>'
    following = f'<a href="?page={page + 1}" rel="next">Next page</a>' if page < count else '<span aria-disabled="true">Next page</span>'
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Page {page} · {title} · DocuMind</title>
<style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#f5f5f3;color:#24334a;font:16px/1.5 system-ui,sans-serif}}
header,main{{max-width:1000px;margin:auto;padding:20px 24px}}header{{display:flex;flex-wrap:wrap;gap:16px;align-items:center}}
.name{{flex:1;min-width:160px;overflow-wrap:anywhere}}h1{{font-size:18px;margin:0}}p{{margin:4px 0;color:#526077;font-size:14px}}
a{{color:#455888;text-underline-offset:3px}}nav{{display:flex;flex-wrap:wrap;gap:16px;align-items:center}}
a,input,button{{border-radius:6px}}a:focus-visible,input:focus-visible,button:focus-visible{{outline:3px solid #737fac;outline-offset:4px}}
nav a,nav span{{padding:8px 0}}span[aria-disabled]{{color:#777}}form{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
input,button{{font:inherit;padding:7px 10px;border:1px solid #b6bbc5;background:#fff;color:inherit}}input{{width:90px}}button{{cursor:pointer}}
img{{display:block;width:100%;height:auto;background:#fff;border:1px solid #dce0e7}}main{{padding-top:0}}
@media(max-width:600px){{header,main{{padding:16px}}header{{gap:12px}}nav{{width:100%;justify-content:space-between}}}}
</style></head><body><header><div class="name"><h1>{title}</h1><p>PDF page {page} of {count} · Original document</p></div>
<a href="file#page={page}">Open original PDF</a><nav aria-label="PDF pages">{previous}
<form method="get"><label for="page">Page</label><input id="page" name="page" type="number" min="1" max="{count}" value="{page}" required><button type="submit">Go</button></form>
{following}</nav></header><main><img src="pages/{page}.png" alt="Original PDF page {page} of {title}"></main></body></html>''',
        headers={**PRIVATE_HEADERS, "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})
