import json

import httpx
import pytest

from app.services.errors import GenerationError
from app.services.llm_service import LLMService


@pytest.mark.anyio
@pytest.mark.parametrize("status,body", [
    (404, b"not found"), (500, b"error"),
    (200, b'{"message":{"content":"partial"}}\n'),
    (200, b'{"error":"internal provider error"}\n'),
    (200, b'not json\n'),
])
async def test_local_failures_raise_instead_of_becoming_text(monkeypatch, status, body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body))) as client:
        monkeypatch.setattr(LLMService, "_http_client", client)
        with pytest.raises(GenerationError):
            _ = [token async for token in LLMService.stream_messages([{"role": "user", "content": "hello"}])]


@pytest.mark.anyio
async def test_successful_local_stream_requires_done(monkeypatch):
    body = b'{"message":{"content":"Hello"}}\n{"done":true}\n'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))) as client:
        monkeypatch.setattr(LLMService, "_http_client", client)
        assert [token async for token in LLMService.stream_messages([])] == ["Hello"]


@pytest.mark.anyio
@pytest.mark.parametrize("body,success", [
    (b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n', True),
    (b'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":"stop"}]}\n\n', True),
    (b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n', False),
    (b'data: {"error":{"message":"private provider details"}}\n\n', False),
    (b'data: broken json\n\n', False),
])
async def test_hosted_stream_completion_and_failures(monkeypatch, body, success):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))) as client:
        monkeypatch.setattr(LLMService, "_http_client", client)
        tokens = LLMService.stream_openai_compatible([], "test-model", "https://example.test/v1", "test-key")
        if success:
            assert [token async for token in tokens] == ["Hello"]
        else:
            with pytest.raises(GenerationError):
                _ = [token async for token in tokens]


@pytest.mark.anyio
@pytest.mark.parametrize("thinking_values,expected_override", [([False, True], False), ([False], False), (["low", "high"], None), ([], None)])
@pytest.mark.parametrize("answer_length,limit", [("short", 512), ("long", 1536)])
async def test_settings_thinking_and_real_metrics(monkeypatch, thinking_values, expected_override, answer_length, limit):
    requests = []
    def respond(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"thinking": {"values": thinking_values}})
        return httpx.Response(200, content=(
            '{"message":{"content":"Hello there"}}\n'
            '{"done":true,"done_reason":"stop","model":"test-model","eval_count":20,"eval_duration":500000000,"prompt_eval_count":123,"prompt_eval_duration":80000000,"load_duration":15000000,"total_duration":595000000}\n'
        ).encode())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(LLMService, "_http_client", client)
        telemetry = {}
        result = [token async for token in LLMService.stream_messages([], answer_length=answer_length, telemetry=telemetry, options={"num_ctx":65536})]
    body = next(body for path, body in requests if path == "/api/chat")
    assert result == ["Hello there"]
    assert body["options"]["num_ctx"] == 8192 and body["options"]["num_predict"] == limit
    assert body["keep_alive"] == "15m"
    if expected_override is False:
        assert body["think"] is False
    else:
        assert "think" not in body
    assert telemetry["generated_tokens"] == 20 and telemetry["tok_per_sec"] == 40.0
    assert telemetry["prompt_tokens"] == 123 and telemetry["load_ms"] == 15.0
    assert telemetry["prompt_eval_ms"] == 80.0 and telemetry["generation_ms"] == 500.0


@pytest.mark.anyio
async def test_preload_uses_same_context_and_queries_capability_once(monkeypatch):
    requests = []
    def respond(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"thinking": {"values": [False, True]}})
        return httpx.Response(200, json={"done":True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(LLMService, "_http_client", client)
        assert await LLMService.preload_model("test-model")
        assert await LLMService.preload_model("test-model")
    assert sum(path == "/api/show" for path, _ in requests) == 1
    for path, body in requests:
        if path == "/api/chat":
            assert body["messages"] == [] and body["options"]["num_ctx"] == 8192
            assert body["keep_alive"] == "15m" and body["think"] is False
