"""Bounded multi-query hybrid search, CPU cross-encoder reranking, neighbors."""
import asyncio
import os
import re
import threading
import time

from .vector_db import search_page_sources
from .documents import read_pages

_model = None
_lock = threading.Lock()


def subqueries(question, focus=''):
    parts = [part.strip() for part in re.split(r'\?\s+|;|\band then\b|\balso\b', question, flags=re.I) if len(part.strip()) >= 12]
    return list(dict.fromkeys(([f'{focus[:600]}\n{question}' if focus else question] + parts)))[:3]


def rerank(question, hits):
    global _model
    # One CPU model, lazy loaded; failure is explicit in telemetry with RRF fallback.
    with _lock:
        if _model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            _model = TextCrossEncoder(model_name='Xenova/ms-marco-MiniLM-L-6-v2', threads=2,
                                     cache_dir=os.getenv('DOCUMIND_RERANK_CACHE', None), local_files_only=os.getenv('DOCUMIND_LOCAL_ONLY') == '1')
        scores = list(_model.rerank(question[:2000], [hit['text'][:3500] for hit in hits]))
    return sorted([{**hit, 'rerank_score': float(score)} for hit, score in zip(hits, scores)], key=lambda h: h['rerank_score'], reverse=True)


async def retrieve(pdf_ids, question, focus='', use_reranker=True):
    start = time.perf_counter()
    queries = subqueries(question, focus)
    groups = await asyncio.gather(*(search_page_sources(pdf_ids, query, per_document=6) for query in queries))
    unique = {}
    for hits, _ in groups:
        for hit in hits:
            key = (hit['pdf_id'], hit['page'])
            if key not in unique or len(hit['text']) > len(unique[key]['text']): unique[key] = hit
    hits = list(unique.values())[:36]
    status = 'disabled'
    if re.search('[\u0600-\u06ff\u4e00-\u9fff]', question):
        status = 'multilingual hybrid; English-only reranker skipped'
    elif use_reranker and hits:
        try:
            hits = await asyncio.wait_for(asyncio.to_thread(rerank, question, hits), timeout=60)
            status = 'cross-encoder'
        except Exception:
            status = 'unavailable; hybrid ranking retained'
    # Reserve one result per selected document before filling the global budget.
    selected = []
    for pdf_id in pdf_ids:
        match = next((h for h in hits if h['pdf_id'] == pdf_id), None)
        if match: selected.append(match)
    for hit in hits:
        if hit not in selected and len(selected) < 6: selected.append(hit)
    pages = await asyncio.to_thread(read_pages, pdf_ids)
    lookup = {(p['pdf_id'], p['page']): p for p in pages}
    for hit in list(selected)[:2]:
        # Neighbor expansion preserves a definition/example continued on the next page.
        neighbor = lookup.get((hit['pdf_id'], hit['page'] + 1))
        if neighbor and neighbor['text'].strip() and not any(h['pdf_id'] == neighbor['pdf_id'] and h['page'] == neighbor['page'] for h in selected):
            selected.append({**neighbor, 'score': 0.0, 'text': neighbor['text'][:3500]})
    return selected, {'retrieval_ms': round((time.perf_counter() - start) * 1000, 1), 'search_queries': len(queries),
                      'candidates': len(hits), 'reranker': status, 'source_notice': 'Retrieved evidence supports document claims; calculated results are separate. Search scores are not confidence probabilities.'}
