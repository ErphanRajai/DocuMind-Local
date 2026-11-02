import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from typing import AsyncGenerator, List, Optional
from urllib.parse import urlparse

import httpx

from .errors import GenerationError
from .context_budget import CONTEXT_TOKENS, OUTPUT_TOKENS, TokenCounter, build_prompt

logger = logging.getLogger(__name__)


class LLMService:
    @staticmethod
    def require_local_endpoint(url):
        if os.getenv('DOCUMIND_LOCAL_ONLY') == '1' and urlparse(str(url)).hostname not in {'localhost','127.0.0.1','::1','host.docker.internal'}:
            raise GenerationError('Local-only mode permits model requests only to this computer.')

    @staticmethod
    async def guard_local_request(request):
        LLMService.require_local_endpoint(request.url)
    CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:3b")
    EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
    API_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434/api/chat")
    EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://host.docker.internal:11434/api/embeddings")
    TAGS_URL = os.getenv("OLLAMA_TAGS_URL", "http://host.docker.internal:11434/api/tags")
    _http_client: Optional[httpx.AsyncClient] = None
    KEEP_ALIVE = "15m"
    _profiles = OrderedDict()
    _profile_lock = None
    _generation_lock = None

    @classmethod
    async def startup(cls) -> None:
        """Reuse HTTP connections to the local Ollama service across requests."""
        if cls._http_client is None or cls._http_client.is_closed:
            cls._http_client = httpx.AsyncClient(
                event_hooks={'request':[cls.guard_local_request]},
                timeout=httpx.Timeout(connect=20.0, read=60.0, write=300.0, pool=60.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )

    @classmethod
    async def shutdown(cls) -> None:
        if cls._http_client is not None and not cls._http_client.is_closed:
            await cls._http_client.aclose()
        cls._http_client = None
        cls._profiles.clear()
        cls._profile_lock = None
        cls._generation_lock = None

    @classmethod
    async def _client(cls):
        if cls._http_client is None or cls._http_client.is_closed:
            await cls.startup()
        return cls._http_client

    @classmethod
    def _locks(cls):
        if cls._profile_lock is None:
            cls._profile_lock = asyncio.Lock()
        if cls._generation_lock is None:
            cls._generation_lock = asyncio.Lock()

    @classmethod
    async def model_profile(cls, model):
        """Read tokenizer and thinking controls locally; never download a tokenizer."""
        if os.getenv('DOCUMIND_LOCAL_ONLY') == '1' and 'cloud' in model.lower():
            raise GenerationError('Cloud-backed models are disabled in local-only mode.')
        cls._locks()
        async with cls._profile_lock:
            cached = cls._profiles.get(model)
            if cached and time.monotonic() - cached[0] < 900:
                cls._profiles.move_to_end(model)
                return cached[1]
            data = {}
            try:
                client = await cls._client()
                response = await client.post(
                    cls.API_URL.rsplit("/api/", 1)[0] + "/api/show",
                    json={"model": model, "verbose": True}, timeout=15,
                )
                if response.status_code == 404:
                    raise GenerationError(f"Model '{model}' is not installed in Ollama. Select an installed model.")
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    data = {}
                if os.getenv('DOCUMIND_LOCAL_ONLY') == '1' and (data.get('remote_host') or data.get('remote_model')):
                    raise GenerationError('This model delegates to a remote host; choose an installed local model.')
            except (httpx.HTTPError, ValueError):
                logger.warning("Could not read model metadata; using conservative prompt budgeting")
            try:
                counter = await asyncio.to_thread(TokenCounter.from_metadata, data.get("model_info", {}))
            except Exception:
                logger.warning("Unsupported tokenizer metadata; using conservative prompt budgeting")
                counter = TokenCounter()
            thinking = data.get("thinking") or {}
            profile = {
                "counter": counter,
                "can_disable_thinking": isinstance(thinking, dict) and False in (thinking.get("values") or []),
            }
            cls._profiles[model] = (time.monotonic(), profile)
            while len(cls._profiles) > 4:
                cls._profiles.popitem(last=False)
            return profile

    @classmethod
    async def prepare_prompt(cls, system, question, history=None, sources=None, model=None,
                             provider="ollama", answer_length="short", spread=False):
        counter = (await cls.model_profile(model or cls.CHAT_MODEL))["counter"] if provider == "ollama" else TokenCounter()
        return await asyncio.to_thread(
            build_prompt, counter, system, question, history, sources, answer_length, spread
        )

    @classmethod
    async def preload_model(cls, model):
        """An empty chat loads the selected model with the same 8K allocation."""
        try:
            profile = await cls.model_profile(model)
            body = {
                "model": model, "messages": [], "stream": False,
                "keep_alive": cls.KEEP_ALIVE,
                "options": {"num_ctx": CONTEXT_TOKENS, "num_predict": OUTPUT_TOKENS["short"]},
            }
            if profile["can_disable_thinking"]:
                body["think"] = False
            async with cls._generation_lock:
                client = await cls._client()
                response = await client.post(cls.API_URL, json=body)
                response.raise_for_status()
            return True
        except (httpx.HTTPError, GenerationError):
            logger.warning("Selected model could not be preloaded: %s", model)
            return False

    @staticmethod
    def generation_metrics(data):
        metrics = {"metrics_source": "ollama", "model": data.get("model"), "done_reason": data.get("done_reason")}
        for source, destination in (("eval_count", "generated_tokens"), ("prompt_eval_count", "prompt_tokens")):
            if isinstance(data.get(source), (int, float)):
                metrics[destination] = data[source]
        for source, destination in (("load_duration", "load_ms"), ("prompt_eval_duration", "prompt_eval_ms"),
                                    ("eval_duration", "generation_ms"), ("total_duration", "total_model_ms")):
            if isinstance(data.get(source), (int, float)):
                metrics[destination] = round(data[source] / 1_000_000, 2)
        if data.get("eval_duration", 0) > 0 and "eval_count" in data:
            metrics["tok_per_sec"] = round(data["eval_count"] * 1_000_000_000 / data["eval_duration"], 2)
        return metrics

    # Suggested models, not a claim of measured accuracy on arbitrary exams.
    RECOMMENDED_MODELS = [
        {"name":"qwen3:4b-instruct-2507-q4_K_M", "desc":"Multilingual local setup default", "url":"https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M"},
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
        cls.require_local_endpoint(cls.TAGS_URL)
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
        answer_length: str = "short",
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
            raise GenerationError("Provider URL must use HTTPS, or HTTP on a local address.")

        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        timeout = httpx.Timeout(connect=20.0, read=60.0, write=300.0, pool=60.0)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": messages, "stream": True, "temperature": 0.2,
                "max_tokens": OUTPUT_TOKENS[answer_length]}

        try:
            client = await cls._client()
            async with client.stream("POST", endpoint, headers=headers, json=body, timeout=timeout) as response:
                if response.status_code >= 400:
                    raise GenerationError(f"Provider request failed with HTTP {response.status_code}. Check the API key, model, and endpoint.")
                finished = False
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        finished = True
                        break
                    try:
                        event = json.loads(data)
                        if event.get("error"):
                            raise GenerationError("The selected provider reported an error. Check its model settings.")
                        choices = event.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        token = delta.get("content", "")
                        if isinstance(token, str) and token:
                            yield token
                        if choices[0].get("finish_reason") is not None:
                            finished = True
                    except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as exc:
                        raise GenerationError("The provider returned an invalid streaming response.") from exc
                if not finished:
                    raise GenerationError("The provider connection ended before the answer was complete. Please try again.")
        except httpx.HTTPError as exc:
            logger.warning("OpenAI-compatible provider connection failed: %s", type(exc).__name__)
            raise GenerationError("Could not connect to the selected provider. Check the endpoint and your connection.") from exc

    @classmethod
    async def stream_messages(
        cls, messages, model=None, provider="ollama", api_base_url=None, api_key=None, options=None,
        answer_length="short", telemetry=None,
    ) -> AsyncGenerator[str, None]:
        target_model = model or cls.CHAT_MODEL
        if os.getenv('DOCUMIND_LOCAL_ONLY') == '1' and provider != 'ollama':
            raise GenerationError('Hosted providers are disabled in local-only mode.')
        if provider == "openai-compatible":
            if not api_base_url or not api_key:
                raise GenerationError("Add an API endpoint and API key in Model settings.")
            async for token in cls.stream_openai_compatible(messages, target_model, api_base_url, api_key, answer_length):
                yield token
            return
        if provider != "ollama":
            raise GenerationError("Unsupported model provider.")
        profile = await cls.model_profile(target_model)
        generation_options = {"temperature": 0.2, **(options or {})}
        generation_options.update(num_ctx=CONTEXT_TOKENS, num_predict=OUTPUT_TOKENS[answer_length])
        payload = {
            "model": target_model, "messages": messages,
            "options": generation_options, "stream": True, "keep_alive": cls.KEEP_ALIVE,
        }
        if profile["can_disable_thinking"]:
            payload["think"] = False
        if telemetry is not None:
            telemetry.update(context_tokens=CONTEXT_TOKENS, max_output_tokens=OUTPUT_TOKENS[answer_length],
                             thinking_disabled=profile["can_disable_thinking"])
        try:
            client = await cls._client()
            cls._locks()
            async with cls._generation_lock, client.stream("POST", cls.API_URL, json=payload) as response:
                if response.status_code == 404:
                    raise GenerationError(f"Model '{target_model}' is not installed in Ollama. Select an installed model.")
                if response.status_code != 200:
                    raise GenerationError(f"Ollama returned HTTP {response.status_code}. Check the local model service.")
                finished = False
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("error"):
                            raise GenerationError("Ollama could not generate an answer. Check the selected model.")
                        token = data.get("message", {}).get("content", "")
                        if not isinstance(token, str):
                            raise TypeError("Token must be text")
                        if token:
                            yield token
                        if data.get("done"):
                            if telemetry is not None:
                                telemetry.update(cls.generation_metrics(data))
                            finished = True
                            break
                    except (ValueError, TypeError, AttributeError) as exc:
                        raise GenerationError("Ollama returned an invalid streaming response.") from exc
                if not finished:
                    raise GenerationError("The Ollama connection ended before the answer was complete. Please try again.")
        except httpx.HTTPError as exc:
            logger.warning("Local model connection failed: %s", type(exc).__name__)
            raise GenerationError("Could not reach Ollama or the model timed out. Check that Ollama is running.") from exc

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
        answer_length: str = "short",
        telemetry: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """Generate a requested summary from already extracted chunks."""
        if not chunks:
            raise GenerationError("No readable text is available for this document.")

        target_model = model if model else cls.CHAT_MODEL

        user_directive = custom_prompt.strip() if (custom_prompt and custom_prompt.strip()) else (
            "Summarize the documents' purpose, main findings, and important details."
        )

        system_instruction = (
            "You are DocuMind, a document analysis assistant. Summarize the extracted source excerpts. "
            "Identify missing evidence and do not invent details that are absent from the excerpts."
        )

        plan = await cls.prepare_prompt(
            system_instruction, user_directive,
            sources=[{"title": f"Document {index + 1}", "text": text} for index, text in enumerate(chunks)],
            model=target_model, provider=provider, answer_length=answer_length, spread=True,
        )
        if telemetry is not None:
            telemetry.update(plan.metadata)

        async for token in cls.stream_messages(
            plan.messages,
            model=target_model, provider=provider, api_base_url=api_base_url, api_key=api_key,
            answer_length=answer_length, telemetry=telemetry,
        ):
            yield token

    @classmethod
    async def summarize_chunks(cls, chunks: List[str], model: Optional[str] = None) -> str:
        summary = ""
        async for token in cls.stream_summarize_chunks(chunks, model=model):
            summary += token
        return summary
