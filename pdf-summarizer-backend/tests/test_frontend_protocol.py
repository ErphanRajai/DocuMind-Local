import importlib.util
import json
from pathlib import Path

import httpx
import pytest

module_path = Path(__file__).resolve().parents[2] / "pdf-summarizer-frontend" / "api_client.py"
spec = importlib.util.spec_from_file_location("frontend_api", module_path)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class FragmentedStream(httpx.SyncByteStream):
    def __init__(self, body):
        self.body = body

    def __iter__(self):
        for index in range(0, len(self.body), 2):
            yield self.body[index:index + 2]


def stream(events):
    body = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events).encode()
    return httpx.Response(200, stream=FragmentedStream(body))


def test_utf8_and_events_split_across_packets():
    telemetry = {}
    response = stream([{"type": "metadata", "retrieval_ms": 12}, {"type": "text", "content": "café 🌱"}, {"type": "done"}])
    assert list(api.response_text_chunks(response, telemetry)) == ["café 🌱"]
    assert telemetry["retrieval_ms"] == 12


@pytest.mark.parametrize("last_event", [None, {"type": "error", "message": "Model failed"}])
def test_error_or_disconnect_never_returns_completed_answer(last_event):
    data = [{"type": "text", "content": "partial"}]
    if last_event:
        data.append(last_event)
    with pytest.raises(RuntimeError):
        list(api.response_text_chunks(stream(data), {}))


def test_status_polling_waits_for_indexing_and_surfaces_warnings():
    statuses = iter(["indexing", "partial"])
    def respond(request):
        return httpx.Response(200, json={"id": 1, "filename": "test.pdf", "status": next(statuses), "warning_message": "Page 2 unreadable"})
    updates = []
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = api.wait_for_documents(client, "http://backend", [1], updates.append, interval=0)
    assert len(updates) == 2 and records[0]["warning_message"]


def test_polling_stops_on_failed_extraction():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "filename": "test.pdf", "status": "failed", "error_message": "No readable text"
    }))) as client:
        with pytest.raises(RuntimeError, match="No readable text"):
            api.wait_for_documents(client, "http://backend", [1], lambda records: None)


def test_final_metrics_do_not_depend_on_network_packet_count():
    telemetry = {}
    response = stream([
        {"type":"metadata", "retrieval_ms":12}, {"type":"text", "content":"A long answer delivered in one chunk."},
        {"type":"done", "metrics":{"metrics_source":"ollama", "generated_tokens":50, "tok_per_sec":25.0, "load_ms":5.0}},
    ])
    assert list(api.response_text_chunks(response, telemetry)) == ["A long answer delivered in one chunk."]
    assert telemetry["generated_tokens"] == 50 and telemetry["tok_per_sec"] == 25.0
    assert telemetry["retrieval_ms"] == 12
