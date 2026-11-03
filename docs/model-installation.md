# Model library and Windows command-line installer

Open **Model & preferences → Local Ollama** in PDF conversations, or **Model: … · Manage models** in the exam desk. The list marks installed and missing models. Choose a missing catalogue model to preview its model-file size and configured library folder. Edit the folder if needed, review again, then click **Install in Command Prompt**. Selecting a missing model does not change the active answer model and does not download weights.

The preview reads public registry metadata, reports model-file size, remaining download estimate, free space and any existing-library copy. Sizes use GiB, not a RAM/VRAM requirement. A failed size lookup blocks installation until a fresh successful preview. Registry tags may change after preview; disk/download errors remain explicit failures. No model-quality or speed guarantee is implied by catalogue descriptions.

Command Prompt shows DocuMind progress and stays open after completion. The UI polls the same job; settings can be closed and reopened during installation. Cancel in the UI or press Ctrl+C in the console. Interrupted downloads can be retried; Ollama reuses downloaded parts. Keep DocuMind running while its desktop installer job is active. A completed status requires both Ollama's success event and an installed-model tag.

## Folder behavior

Ollama has one model library per server. Changing the folder therefore applies to the DocuMind library, including its embedding model, rather than choosing an isolated download file. Existing model files are **copied, not deleted or moved**. A conflicting destination file fails safely. The preview budgets copying and download space plus 512 MiB of headroom. Pick an empty dedicated directory or an existing Ollama library containing only `blobs` and `manifests`.

A new folder is downloaded using a temporary, local Ollama server with its own `OLLAMA_MODELS`. After verification succeeds, DocuMind records `DOCUMIND_MODEL_DIRECTORY` in its local `.env`, preserving unrelated settings. **Restart DocuMind to activate it.** The running app retains its existing server during the operation. If a foreign server occupies the configured port next launch, DocuMind chooses a free port and leaves that server alone.

For an existing server, Ollama's generated Modelfile supplies its actual model-blob path to establish that the configured folder really is its library. A server owned by the current launcher is also known to use its supplied environment. If the folder cannot be established, the installer uses a temporary server and requires a restart, so the chosen destination is honored. Old model files remain in their original location; reclaiming that disk space is a separate user decision.

## CLI examples

From Command Prompt in the project directory:

```bat
documind --help
documind models --help
documind models list
documind models info llama3.2:3b
documind models install llama3.2:3b
documind models install llama3.2:3b --directory "D:\AI\DocuMindModels"
```

PowerShell uses `.\documind.cmd`:

```powershell
.\documind.cmd --help
.\documind.cmd models install llama3.2:3b --directory 'D:\AI\DocuMindModels'
```

`models info` reviews without downloading weights. `models install` prints the review and asks `Proceed?`; `--yes` explicitly accepts it for scripting. The command is available from the project directory and is not added to the system PATH. The command wrapper reuses the launcher environment, including bundled Ollama binaries in an offline transfer installation. New downloads still require internet.

## Actual implementation and data flow

| Module | Responsibility |
| --- | --- |
| [model-library.tsx](../documind-web/components/model-library.tsx) | Shared model picker, frozen preview, editable destination, progress/cancellation, retry and explicit selection of an installed answer model. |
| [local-models route](../documind-web/app/api/local-models/[...path]/route.ts) | Next.js forwards a small allowlist of same-origin requests to the host helper. The browser never receives the helper credential and cannot invoke its private console execution route. |
| [model_installation.py](../model_installation.py) | Standard-library loopback helper, catalogue, manifest metadata, path/space validation, one active job, visible console launch, copy-preserving storage change and verified NDJSON download progress. |
| [documind_cli.py](../documind_cli.py), [documind.cmd](../documind.cmd) | `argparse` help and commands, interactive review, console progress and return codes. Desktop jobs use a random job ID rather than injecting model/path values into shell text. |
| [launcher.py](../launcher.py) | Starts and stops the host helper with the app, passes an ephemeral credential only to the host Next.js process, honors the selected folder and avoids terminating foreign Ollama processes. |
| [llm_service.py](../pdf-summarizer-backend/app/services/llm_service.py) | Reports actual installed answer models; an empty or unreachable Ollama no longer invents an installed default model. |

The host helper is necessary because FastAPI runs in Linux Docker and cannot open the user's Windows Command Prompt. There is no additional Python dependency or hosted installation service.

### Preview before side effects

```python
layers = remote_manifest(name)
total = sum(row['size'] for row in layers)
```

The requested name must belong to the fixed download catalogue. Metadata comes from Ollama's HTTPS registry; this request does not fetch weight blobs. Destination checks reject relative/network paths, drive/project roots, nested libraries, symbolic links and unrelated nonempty folders. Free-space validation runs again before a one-use preview becomes a job. Changing the model or folder invalidates the UI confirmation. The remaining-download value is an estimate because corrupt cached blobs may need downloading again.

### Explicit confirmation and console handoff

```json
{"preview_id":"server-issued-one-use-preview"}
```

This is the browser's installation request. The helper claims one active slot, opens a visible CMD window and passes a hex job ID to the CLI. The chosen model and path remain JSON/Python values, never user-controlled shell fragments. A per-launch secret protects the loopback helper; it stays in process memory/environment, not browser storage, command arguments, `.env`, logs or committed files. The Next.js route restricts local host, origin, method, path and payload size. No API is provided for arbitrary commands, arbitrary registry hosts or deleting models.

### Reliable completion and storage changes

```python
if not success:
    raise InstallError('The download ended before verification finished. Retry to resume.')
```

Ollama's NDJSON status events supply progress. A dropped stream, server error or missing final success remains failed/cancelled. After success, the helper checks `/api/tags`; only then can it persist a changed library location and report completion. Existing models are copied before downloading into a new library so BGE-M3 document search remains available after restart. No existing file is overwritten if its contents conflict. Cancelled copy operations remove only their own temporary file.

The tradeoff is a Windows-specific visible-console flow for the desktop UI, a shared folder rather than per-model activation paths, and one restart for a folder change. Direct CLI use is also supported; the normal desktop launch provides UI-to-console integration. Running `npm start` alone leaves installed models usable but shows instructions to use `Start_DocuMind.bat` for the installer.

## Verification

The installer is tested with tiny local fixtures and mocked remote responses: size-only preview, destination/space validation, conflicting-file protection, cancellation, one-use previews, single-job admission, closed-console recovery, missing success/tag failures, copied-library preservation, settings preservation, browser origin restrictions and non-disclosure of the helper token. Public registry manifests for all seven catalogue models were read successfully; no real model weights were downloaded for verification. A real Windows CMD smoke test completed through the helper and CLI against a six-byte loopback fixture, then closed only its own test window.

Verified on Windows: **264 Python tests, 74 frontend unit tests and 10 browser tests passed**; the production Next.js build passed. The Python run reported an existing Starlette/httpx deprecation warning. Browser tests use controlled model/provider responses; they do not prove real-world download speed or model quality. Docker was stopped during this verification, so the complete container-backed application was not exercised live.

Repeat the checks from the corresponding directory:

```powershell
# pdf-summarizer-backend
.\venv_win\Scripts\python.exe -m pytest -q

# documind-web
npm test
npm run build
# With the frontend already running at the configured test URL:
npm run test:e2e
```

Related authoritative behavior: [Ollama model storage configuration](https://docs.ollama.com/faq#where-are-models-stored) and [streamed model pulls](https://docs.ollama.com/api/pull).
