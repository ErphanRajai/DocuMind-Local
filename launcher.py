"""Start the local DocuMind stack and open its desktop window."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
FRONTEND_URL = ENVIRONMENT.get("DOCUMIND_FRONTEND_URL", "http://127.0.0.1:8501")


def wait_for_url(url: str, timeout: int = 300) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    return False


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    compose = ["docker", "compose"]
    if shutil.which("docker") is None:
        print("Docker was not found. Install and start Docker Desktop, then try again.")
        return 1
    if subprocess.run(["docker", "--version"], capture_output=True).returncode != 0:
        print("Docker is not responding. Start Docker Desktop and try again.")
        return 1

    print("Starting DocuMind services. The first launch may take a few minutes...")
    result = subprocess.run(compose + ["up", "-d", "--build"], cwd=ROOT, env=ENVIRONMENT)
    if result.returncode != 0:
        print("Could not start the backend. Check that Docker Desktop is running.")
        return result.returncode

    if not wait_for_url(f"{BACKEND_URL}/healthz"):
        print("The backend did not become ready. Review the Docker logs with: docker compose logs -f")
        return 1

    frontend = None
    try:
        frontend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "pdf-summarizer-frontend" / "app.py"),
                "--server.headless=true",
                "--server.address=127.0.0.1",
                "--server.port=8501",
                "--browser.gatherUsageStats=false",
            ],
            cwd=ROOT,
            env=ENVIRONMENT,
        )

        if not wait_for_url(FRONTEND_URL):
            print("The interface did not start. Check the Python environment and frontend requirements.")
            return 1

        print(f"DocuMind is ready at {FRONTEND_URL}")
        try:
            import webview

            webview.create_window(
                title="DocuMind Local AI Workspace",
                url=FRONTEND_URL,
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

            webbrowser.open(FRONTEND_URL)
            frontend.wait()
    except KeyboardInterrupt:
        print("Stopping DocuMind...")
    finally:
        stop_process(frontend)
        subprocess.run(compose + ["down"], cwd=ROOT, env=ENVIRONMENT, check=False, capture_output=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
