"""Review every text segment with bounded prompts and content-addressed caching."""
import asyncio
import hashlib
import json
import re

from ..models import ReviewCache
from . import documents
from .citations import GROUNDED_SYSTEM, bind_sources, citation_warning, check_quotes
from .errors import GenerationError
from .llm_service import LLMService
from .pdf_processor import PDFProcessorService
from .context_budget import TokenCounter
from .languages import language_instruction

REVIEW_VERSION = "complete-review-2"


def segment_text(text):
    counter = TokenCounter()
    remaining = text.strip()
    while remaining:
        segment = counter.prefix(remaining, 1800)
        yield segment
        if len(segment) == len(remaining):
            return
        remaining = remaining[max(1, len(segment) - min(120, len(segment) // 4)):]


def cache_read(key):
    with documents.SessionLocal() as db:
        row = db.get(ReviewCache, key)
        return json.loads(row.payload) if row else None


def cache_write(key, value):
    with documents.SessionLocal() as db:
        db.merge(ReviewCache(key=key, payload=json.dumps(value)))
        db.commit()
    from .study_store import maintain_cache
    maintain_cache()


def review_key(source, settings, directive):
    data = {"version": REVIEW_VERSION, "source": source, "settings": settings, "directive": directive}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


async def review_events(payload, records, event):
    pages = await asyncio.to_thread(documents.read_pages, payload.pdf_ids)
    sources = bind_sources([page for page in pages if page["text"].strip()], records)
    if not sources:
        raise GenerationError("No readable pages are available for a complete review.")
    # Character cap deliberately fits even the conservative UTF-8 counter for
    # common text. prepare_prompt must preserve the entire segment or fail.
    segments = [(source, text) for source in sources for text in segment_text(source["text"])]
    if len(segments) > 600:
        raise GenerationError("This complete review exceeds the 600-segment local limit. Split the PDF into smaller documents.")
    settings = {key: getattr(payload, key) for key in ("model", "provider", "api_base_url", "answer_length", "answer_language")}
    # Scope private-provider cache entries without storing the credential.
    settings["account"] = hashlib.sha256((payload.api_key or "").encode()).hexdigest()
    directive = payload.custom_prompt or "Extract the purpose, key facts, decisions, contradictions and limitations."
    results, cache_hits, quote_checks = [], 0, []
    yield event("metadata", sources=[{**{k: s[k] for k in ("id", "pdf_id", "page", "filename")}, "excerpt": s["text"]} for s in sources],
                source_notice="Complete review processes every readable page in segments. Blank pages and extraction warnings remain visible. Individual findings are below; this does not guarantee perfect interpretation.")
    for index, (source, text) in enumerate(segments):
        yield event("status", phase="reviewing", message=f"Reviewing segment {index + 1} of {len(segments)} · PDF page {source['page']}",
                    completed=index, total=len(segments))
        # A one-excerpt prompt always uses S1 locally. Only after validating it
        # do we map that marker onto this review's stable, global page ID.
        segment_source = {**source, "id": "S1", "title": f"[S1] {source['filename']} — PDF page {source['page']}", "text": text}
        key = review_key({**source, "text": text}, settings, directive)
        result = await asyncio.to_thread(cache_read, key)
        if result is None:
            plan = await LLMService.prepare_prompt(GROUNDED_SYSTEM + ' ' + language_instruction(payload.answer_language, payload.custom_prompt or text),
                directive + " Report only this segment's findings in at most five short bullets. "
                "Use your own words without quotation marks, headings or introductions. "
                "End each factual bullet with [S1], the only source in this prompt. "
                "If there are no substantive findings, say so briefly.",
                sources=[segment_source], model=payload.model, provider=payload.provider, answer_length=payload.answer_length)
            if plan.metadata["excerpts_shortened"]:
                raise GenerationError("A review segment exceeds the model context. A complete review was not produced.")
            answer, telemetry = "", {}
            async for token in LLMService.stream_messages(plan.messages, model=payload.model, provider=payload.provider,
                    api_base_url=payload.api_base_url, api_key=payload.api_key, answer_length=payload.answer_length, telemetry=telemetry):
                answer += token
            if not answer.strip() or telemetry.get("done_reason") == "length" or citation_warning(answer, [segment_source]) == "invalid":
                raise GenerationError("A review segment was empty, truncated, or contained an invalid citation. Retry to resume cached segments.")
            checks = check_quotes(answer, [{**segment_source, "excerpt": text}])
            if any(not check["verified"] for check in checks):
                raise GenerationError("A review segment contained an unverified quote. Retry this review.")
            answer = re.sub(r"\[S1\]", f"[{source['id']}]", answer)
            for check in checks:
                check["sources"] = [source["id"] if key == "S1" else key for key in check["sources"]]
            result = {"answer": answer, "checks": checks}
            await asyncio.to_thread(cache_write, key, result)
        else:
            cache_hits += 1
        results.append(result["answer"])
        quote_checks.extend(result["checks"])
        # Emit each segment, rather than squeeze a long document's findings into
        # one final 8K prompt and silently discard intermediate evidence.
        heading = f"\n\n### {source['filename']} · PDF page {source['page']}\n\n"
        yield event("text", content=heading + result["answer"])
    yield event("done", metrics={"review_mode": "complete", "pages_reviewed": len(sources), "segments_reviewed": len(segments),
        "cache_hits": cache_hits, "quote_checks": quote_checks, "warnings": [r["warning_message"] for r in records if r["warning_message"]],
        "citation_warning": "Check the linked evidence: citation locations and exact quotes are checked; paraphrased claims are not automatically verified."})
