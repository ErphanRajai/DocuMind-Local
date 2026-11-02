import asyncio
import logging
import os
import time
import uuid
from typing import List, Tuple, Union

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    Fusion,
    FusionQuery,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from .llm_service import LLMService

logger = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "http://localhost:6333")
COLLECTION_NAME = os.getenv('DOCUMIND_QDRANT_COLLECTION', 'pdf_chunks')
DENSE_VECTOR_DIM = int(os.getenv("EMBED_VECTOR_DIM", "768"))

LOCAL_INDEX_PATH = os.getenv('DOCUMIND_QDRANT_LOCAL_PATH')
qdrant_client = QdrantClient(path=LOCAL_INDEX_PATH) if LOCAL_INDEX_PATH else QdrantClient(url=QDRANT_HOST)
client = qdrant_client

# Local CPU BM25 model via ONNX runtime
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25", cache_dir=os.getenv('DOCUMIND_RERANK_CACHE'), local_files_only=os.getenv('DOCUMIND_LOCAL_ONLY') == '1')


def init_qdrant_collection():
    """Initializes dual named-vector (dense + sparse) collection if not present."""
    try:
        collections = qdrant_client.get_collections().collections
        collection_names = [col.name for col in collections]

        if COLLECTION_NAME not in collection_names:
            logger.info("Initializing Hybrid Qdrant collection '%s'...", COLLECTION_NAME)
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "dense": VectorParams(size=DENSE_VECTOR_DIM, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False)
                    )
                },
            )
    except Exception:
        logger.exception("Failed to initialize hybrid Qdrant collection")
        raise


init_vector_db = init_qdrant_collection


async def store_chunks_in_qdrant(pdf_id: int, chunks: List[str], filename: str = "", page_numbers=None):
    if not chunks:
        return
    if page_numbers is not None and len(page_numbers) != len(chunks):
        raise ValueError("Every chunk must have a page number")
    version = 1 if page_numbers is not None else 0

    # Keep CPU-bound sparse encoding off the API event loop and batch dense
    # requests to avoid one HTTP round trip per chunk on current Ollama builds.
    sparse_embeddings, dense_embeddings = await asyncio.gather(
        asyncio.to_thread(lambda: list(sparse_model.embed(chunks))),
        LLMService.get_embeddings(chunks),
    )

    # 3. Assemble dual-vector point structs
    points = []
    for idx, (chunk, dense_vec, sparse_vec) in enumerate(
        zip(chunks, dense_embeddings, sparse_embeddings)
    ):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"documind:{pdf_id}:v{version}:{idx}"))
        points.append(
            PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vec,
                    "sparse": SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
                payload={
                    "pdf_id": int(pdf_id),
                    "filename": filename,
                    "chunk_index": idx,
                    "text": chunk,
                    "page_number": page_numbers[idx] if page_numbers is not None else None,
                    "source_version": version,
                },
            )
        )

    # 4. Bulk upsert to Qdrant
    if points:
        batch_size = 50
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await asyncio.to_thread(
                qdrant_client.upsert,
                collection_name=COLLECTION_NAME,
                points=batch,
                wait=True,
            )
        if version == 1:
            # Remove only this document's old, unlocated chunks after the new
            # index is fully written. Other documents and their IDs stay intact.
            await asyncio.to_thread(qdrant_client.delete, collection_name=COLLECTION_NAME,
                points_selector=models.FilterSelector(filter=models.Filter(
                    must=[models.FieldCondition(key="pdf_id", match=models.MatchValue(value=int(pdf_id)))],
                    should=[models.Filter(must_not=[models.FieldCondition(key="source_version", match=models.MatchValue(value=1))]),
                            models.FieldCondition(key="chunk_index", range=models.Range(gte=len(chunks)))],
                )), wait=True)


async def search_page_sources(pdf_ids, query_text, per_document=3):
    """Keep the document/page payload; reserve results for every selected PDF."""
    started = time.perf_counter()
    if LOCAL_INDEX_PATH or COLLECTION_NAME != 'pdf_chunks':
        # A separate embedded index can rebuild selected documents from durable
        # page text. Never open Docker's incompatible storage files directly.
        from .documents import read_pages, read_documents
        for pdf_id in pdf_ids:
            condition = models.Filter(must=[models.FieldCondition(key='pdf_id', match=models.MatchValue(value=int(pdf_id)))])
            count = await asyncio.to_thread(qdrant_client.count, collection_name=COLLECTION_NAME, count_filter=condition, exact=True)
            if count.count == 0:
                pages = await asyncio.to_thread(read_pages, [pdf_id])
                records = await asyncio.to_thread(read_documents, [pdf_id])
                from .pdf_processor import PDFProcessorService
                chunks, numbers = [], []
                for page in pages:
                    items = PDFProcessorService.structured_chunks(page['text'])
                    chunks.extend(items); numbers.extend([page['page']] * len(items))
                if chunks: await store_chunks_in_qdrant(pdf_id, chunks, records[0]['filename'] if records else '', numbers)
    dense, sparse_list = await asyncio.gather(LLMService.get_embedding(query_text),
        asyncio.to_thread(lambda: list(sparse_model.embed([query_text]))))
    sparse = sparse_list[0]

    async def query(pdf_id):
        condition = models.Filter(must=[
            models.FieldCondition(key="pdf_id", match=models.MatchValue(value=int(pdf_id))),
            models.FieldCondition(key="source_version", match=models.MatchValue(value=1)),
        ])
        result = await asyncio.to_thread(qdrant_client.query_points,
            collection_name=COLLECTION_NAME,
            prefetch=[Prefetch(query=dense, using="dense", filter=condition, limit=per_document * 4),
                Prefetch(query=SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()),
                         using="sparse", filter=condition, limit=per_document * 4)],
            query=FusionQuery(fusion=Fusion.RRF), query_filter=condition, limit=per_document * 2)
        # Several adjacent chunks can belong to the same page. Combine those
        # without letting one page crowd every other source out of the prompt.
        pages = {}
        for hit in result.points:
            payload = hit.payload or {}
            page = payload.get("page_number")
            if type(page) is not int or page < 1 or not payload.get("text"):
                continue
            if page not in pages:
                if len(pages) >= per_document:
                    continue
                pages[page] = {"pdf_id": int(pdf_id), "page": page, "text": "", "score": float(hit.score)}
            pages[page]["text"] += ("\n\n" if pages[page]["text"] else "") + payload["text"]
        return list(pages.values())

    results = await asyncio.gather(*(query(pdf_id) for pdf_id in pdf_ids))
    return [source for group in results for source in group], (time.perf_counter() - started) * 1000


async def search_chunks_in_qdrant_with_scores(
    pdf_ids: Union[int, List[int]], query_text: str, limit: int = 3
) -> Tuple[List[str], List[float], float]:
    """
    Executes hybrid retrieval combining dense semantic search + BM25 sparse search
    fused with Reciprocal Rank Fusion (RRF) across single or multiple PDF IDs.
    """
    t0 = time.perf_counter()

    if isinstance(pdf_ids, int):
        target_ids = [pdf_ids]
    else:
        target_ids = [int(p) for p in pdf_ids if p is not None]

    if not target_ids:
        return [], [], 0.0

    # Generate dense query embedding
    query_dense = await LLMService.get_embedding(query_text)

    # Generate sparse query embedding
    sparse_emb_generator = sparse_model.embed([query_text])
    query_sparse = await asyncio.to_thread(lambda: next(sparse_emb_generator))

    if len(target_ids) == 1:
        filter_condition = models.Filter(
            must=[models.FieldCondition(key="pdf_id", match=models.MatchValue(value=target_ids[0]))]
        )
    else:
        filter_condition = models.Filter(
            must=[models.FieldCondition(key="pdf_id", match=models.MatchAny(any=target_ids))]
        )

    # Hybrid Prefetch + Reciprocal Rank Fusion query
    results = await asyncio.to_thread(
        qdrant_client.query_points,
        collection_name=COLLECTION_NAME,
        prefetch=[
            Prefetch(
                query=query_dense,
                using="dense",
                filter=filter_condition,
                limit=limit * 3,
            ),
            Prefetch(
                query=SparseVector(
                    indices=query_sparse.indices.tolist(),
                    values=query_sparse.values.tolist(),
                ),
                using="sparse",
                filter=filter_condition,
                limit=limit * 3,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
    )
    t_done = time.perf_counter()

    chunks = [hit.payload.get("text", "") for hit in results.points]
    scores = [float(hit.score) for hit in results.points]
    retrieval_latency_ms = (t_done - t0) * 1000.0

    return chunks, scores, retrieval_latency_ms
