# Local model performance

DocuMind keeps `llama3.2:3b` as the default. These changes tune its runtime and request flow; they do not replace the model or rebuild document embeddings.

## One 8,192-token context

Every local generation request and model preload explicitly sends:

```python
options = {"num_ctx": 8192, "num_predict": 512}
keep_alive = "15m"
```

The Longer answer setting uses 1,536 output tokens, with the same 8K context. This prevents ordinary chat from inheriting a much larger machine-wide `OLLAMA_CONTEXT_LENGTH` and avoids switching between 8K summary and 64K chat allocations.

`context_budget.py` reserves output space plus 512 tokens for chat-template differences. It preserves the full current question, includes selected document sources, and fits recent history into the remaining space. Long summaries receive excerpts from the beginning, middle, and end of each selected document. The user sees a persistent notice when excerpts are shortened or older history is omitted. An oversized question is rejected rather than silently truncated.

For Llama 3, the budgeter reconstructs the text tokenizer using vocabulary and merges exposed by the **local** Ollama `/api/show` endpoint. No tokenizer or model download is required. Role/template overhead is accounted for conservatively. Other tokenizer families use a conservative UTF-8 byte bound until a verified tokenizer is supported. This fallback can include less text; the final response still reports Ollama's actual prompt-token count.

## Keep the selected model warm

The UI calls `POST /summarizer/models/preload` when a local model is selected. An empty chat request loads that model with the same 8K context and `keep_alive: "15m"`. Repeated UI reruns do not repeatedly reload it. Every generation renews the 15-minute keep-alive period. This reduces model-loading delay, not the time needed to evaluate a new prompt.

Local preloads and generations share a lock so they do not compete for multiple generation slots on the laptop GPU. PDF extraction and health checks remain independent.

## Short and Longer answers

Open the model picker and choose **Answer length → Short** or **Longer**. The default is Short: a concise instruction and a 512-token generation cap. Longer requests more explanation and allows 1,536 tokens. If an answer reaches its cap, the UI says so. The input budget reserves the chosen output allocation before packing document text/history.

## Flash Attention and cache precision

When the launcher starts its own Ollama server, it applies these process-scoped settings:

```text
OLLAMA_CONTEXT_LENGTH=8192
OLLAMA_KEEP_ALIVE=15m
OLLAMA_NUM_PARALLEL=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=f16
```

The project setting `DOCUMIND_OLLAMA_KV_CACHE_TYPE=q8_0` selects an 8-bit context cache instead. The default remains `f16`: the tuned 8K model fits entirely on the tested 6 GB GPU, and a small synthetic comparison did not establish a speed advantage for q8. The cache allocation fell from 896 MiB to 476 MiB with q8, and the four tested factual fields remained correct. This is a small smoke comparison, not a broad accuracy evaluation.

The launcher leaves an already-running Ollama server untouched. Its existing Flash Attention/cache settings remain in effect; per-request 8K context and 15-minute keep-alive still apply. No Windows user or machine environment variables are changed. When the launcher closes a server it started on Windows, it also stops that server's child model runners so they do not retain GPU memory.

## Thinking controls

The backend reads each selected model's advertised `thinking.values` from `/api/show`, caches the metadata, and sends `think: false` only when `false` is supported. Models that require thinking or expose only named levels keep their supported defaults. Longer changes response length; it does not enable an extra reasoning mode.

## Actual generation metrics

Ollama's final stream event supplies token counts and nanosecond timings. The backend forwards these in the final JSON Lines `done.metrics` object:

```python
tokens_per_second = eval_count * 1_000_000_000 / eval_duration
```

Saved metrics include generated tokens, evaluated prompt tokens, model load time, prompt evaluation time, generation time, and total model time. The frontend separately measures **time to first visible answer text** and total response duration, including retrieval and request overhead.

Enable **Connection & details → Show response details** to see generation speed, output tokens, model-loading time, first response time, and document search time. Old saved responses and hosted providers without Ollama metrics do not acquire invented token counts. Network chunk counts are no longer treated as token counts.

## Relevant code and checks

- Backend: `app/services/context_budget.py`, `app/services/llm_service.py`, `app/routers/summarizer.py`, `app/schemas.py`.
- Frontend: `api_client.py`, `app.py`.
- Startup: repository-root `launcher.py`, `.env.example`, `docker-compose.yml`.
- Tests: prompt packing, Unicode boundaries, unsupported tokenizer fallback, thinking capabilities, preload settings, genuine token metrics, API length choices, and safe launcher lifecycle are covered by the backend test suite.
