import asyncio
import json
import logging
import os
from typing import AsyncGenerator, List, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMService:
    CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:3b")
    EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
    API_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434/api/chat")
    EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://host.docker.internal:11434/api/embeddings")
    TAGS_URL = os.getenv("OLLAMA_TAGS_URL", "http://host.docker.internal:11434/api/tags")
    _http_client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def startup(cls) -> None:
        """Reuse HTTP connections to the local Ollama service across requests."""
        if cls._http_client is None or cls._http_client.is_closed:
            cls._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=20.0, read=60.0, write=300.0, pool=60.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )

    @classmethod
    async def shutdown(cls) -> None:
        if cls._http_client is not None and not cls._http_client.is_closed:
            await cls._http_client.aclose()
        cls._http_client = None

    @classmethod
    async def _client(cls):
        if cls._http_client is None or cls._http_client.is_closed:
            await cls.startup()
        return cls._http_client

    # Recommended verified models for local RAG & technical analysis
    RECOMMENDED_MODELS = [
        {"name": "llama3.2:3b", "desc": "Lightweight & Fast (Meta)", "url": "https://ollama.com/library/llama3.2"},
        {"name": "llama3.1:8b", "desc": "Balanced Accuracy (Meta)", "url": "https://ollama.com/library/llama3.1"},
        {"name": "qwen2.5:7b", "desc": "High Technical Precision (Alibaba)", "url": "https://ollama.com/library/qwen2.5"},
        {"name": "mistral:7b", "desc": "Instruction Following (Mistral)", "url": "https://ollama.com/library/mistral"},
        {"name": "deepseek-r1:8b", "desc": "Deep Reasoning & Analysis", "url": "https://ollama.com/library/deepseek-r1"},
        {"name": "phi4:14b", "desc": "High Logic & Math Capacity (Microsoft)", "url": "https://ollama.com/library/phi4"},
    ]

    @classmethod
    async def get_available_models(cls) -> List[str]:
        """Fetches all installed Ollama models from the local instance."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(cls.TAGS_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    embed_base = cls.EMBED_MODEL.split(":", 1)[0].lower()
                    models = [
                        name
                        for item in data.get("models", [])
                        if (name := item.get("name"))
                        and name.split(":", 1)[0].lower() != embed_base
                    ]
                    return models if models else [cls.CHAT_MODEL]
            except Exception as e:
                logger.warning(f"Failed to fetch Ollama model tags: {e}")
        return [cls.CHAT_MODEL]

    @classmethod
    async def stream_openai_compatible(
        cls,
        messages: list[dict],
        model: str,
        base_url: str,
        api_key: str,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from OpenAI-compatible hosted or local APIs."""
        from urllib.parse import urlparse

        base_url = base_url.strip().rstrip("/")
        parsed = urlparse(base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
        if not parsed.hostname or not (
            parsed.scheme == "https"
            or (parsed.scheme == "http" and parsed.hostname.lower() in local_hosts)
        ):
            yield "[Provider URL must use HTTPS, or HTTP on a local address.]"
            return

        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        timeout = httpx.Timeout(connect=20.0, read=None, write=300.0, pool=60.0)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": messages, "stream": True, "temperature": 0.2}

        try:
            client = await cls._client()
            async with client.stream("POST", endpoint, headers=headers, json=body, timeout=timeout) as response:
                if response.status_code >= 400:
                    yield f"[Provider request failed with HTTP {response.status_code}. Check the API key, model, and endpoint.]"
                    return
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                        delta = event.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if isinstance(token, str) and token:
                            yield token
                    except (json.JSONDecodeError, IndexError, AttributeError):
                        continue
        except httpx.HTTPError as exc:
            logger.warning("OpenAI-compatible provider connection failed: %s", type(exc).__name__)
            yield "[Could not connect to the selected provider. Check the endpoint and your connection.]"

    @classmethod
    async def get_embedding(cls, text: str) -> List[float]:
        payload = {"model": cls.EMBED_MODEL, "prompt": text}
        client = await cls._client()
        resp = await client.post(cls.EMBED_URL, json=payload)
        if resp.status_code == 200:
            embedding = resp.json().get("embedding", [])
            if embedding:
                return embedding
        raise RuntimeError(f"Embedding failure: {resp.text}")

    @classmethod
    async def get_embeddings(cls, texts: List[str]) -> List[List[float]]:
        """Embed chunks in batches, falling back to the legacy Ollama endpoint."""
        if not texts:
            return []

        client = await cls._client()
        batch_url = cls.EMBED_URL.replace("/api/embeddings", "/api/embed")
        embeddings: List[List[float]] = []
        try:
            for start in range(0, len(texts), 16):
                response = await client.post(
                    batch_url,
                    json={"model": cls.EMBED_MODEL, "input": texts[start : start + 16]},
                )
                response.raise_for_status()
                batch = response.json().get("embeddings", [])
                if len(batch) != len(texts[start : start + 16]) or any(not vector for vector in batch):
                    raise ValueError("Ollama returned an incomplete embedding batch")
                embeddings.extend(batch)
            return embeddings
        except (httpx.HTTPError, ValueError, KeyError):
            logger.info("Batch embedding API unavailable; using the compatible single-text endpoint")

        semaphore = asyncio.Semaphore(5)

        async def embed_one(text: str) -> List[float]:
            async with semaphore:
                return await cls.get_embedding(text)

        return await asyncio.gather(*(embed_one(text) for text in texts))

    @classmethod
    async def stream_summarize_chunks(
        cls,
        chunks: List[str],
        custom_prompt: Optional[str] = None,
        model: Optional[str] = None,
        provider: str = "ollama",
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Executive Document Summarizer with zero-refusal prompt structures.
        """
        if not chunks:
            yield "No readable text could be extracted from the document."
            return

        if len(chunks) == 1:
            selected_text = chunks[0]
        elif len(chunks) == 2:
            selected_text = f"{chunks[0]}\n\n---\n\n{chunks[1]}"
        elif len(chunks) == 3:
            selected_text = f"{chunks[0]}\n\n---\n\n{chunks[1]}\n\n---\n\n{chunks[2]}"
        else:
            selected_text = (
                f"[DOCUMENT_HEAD]\n{chunks[0]}\n\n"
                f"[DOCUMENT_CORE]\n{chunks[1]}\n\n"
                f"[DOCUMENT_CONCLUSION]\n{chunks[-1]}"
            )

        truncated_context = selected_text[:14000]
        target_model = model if model else cls.CHAT_MODEL

        user_directive = custom_prompt.strip() if (custom_prompt and custom_prompt.strip()) else (
            "Provide a comprehensive, structured technical breakdown covering the background, core details, achievements, and key findings."
        )

        system_instruction = (
            "You are DocuMind, an elite AI document analysis engine. "
            "You have direct access to the raw extracted document content provided below. "
            "Never claim you cannot view, open, or access files. Analyze and answer directly using the provided text."
        )

        user_content = (
            f"=== EXTRACTED SOURCE CONTENT ===\n{truncated_context}\n\n"
            f"=== INSTRUCTION ===\n{user_directive}"
        )

        if provider == "openai-compatible":
            if not api_base_url or not api_key:
                yield "[Add an API endpoint and API key in Model settings to use this provider.]"
                return
            async for token in cls.stream_openai_compatible(
                [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content},
                ],
                model=target_model,
                base_url=api_base_url,
                api_key=api_key,
            ):
                yield token
            return

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content}
            ],
            "options": {
                "num_ctx": 8192,
                "temperature": 0.2,
                "num_predict": 850,
            },
            "stream": True,
        }

        try:
            client = await cls._client()
            async with client.stream("POST", cls.API_URL, json=payload) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            yield token
                elif response.status_code == 404:
                    yield f"[Backend Error: Model '{target_model}' is not pulled in Ollama. Run 'ollama pull {target_model}' in terminal to install it.]"
                else:
                    yield f"[Inference Server Error: HTTP {response.status_code}]"
        except Exception as e:
            logger.exception("Local Ollama summary request failed")
            yield f"[Connection error: {type(e).__name__}. Check that Ollama is running.]"

    @classmethod
    async def summarize_chunks(cls, chunks: List[str], model: Optional[str] = None) -> str:
        summary = ""
        async for token in cls.stream_summarize_chunks(chunks, model=model):
            summary += token
        return summary
