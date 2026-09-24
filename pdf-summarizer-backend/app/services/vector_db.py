import asyncio
import logging
import os
import time
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
COLLECTION_NAME = "pdf_chunks"
DENSE_VECTOR_DIM = int(os.getenv("EMBED_VECTOR_DIM", "768"))

qdrant_client = QdrantClient(url=QDRANT_HOST)
client = qdrant_client

# Local CPU BM25 model via ONNX runtime
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")


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
    except Exception as e:
        logger.error("Failed to initialize hybrid Qdrant collection: %s", str(e))


init_vector_db = init_qdrant_collection


async def store_chunks_in_qdrant(pdf_id: int, chunks: List[str], filename: str = ""):
    if not chunks:
        return

    # 1. Compute BM25 sparse embeddings
    sparse_embeddings = list(sparse_model.embed(chunks))

    # 2. Concurrently compute Ollama dense embeddings
    semaphore = asyncio.Semaphore(5)

    async def fetch_emb(chunk: str):
        async with semaphore:
            return await LLMService.get_embedding(chunk)

    dense_embeddings = await asyncio.gather(*(fetch_emb(c) for c in chunks))

    # 3. Assemble dual-vector point structs
    points = []
    for idx, (chunk, dense_vec, sparse_vec) in enumerate(
        zip(chunks, dense_embeddings, sparse_embeddings)
    ):
        point_id = int(f"{pdf_id}{idx:04d}")
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
                },
            )
        )

    # 4. Bulk upsert to Qdrant
    if points:
        batch_size = 50
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=batch)


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
    query_sparse = next(sparse_emb_generator)

    if len(target_ids) == 1:
        filter_condition = models.Filter(
            must=[models.FieldCondition(key="pdf_id", match=models.MatchValue(value=target_ids[0]))]
        )
    else:
        filter_condition = models.Filter(
            must=[models.FieldCondition(key="pdf_id", match=models.MatchAny(any=target_ids))]
        )

    # Hybrid Prefetch + Reciprocal Rank Fusion query
    results = qdrant_client.query_points(
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