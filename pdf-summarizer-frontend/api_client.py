"""API protocol helpers, kept independent of Streamlit for focused tests."""

import time
import json


def require_success(response):
    if response.is_error:
        response.read()
        try:
            detail = response.json().get("detail", "Request failed.")
            if isinstance(detail, list):
                detail = "; ".join(item.get("msg", "Invalid request") for item in detail)
        except (ValueError, AttributeError):
            detail = f"Backend returned HTTP {response.status_code}."
        raise RuntimeError(str(detail))


def response_text_chunks(response, telemetry):
    """Decode whole JSON lines even when UTF-8 or events span network packets."""
    require_success(response)
    for line in response.iter_lines():
        if not line:
            continue
        try:
            event = json.loads(line)
            kind = event["type"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("The backend returned an invalid answer stream.") from exc
        if kind == "metadata":
            telemetry.update(event)
        elif kind == "text":
            yield event["content"]
        elif kind == "replace_text":
            telemetry['_replace_text'] = True
            yield event['content']
        elif kind in {'status','heartbeat'}:
            continue
        elif kind == "error":
            raise RuntimeError(event.get("message", "The answer could not be completed."))
        elif kind == "done":
            telemetry.update(event.get("metrics", {}))
            return
        else:
            raise RuntimeError("The backend returned an unknown answer event.")
    raise RuntimeError("The connection ended before the answer finished. The incomplete answer was not saved.")


def wait_for_documents(client, backend_url, pdf_ids, on_update, timeout=600, interval=0.5):
    """Wait for indexing instead of uploading or extracting the same PDF again."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        records = []
        for pdf_id in pdf_ids:
            response = client.get(f"{backend_url}/summarizer/documents/{pdf_id}", timeout=10)
            require_success(response)
            record = response.json()
            if record["status"] == "failed":
                raise RuntimeError(f"{record['filename']}: {record.get('error_message') or 'Document processing failed.'}")
            records.append(record)
        on_update(records)
        if all(record["status"] in {"completed", "partial"} for record in records):
            return records
        time.sleep(interval)
    raise RuntimeError("The PDFs are still processing. Wait a little, then send your question again.")
