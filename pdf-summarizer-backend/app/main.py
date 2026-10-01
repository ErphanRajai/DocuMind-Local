import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import summarizer
from .services.llm_service import LLMService
from .services.vector_db import (
    client as qdrant_client,
    init_vector_db,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQL tables
    await asyncio.to_thread(Base.metadata.create_all, bind=engine)
    # Compose starts the backend and Qdrant together; allow Qdrant time to accept requests.
    for attempt in range(30):
        try:
            await asyncio.to_thread(init_vector_db)
            break
        except Exception:
            if attempt == 29:
                raise
            logger.warning("Qdrant is not ready yet; retrying collection setup (%s/30)", attempt + 1)
            await asyncio.sleep(2)

    # Reuse local Ollama HTTP connections across requests.
    await LLMService.startup()
    try:
        yield
    finally:
        await LLMService.shutdown()


app = FastAPI(
    title="DocuMind Backend",
    version="1.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8501", "http://localhost:8501"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(summarizer.router)


@app.get("/healthz")
async def healthz():
    status = {"status": "healthy", "qdrant": "connected", "ollama": "connected"}

    # Check Qdrant without blocking other API requests.
    try:
        await asyncio.to_thread(qdrant_client.get_collections)
    except Exception as e:
        status["qdrant"] = f"unreachable: {str(e)}"
        status["status"] = "degraded"

    # 2. Check Ollama
    try:
        async with httpx.AsyncClient(timeout=3.0) as http_client:
            res = await http_client.get(LLMService.API_URL.rsplit("/api/", 1)[0])
        if res.status_code >= 400:
            raise RuntimeError(f"HTTP {res.status_code}")
    except Exception as e:
        status["ollama"] = f"unreachable: {str(e)}"
        status["status"] = "degraded"

    return status
