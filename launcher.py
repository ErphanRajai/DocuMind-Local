"""Start the local DocuMind stack and open its desktop window."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_project_environment() -> dict[str, str]:
    environment = os.environ.copy()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                environment.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return environment


ENVIRONMENT = load_project_environment()
BACKEND_URL = ENVIRONMENT.get("DOCUMIND_BACKEND_URL", "http://127.0.0.1:8888")
UI_MODE = ENVIRONMENT.get("DOCUMIND_UI", "next")
FRONTEND_URL = ENVIRONMENT.get("DOCUMIND_FRONTEND_URL", "http://127.0.0.1:8501" if UI_MODE == "classic" else "http://127.0.0.1:4317")


def frontend_address(url: str):
    address = urlparse(url)
    if address.scheme != "http" or address.hostname not in {"127.0.0.1", "localhost"} or not address.port:
        raise ValueError("DOCUMIND_FRONTEND_URL must be a local HTTP URL with a port.")
    return address


def choose_frontend_url(preferred: str) -> str:
    """Windows can reserve a port even when no process is listening on it."""
    address = frontend_address(preferred)
    for port in dict.fromkeys([address.port, *range(4400, 4410)]):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return address._replace(netloc=f"127.0.0.1:{port}").geturl()
    raise RuntimeError("No frontend port is available. Close an unused DocuMind window or choose a free DOCUMIND_FRONTEND_URL port.")


def frontend_command(url: str | None = None):
    """Use a direct Node process so shutdown owns the actual Next server."""
    address = frontend_address(url or FRONTEND_URL)
    if UI_MODE == "classic":
        return [sys.executable, "-m", "streamlit", "run", str(ROOT / "pdf-summarizer-frontend" / "app.py"),
                "--server.headless=true", "--server.address=127.0.0.1", f"--server.port={address.port}", "--browser.gatherUsageStats=false"], ROOT
    node = shutil.which("node")
    web_root = ROOT / "documind-web"
    cli = web_root / "node_modules" / "next" / "dist" / "bin" / "next"
    if not node or not cli.is_file() or not (web_root / ".next" / "BUILD_ID").is_file():
        raise RuntimeError("Build the new interface first: cd documind-web; npm ci; npm run build. Or set DOCUMIND_UI=classic.")
    return [node, str(cli), "start", "--hostname", "127.0.0.1", "--port", str(address.port)], web_root


def wait_for_url(url: str, timeout: int = 300, process: subprocess.Popen | None = None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    return False


def ollama_environment(environment: dict[str, str]) -> dict[str, str]:
    """Keep application GPU settings scoped to the server process we own."""
    result = environment.copy()
    port = int(environment.get("DOCUMIND_OLLAMA_PORT", "11434"))
    if not 1 <= port <= 65535:
        raise ValueError("DOCUMIND_OLLAMA_PORT must be between 1 and 65535")
    cache_type = environment.get("DOCUMIND_OLLAMA_KV_CACHE_TYPE", "f16")
    if cache_type not in {"f16", "q8_0"}:
        raise ValueError("DOCUMIND_OLLAMA_KV_CACHE_TYPE must be f16 or q8_0")
    result.update(
        OLLAMA_HOST=f"127.0.0.1:{port}", OLLAMA_CONTEXT_LENGTH="8192",
        OLLAMA_KEEP_ALIVE="15m", OLLAMA_NUM_PARALLEL="1",
        OLLAMA_FLASH_ATTENTION=environment.get("DOCUMIND_OLLAMA_FLASH_ATTENTION", "1"),
        OLLAMA_KV_CACHE_TYPE=cache_type,
    )
    return result


def start_ollama_if_needed() -> subprocess.Popen | None:
    environment = ollama_environment(ENVIRONMENT)
    url = f"http://{environment['OLLAMA_HOST']}/api/version"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                return None  # Never restart a server started by another app.
    except (OSError, urllib.error.URLError):
        pass
    executable = shutil.which("ollama")
    if executable is None:
        print("Ollama was not found. Start or install Ollama to use local models and document search.")
        return None
    log_directory = Path(tempfile.gettempdir()) / "DocuMind"
    log_directory.mkdir(parents=True, exist_ok=True)
    print("Starting local Ollama with DocuMind's GPU settings...")
    with (log_directory / "ollama.log").open("ab") as log:
        process = subprocess.Popen(
            [executable, "serve"], env=environment, cwd=ROOT,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    if not wait_for_url(url, timeout=30):
        print(f"Ollama did not become ready. Check {log_directory / 'ollama.log'}")
    return process


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def stop_owned_ollama(process: subprocess.Popen | None) -> None:
    """Only a server started by this launcher is eligible for tree shutdown."""
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        # terminate() alone leaves llama-server.exe children holding GPU memory.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            stop_process(process)
    else:
        stop_process(process)


def main() -> int:
    compose = ["docker", "compose"]
    if shutil.which("docker") is None:
        print("Docker was not found. Install and start Docker Desktop, then try again.")
        return 1
    if subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True).returncode != 0:
        print("Docker is not responding. Start Docker Desktop and try again.")
        return 1

    print("Starting DocuMind services. The first launch may take a few minutes...")
    ollama_process = start_ollama_if_needed()
    result = subprocess.run(compose + ["up", "-d", "--build"], cwd=ROOT, env=ENVIRONMENT)
    if result.returncode != 0:
        stop_owned_ollama(ollama_process)
        print("Could not start the backend. Check that Docker Desktop is running.")
        return result.returncode

    if not wait_for_url(f"{BACKEND_URL}/healthz"):
        stop_owned_ollama(ollama_process)
        print("The backend did not become ready. Review the Docker logs with: docker compose logs -f")
        return 1

    frontend = None
    try:
        frontend_url = choose_frontend_url(FRONTEND_URL)
        if frontend_url != FRONTEND_URL:
            print(f"The configured frontend port is unavailable; using {frontend_url}")
        command, frontend_cwd = frontend_command(frontend_url)
        frontend = subprocess.Popen(
            command,
            cwd=frontend_cwd,
            env=ENVIRONMENT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if not wait_for_url(frontend_url, process=frontend):
            print(f"The interface did not start at {frontend_url}. Check its startup error above before trying again.")
            return 1

        print(f"DocuMind is ready at {frontend_url}")
        try:
            import webview

            webview.create_window(
                title="DocuMind Local AI Workspace",
                url=frontend_url,
                width=1360,
                height=900,
                min_size=(960, 640),
                text_select=True,
                zoomable=True,
            )
            webview.start()
        except Exception as exc:
            print(f"Desktop view unavailable ({exc}); opening DocuMind in your browser instead.")
            import webbrowser

            webbrowser.open(frontend_url)
            frontend.wait()
    except KeyboardInterrupt:
        print("Stopping DocuMind...")
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    finally:
        stop_process(frontend)
        subprocess.run(compose + ["down"], cwd=ROOT, env=ENVIRONMENT, check=False, capture_output=True)
        stop_owned_ollama(ollama_process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
