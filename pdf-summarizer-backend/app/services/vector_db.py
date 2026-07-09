from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
import httpx
import os
import uuid

client = AsyncQdrantClient(host="qdrant_service", port=6333)

COLLECTION_NAME = "documind_chunks"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama_service:11434")

async def init_vector_db():
    collections = await client.get_collections()
    exists = any(col.name == COLLECTION_NAME for col in collections.collections)

    if not exists:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
        )
        print(f"Collection {COLLECTION_NAME} created successfully")
    else:
        print(f"Collection {COLLECTION_NAME} already exists")

async def get_embedding(text: str) -> list[float]:
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    payload = {
        "model": "nomic-embed-text",
        "prompt": text
    }
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.post(url, json=payload)
        response.raise_for_status()
        return response.json()["embedding"]
    
async def store_chunks_in_qdrant(pdf_id: int, chunks: list[str]):
    await init_vector_db()
    points = []

    for idx, chunk_text in enumerate(chunks):
        vector = await get_embedding(chunk_text)
        point_id = str(uuid.uuid4())
        point = models.PointStruct(
            id=point_id,
            vector=vector,
            payload={"pdf_id": pdf_id, "text": chunk_text}
        )
        points.append(point)
        
    await client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    print(f"Successfully stored {len(points)} chunks for PDF ID {pdf_id} in Qdrant.")

async def search_chunks_in_qdrant(pdf_id: int, query_text: str, limit: int = 3) -> list[str]:
    try:
        query_vector = await get_embedding(query_text)
        search_results = await client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="pdf_id",
                        match=models.MatchValue(value=pdf_id)
                    )
                ]
            ),
            limit=limit
        )

        retrieved_texts = [
            hit.payload["text"] 
            for hit in search_results.points 
            if hit.payload and "text" in hit.payload
        ]
        print(f"DEBUG RAG: Found {len(retrieved_texts)} chunks for PDF ID {pdf_id}")
        return retrieved_texts
    except Exception as e:
        print(f"CRITICAL ERROR in Qdrant Search: {str(e)}")
        return []