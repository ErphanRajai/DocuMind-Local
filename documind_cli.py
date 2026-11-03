"""DocuMind command-line interface; model operations use the host installer."""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from model_installation import InstallError, LOCAL, ModelManager, TERMINAL


def size(value):
    return f"{value / 1024**3:.2f} GiB"


def parser():
    root = argparse.ArgumentParser(prog="documind", description="Manage DocuMind's local model library. Downloads require internet; answering stays local.")
    groups = root.add_subparsers(dest="command", required=True)
    models = groups.add_parser("models", help="List, review and install Ollama answer models")
    commands = models.add_subparsers(dest="action", required=True)
    commands.add_parser("list", help="Show installed and downloadable models")
    info = commands.add_parser("info", help="Preview size, destination and free space without downloading")
    info.add_argument("model")
    info.add_argument("--directory", help="Absolute model-library folder")
    install = commands.add_parser("install", help="Review and download a model with resumable Ollama progress")
    install.add_argument("model", nargs="?")
    install.add_argument("--directory", help="Absolute model-library folder; a new folder requires app restart")
    install.add_argument("--yes", action="store_true", help="Accept the printed size/folder review")
    install.add_argument("--job-id", help=argparse.SUPPRESS)
    return root


def describe(row):
    print(f"\nModel: {row['model']}\nModel files: {size(row['model_bytes'])}\nDownload up to: {size(row['download_bytes'])}\nDestination: {row['directory']}\nFree space: {size(row['free_bytes'])}")
    if row["restart_required"]:
        print(f"Existing library copy: {size(row['copy_bytes'])}\nThe old library is preserved. Restart DocuMind after installation to switch folders.")


def progress(row):
    suffix = f" | {size(row['completed'])} / {size(row['total'])} ({min(100, int(100 * row['completed'] / row['total']))}%)" if row.get("total") else ""
    print(row.get("message", "Working") + suffix, flush=True)


def from_desktop(key):
    import re
    if not re.fullmatch("[a-f0-9]{32}", key):
        raise InstallError("Invalid desktop installation ID.")
    port = int(os.environ.get("DOCUMIND_MODEL_MANAGER_PORT", "0"))
    token = os.environ.get("DOCUMIND_MODEL_MANAGER_TOKEN", "")
    if not 1 <= port <= 65535 or not token:
        raise InstallError("Open installation from DocuMind, or use documind models install MODEL.")
    base = f"http://127.0.0.1:{port}/jobs/{key}"
    headers = {"Authorization": "Bearer " + token}
    with LOCAL.open(urllib.request.Request(base, headers=headers), timeout=10) as response:
        describe(json.load(response))
    terminal = None
    try:
        with LOCAL.open(urllib.request.Request(base + "/run", data=b"{}", headers=headers), timeout=120) as response:
            for line in response:
                row = json.loads(line)
                progress(row)
                if row.get("state") in TERMINAL:
                    terminal = row
    except KeyboardInterrupt:
        with LOCAL.open(urllib.request.Request(base + "/cancel", data=b"{}", headers=headers), timeout=10):
            pass
        print("Cancelled. Reopen installation to resume downloaded parts.")
        return 130
    if not terminal or terminal["state"] != "completed":
        print("Installation did not complete. Retry in DocuMind to resume.")
        return 1
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == "install" and args.job_id:
        return from_desktop(args.job_id)
    import launcher
    manager = ModelManager(Path(__file__).resolve().parent, launcher.load_project_environment())
    if args.action == "list":
        value = manager.catalogue()
        print("Model library: " + value["directory"])
        if not value["ollama_available"]:
            print("Ollama is unavailable; installed status cannot be confirmed.")
        for row in value["models"]:
            print(f"{row['name']}: {'installed' if row['installed'] else 'not installed'}")
        return 0
    if not args.model:
        raise InstallError("Specify a model. Run documind models install --help.")
    row = manager.preview(args.model, args.directory or str(manager.active_root))
    describe(row)
    if args.action == "info":
        return 0
    if not args.yes and input("\nProceed with this download? [y/N] ").strip().lower() != "y":
        print("No download started.")
        return 0
    key = manager.create_job(row["id"], console=False)["id"]
    result = None
    stream = manager.run(key)
    try:
        for result in stream:
            progress(result)
    except KeyboardInterrupt:
        manager.cancel(key)
        print("Cancelled. Run the same command to resume.")
        return 130
    finally:
        stream.close()
    return 0 if result and result["state"] == "completed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc) if isinstance(exc, InstallError) else "The local installer could not connect. Start DocuMind/Ollama and retry.", file=sys.stderr)
        raise SystemExit(1)
