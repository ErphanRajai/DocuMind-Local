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
                    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                    return models if models else [cls.CHAT_MODEL]
            except Exception as e:
                logger.warning(f"Failed to fetch Ollama model tags: {e}")
        return [cls.CHAT_MODEL]

    @classmethod
    async def get_embedding(cls, text: str) -> List[float]:
        payload = {"model": cls.EMBED_MODEL, "prompt": text}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(cls.EMBED_URL, json=payload)
            if resp.status_code == 200:
                return resp.json().get("embedding", [])
            raise RuntimeError(f"Embedding failure: {resp.text}")

    @classmethod
    async def stream_summarize_chunks(
        cls,
        chunks: List[str],
        custom_prompt: Optional[str] = None,
        model: Optional[str] = None,
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

        client_timeout = httpx.Timeout(connect=20.0, read=None, write=300.0, pool=60.0)
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            try:
                async with client.stream("POST", cls.API_URL, json=payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line:
                                data = json.loads(line)
                                token = data.get("message", {}).get("content", "")
                                yield token
                    elif response.status_code == 404:
                        yield f"[Backend Error: Model '{target_model}' is not pulled in Ollama. Run 'ollama run {target_model}' in terminal to install it.]"
                    else:
                        yield f"[Inference Server Error: HTTP {response.status_code}]"
            except Exception as e:
                yield f"[Connection Error: {str(e)}]"

    @classmethod
    async def summarize_chunks(cls, chunks: List[str], model: Optional[str] = None) -> str:
        summary = ""
        async for token in cls.stream_summarize_chunks(chunks, model=model):
            summary += token
        return summary