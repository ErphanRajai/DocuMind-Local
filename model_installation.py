"""Host-side model installation. No shell receives model names or user paths."""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CATALOG = [
    {"name": "qwen3:4b-instruct-2507-q4_K_M", "description": "DocuMind multilingual default"},
    {"name": "llama3.2:3b", "description": "Smaller general-purpose model"},
    {"name": "llama3.1:8b", "description": "Larger general-purpose model"},
    {"name": "qwen2.5:7b", "description": "Multilingual and technical tasks"},
    {"name": "mistral:7b", "description": "Instruction-following model"},
    {"name": "deepseek-r1:8b", "description": "Reasoning model; may take longer before answering"},
    {"name": "phi4:14b", "description": "Large model; needs substantially more memory"},
]
TERMINAL = {"completed", "failed", "cancelled"}
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class InstallError(ValueError):
    pass


def model_name(name):
    if name not in {m["name"] for m in CATALOG}:
        raise InstallError("Choose a downloadable model from the DocuMind catalogue.")
    return name


def read_json(url, payload=None, timeout=8):
    request = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with LOCAL.open(request, timeout=timeout) as response:
        return json.loads(response.read(2_000_001))


def remote_manifest(name):
    """Read public registry metadata only; never download a weight in preview."""
    family, tag = model_name(name).split(":", 1)
    request = urllib.request.Request(f"https://registry.ollama.ai/v2/library/{family}/manifests/{tag}", headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read(1_000_001))
        layers = [data["config"], *data["layers"]]
        if not layers or any(type(r.get("size")) is not int or not 0 <= r["size"] <= 10**12 or not re.fullmatch(r"sha256:[a-f0-9]{64}", r.get("digest", "")) for r in layers):
            raise ValueError()
        return layers
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InstallError("Could not read this model's download size. Connect to the internet and retry the preview. No model was downloaded.") from exc


def directory(value, project):
    if not isinstance(value, str) or not value.strip() or len(value) > 240 or any(ord(c) < 32 for c in value):
        raise InstallError("Choose an absolute local model-library folder.")
    path = Path(value).expanduser()
    if not path.is_absolute() or str(path).startswith("\\\\"):
        raise InstallError("Use an absolute folder on a local drive, not a network path.")
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in [path, *path.parents]):
        raise InstallError("Choose a model folder without symbolic links or junctions.")
    path = path.resolve()
    project = Path(project).resolve()
    if path == project or path in project.parents or path == Path(path.anchor):
        raise InstallError("Choose a dedicated models folder, not a drive or project root.")
    if path.exists() and (not path.is_dir() or any(p.name not in {"blobs", "manifests"} for p in path.iterdir())):
        raise InstallError("Choose an empty folder or an existing Ollama library containing only blobs and manifests.")
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise InstallError("Choose a model folder without symbolic links.")
    return path


def library_files(root):
    root = Path(root)
    files = []
    for folder in [root / "blobs", root / "manifests"]:
        if not folder.exists():
            continue
        for p in folder.rglob("*"):
            if p.is_symlink():
                raise InstallError("The model library contains symbolic links. Use a regular local model folder.")
            if p.is_file() and (folder.name == "manifests" or re.fullmatch(r"sha256-[a-f0-9]{64}", p.name)):
                files.append(p)
            if len(files) > 100_000:
                raise InstallError("The model library is too large for this installer.")
    return files


def disk_free(path):
    ancestor = Path(path)
    while not ancestor.exists():
        ancestor = ancestor.parent
    return shutil.disk_usage(ancestor).free


def copy_library(source, target, cancel, progress):
    """Copy, never move/delete, the existing library to preserve retrieval models."""
    source, target = Path(source), Path(target)
    for p in library_files(source):
        dest = target / p.relative_to(source)
        if cancel.is_set():
            raise InterruptedError("Installation cancelled; existing models are unchanged.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            with p.open("rb") as incoming, dest.open("rb") as existing:
                if hashlib.file_digest(incoming, "sha256").digest() != hashlib.file_digest(existing, "sha256").digest():
                    raise InstallError("A different file already exists in the destination model library. Choose another folder.")
            continue
        temp = dest.with_name(dest.name + ".documind-" + secrets.token_hex(8) + ".tmp")
        try:
            with p.open("rb") as incoming, temp.open("xb") as outgoing:
                while block := incoming.read(4 * 1024 * 1024):
                    if cancel.is_set():
                        raise InterruptedError("Installation cancelled; existing models are unchanged.")
                    outgoing.write(block)
            temp.replace(dest)
            progress("Preserving existing model files", 0, 0)
        finally:
            temp.unlink(missing_ok=True)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stop_owned(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class ModelManager:
    def __init__(self, project, environment):
        self.project = Path(project).resolve()
        self.environment = dict(environment)
        self.active_root = Path(environment.get("OLLAMA_MODELS") or Path.home() / ".ollama/models").expanduser().resolve()
        self.default_root = self.active_root
        port = int(environment.get("DOCUMIND_OLLAMA_PORT", "11434"))
        if not 1 <= port <= 65535:
            raise InstallError("Invalid local Ollama port.")
        self.base = f"http://127.0.0.1:{port}"
        if environment.get("DOCUMIND_OLLAMA_OWNED") != "1" and not environment.get("DOCUMIND_MODEL_DIRECTORY"):
            try:
                tags = read_json(self.base + "/api/tags", timeout=2).get("models", [])
                if tags:
                    show = read_json(self.base + "/api/show", {"model": tags[0]["name"]}, timeout=2)
                    blob = self.source_blob(show)
                    if blob and blob.parent.parent.is_dir():
                        self.active_root = blob.parent.parent.resolve()
                        self.default_root = self.active_root
            except (OSError, ValueError, KeyError):
                pass
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.previews, self.jobs = {}, {}
        self.manifests = {}
        self.consoles = {}
        self.server = None
        self.transient = None

    def catalogue(self):
        try:
            tags = read_json(self.base + "/api/tags").get("models", [])
            installed = {r["name"] for r in tags if isinstance(r.get("name"), str)}
            available = True
        except (OSError, ValueError, KeyError):
            installed, available = set(), False
        names = {r["name"] for r in CATALOG}
        rows = [{**r, "installed": r["name"] in installed} for r in CATALOG]
        rows.extend({"name": n, "description": "Installed locally", "installed": True} for n in sorted(installed - names) if not n.startswith(("bge-m3", "nomic-embed-text")))
        pending = {j["model"] for j in self.jobs.values() if j["state"] == "completed" and j["restart_required"] and Path(j["directory"]) == self.default_root}
        for row in rows:
            row["pending_restart"] = not row["installed"] and row["name"] in pending
        latest = self.status(next(reversed(self.jobs))) if self.jobs else None
        return {"models": rows, "directory": str(self.default_root), "ollama_available": available, "download_available": bool(shutil.which("ollama")), "windows_console": os.name == "nt", "latest_job": latest}

    def preview(self, name, location):
        name = model_name(name)
        target = directory(location, self.project)
        changed = target != self.active_root
        if changed and (target.is_relative_to(self.active_root) or self.active_root.is_relative_to(target)):
            raise InstallError("The old and new model libraries must not be inside one another.")
        cached = self.manifests.get(name)
        layers = cached[1] if cached and time.monotonic() - cached[0] < 600 else remote_manifest(name)
        self.manifests[name] = (time.monotonic(), layers)
        total = sum(r["size"] for r in layers)
        def reusable(base, layer):
            blob = base / "blobs" / layer["digest"].replace(":", "-")
            return blob.is_file() and blob.stat().st_size == layer["size"]
        missing = sum(r["size"] for r in layers if not (reusable(target, r) or changed and reusable(self.active_root, r)))
        copy_bytes = sum(p.stat().st_size for p in library_files(self.active_root) if not (target / p.relative_to(self.active_root)).exists()) if changed else 0
        free = disk_free(target)
        required = missing + copy_bytes + 512 * 1024**2
        if free < required:
            raise InstallError(f"Not enough free space: allow at least {required / 1024**3:.2f} GiB including existing models and temporary space.")
        verified = self.storage_verified()
        if not verified:
            try:
                existing = read_json(self.base + "/api/tags").get("models", [])
            except OSError:
                existing = []
            if existing:
                raise InstallError("Cannot confirm the running Ollama model folder. Restart DocuMind with DOCUMIND_MODEL_DIRECTORY set to your existing local model library; other Ollama servers will be left alone.")
        restart = changed or not verified
        result = {"id": secrets.token_hex(16), "model": name, "directory": str(target), "model_bytes": total, "download_bytes": missing, "copy_bytes": copy_bytes, "free_bytes": free, "required_bytes": required, "restart_required": restart, "created": time.time()}
        with self.lock:
            self.previews = {k: v for k, v in self.previews.items() if time.time() - v["created"] < 900}
            if len(self.previews) >= 32:
                self.previews.pop(next(iter(self.previews)))
            self.previews[result["id"]] = result
        return dict(result)

    def storage_verified(self):
        if self.environment.get("DOCUMIND_OLLAMA_OWNED") == "1":
            return True
        try:
            tags = read_json(self.base + "/api/tags").get("models", [])
            if not tags:
                return False
            # Identical manifests cannot prove physical location after a copy.
            show = read_json(self.base + "/api/show", {"model": tags[0]["name"]})
            blob = self.source_blob(show)
            return bool(blob and blob.parent.parent.resolve() == self.active_root)
        except (OSError, ValueError, KeyError):
            return False

    @staticmethod
    def source_blob(show):
        match = re.search(r"^FROM\s+(.+)$", show.get("modelfile", ""), re.MULTILINE)
        if not match:
            return None
        value = match.group(1).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        blob = Path(value)
        return blob if blob.is_absolute() and blob.parent.name == "blobs" else None

    def status(self, key):
        with self.lock:
            if key not in self.jobs:
                raise InstallError("Installation not found. Review the model again.")
            console = self.consoles.get(key)
            if console and console.poll() is not None and self.jobs[key]["state"] == "queued":
                self.cancel(key)
            return {k: v for k, v in self.jobs[key].items() if k not in {"cancel", "finished"}}

    def create_job(self, preview_id, console=True):
        with self.lock:
            if any(not j["finished"].is_set() for j in self.jobs.values()):
                raise InstallError("An installation is already open. Finish or cancel it first.")
            preview = self.previews.pop(preview_id, None)
            if not preview or time.time() - preview["created"] > 900:
                raise InstallError("This preview expired. Review the size and folder again.")
            directory(preview["directory"], self.project)
            if disk_free(preview["directory"]) < preview["required_bytes"]:
                raise InstallError("Free disk space changed. Review the installation again.")
            if len(self.jobs) >= 32:
                self.jobs.pop(next(iter(self.jobs)))
            key = secrets.token_hex(16)
            self.jobs[key] = {**preview, "id": key, "state": "queued", "message": "Opening Command Prompt", "completed": 0, "total": 0, "cancel": threading.Event(), "finished": threading.Event()}
        try:
            if console:
                self.open_console(key)
        except OSError as exc:
            self.jobs[key].update(state="failed", message="Command Prompt could not open. Retry the installation.")
            self.jobs[key]["finished"].set()
            raise InstallError(self.jobs[key]["message"]) from exc
        return self.status(key)

    def open_console(self, key):
        if os.name != "nt" or not self.server:
            raise OSError("The desktop console installer requires Windows and the DocuMind launcher.")
        # Model/path values are never interpolated into a shell command. A fixed
        # bootstrap calls argparse with a random hex job ID and a numeric port.
        folder = Path(tempfile.gettempdir()) / "DocuMind" / "model-installs"
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / (key + ".cmd")
        script.write_text('@echo off\nsetlocal DisableDelayedExpansion\ntitle DocuMind model installation\n"%DOCUMIND_PYTHON%" "%DOCUMIND_ROOT%\\documind_cli.py" models install --job-id ' + key + '\necho.\necho Run documind --help from the DocuMind folder for more commands.\n', encoding="utf-8")
        env = {**self.environment, "DOCUMIND_PYTHON": sys.executable, "DOCUMIND_ROOT": str(self.project), "DOCUMIND_INSTALL_SCRIPT": str(script), "DOCUMIND_MODEL_MANAGER_TOKEN": self.token, "DOCUMIND_MODEL_MANAGER_PORT": str(self.server.server_port), "PYTHONIOENCODING": "utf-8"}
        command = f'"{os.environ.get("COMSPEC", "cmd.exe")}" /d /s /k ""{script}""'
        self.consoles[key] = subprocess.Popen(command, cwd=self.project, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def cancel(self, key):
        with self.lock:
            if key not in self.jobs:
                raise InstallError("Installation not found.")
            job = self.jobs[key]
            job["cancel"].set()
            if job["state"] == "queued":
                job.update(state="cancelled", message="Cancelled before download started")
                job["finished"].set()
            elif job["state"] not in TERMINAL:
                job["message"] = "Cancelling installation; downloaded parts are retained"
        return self.status(key)

    def run(self, key):
        with self.lock:
            job = self.jobs.get(key)
            if not job or job["state"] != "queued":
                raise InstallError("This installation already started or was cancelled.")
            job.update(state="running", message="Preparing model installation")
        target = Path(job["directory"])
        def update(message, completed=0, total=0):
            with self.lock:
                job.update(message=message, completed=completed, total=total)
        try:
            target = directory(str(target), self.project)
            target.mkdir(parents=True, exist_ok=True)
            if job["restart_required"]:
                update("Preserving the existing model library")
                yield self.status(key)
                if self.active_root != target:
                    copy_library(self.active_root, target, job["cancel"], update)
                executable = shutil.which("ollama")
                if not executable:
                    raise InstallError("Ollama is not installed. Run Install_DocuMind.cmd first.")
                port = free_port()
                base = f"http://127.0.0.1:{port}"
                env = {**self.environment, "OLLAMA_MODELS": str(target), "OLLAMA_HOST": f"127.0.0.1:{port}", "OLLAMA_NO_CLOUD": "1"}
                self.transient = subprocess.Popen([executable, "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                for _ in range(100):
                    if job["cancel"].is_set():
                        raise InterruptedError("Installation cancelled.")
                    if self.transient.poll() is not None:
                        raise InstallError("The temporary Ollama server could not start.")
                    try:
                        read_json(base + "/api/version", timeout=1)
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise InstallError("The temporary Ollama server did not become ready.")
            else:
                base = self.base
            request = urllib.request.Request(base + "/api/pull", data=json.dumps({"model": job["model"], "stream": True}).encode(), headers={"Content-Type": "application/json"})
            success = False
            with LOCAL.open(request, timeout=30) as response:
                while line := response.readline(1_000_001):
                    if job["cancel"].is_set():
                        raise InterruptedError("Installation cancelled. Retry to resume downloaded parts.")
                    if len(line) > 1_000_000:
                        raise InstallError("Invalid model download progress response.")
                    row = json.loads(line)
                    if row.get("error"):
                        raise InstallError("Ollama could not download this model. Check your connection and retry to resume.")
                    update(str(row.get("status", "Downloading"))[:200], max(0, int(row.get("completed", 0))), max(0, int(row.get("total", 0))))
                    success = row.get("status") == "success"
                    yield self.status(key)
            if not success:
                raise InstallError("The download ended before verification finished. Retry to resume.")
            names = {r["name"] for r in read_json(base + "/api/tags").get("models", [])}
            if job["model"] not in names:
                raise InstallError("Ollama did not report the model as installed. Retry installation.")
            from setup_documind import update_environment
            update_environment(self.project / ".env", {"DOCUMIND_MODEL_DIRECTORY": str(target)})
            self.default_root = target
            job.update(state="completed", message="Installed. Restart DocuMind to use the new library folder." if job["restart_required"] else "Installed and ready to select")
            yield self.status(key)
        except (GeneratorExit, BrokenPipeError, ConnectionResetError):
            if job["state"] not in TERMINAL:
                job.update(state="cancelled", message="Console closed. Retry to resume downloaded parts.")
            raise
        except (OSError, ValueError, KeyError) as exc:
            job.update(state="cancelled" if isinstance(exc, InterruptedError) else "failed", message=str(exc) if isinstance(exc, (InstallError, InterruptedError)) else "Installation interrupted. Check Ollama and your connection, then retry to resume.")
            yield self.status(key)
        finally:
            stop_owned(self.transient)
            self.transient = None
            job["finished"].set()

    def start(self):
        manager = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # No request bodies, bearer tokens or file paths in logs.

            def respond(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

            def dispatch(self):
                if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + manager.token):
                    self.respond(403, {"detail": "Local installer authorization required."}); return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 4096:
                        raise InstallError("Installation request is too large.")
                    data = json.loads(self.rfile.read(size)) if size else {}
                    path = self.path.strip("/").split("/")
                    if self.command == "GET" and path == ["catalog"]:
                        self.respond(200, manager.catalogue())
                    elif self.command == "POST" and path == ["preview"]:
                        self.respond(200, manager.preview(data.get("model"), data.get("directory")))
                    elif self.command == "POST" and path == ["install"]:
                        self.respond(202, manager.create_job(data.get("preview_id")))
                    elif len(path) >= 2 and path[0] == "jobs" and re.fullmatch("[a-f0-9]{32}", path[1]):
                        key = path[1]
                        if self.command == "GET" and len(path) == 2:
                            self.respond(200, manager.status(key))
                        elif self.command == "POST" and path[2:] == ["cancel"]:
                            self.respond(200, manager.cancel(key))
                        elif self.command == "POST" and path[2:] == ["run"]:
                            manager.status(key)
                            stream = manager.run(key)
                            first = next(stream)  # Validate/claim before sending HTTP headers.
                            self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
                            try:
                                for row in itertools.chain((first,), stream):
                                    self.wfile.write(json.dumps(row).encode() + b"\n"); self.wfile.flush()
                            finally:
                                stream.close()
                        else:
                            self.respond(404, {"detail": "Route not found"})
                    else:
                        self.respond(404, {"detail": "Route not found"})
                except (ValueError, KeyError, TypeError) as exc:
                    self.respond(422, {"detail": str(exc) if isinstance(exc, InstallError) else "Invalid installer request."})
                except (OSError, BrokenPipeError):
                    pass

            do_GET = dispatch
            do_POST = dispatch
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return {"DOCUMIND_MODEL_MANAGER_PORT": str(self.server.server_port), "DOCUMIND_MODEL_MANAGER_TOKEN": self.token}

    def close(self):
        for key in list(self.jobs):
            self.cancel(key)
        stop_owned(self.transient)
        if self.server:
            self.server.shutdown()
            self.server.server_close()
