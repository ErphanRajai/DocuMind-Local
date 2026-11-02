"""Resumable Windows setup. Standard library only; never prints .env contents."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent
CHAT_MODEL = 'qwen3:4b-instruct-2507-q4_K_M'
EMBED_MODEL = 'bge-m3'


def ensure_frontend_closed():
    if os.name != 'nt': return
    script = "$root=[IO.Path]::GetFullPath($env:DOCUMIND_SETUP_ROOT)+'\\'; Get-Process node -ErrorAction SilentlyContinue | ForEach-Object { $p=$_; try { if($p.Modules | Where-Object { $_.FileName.StartsWith($root,[StringComparison]::OrdinalIgnoreCase) }) { $p.Id } } catch {} }"
    check = subprocess.run(['powershell.exe','-NoProfile','-Command',script], env={**os.environ,'DOCUMIND_SETUP_ROOT':str(ROOT/'documind-web')}, capture_output=True, text=True)
    if check.stdout.strip():
        raise RuntimeError('Close running DocuMind windows and project Node/test processes before setup, then rerun it. Windows has locked the interface library. Setup will not terminate your processes automatically.')


def choose_ollama_port(environment):
    preferred = int(environment.get('DOCUMIND_OLLAMA_PORT','11434'))
    if not 1 <= preferred <= 65535: raise RuntimeError('DOCUMIND_OLLAMA_PORT must be between 1 and 65535.')
    for port in dict.fromkeys([preferred,*range(21434,21444)]):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/version',timeout=1) as response:
                if json.load(response).get('version'): return port
        except (OSError,ValueError): pass
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            if os.name=='nt': probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try: probe.bind(('127.0.0.1',port))
            except OSError: continue
        return port
    raise RuntimeError('No local Ollama port is available. Close an unused local model server and rerun setup.')


def run(command, cwd=ROOT, environment=None):
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def update_environment(path, changes):
    """Replace only owned keys; preserve credentials, comments and unrelated settings."""
    rows = path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []
    remaining = dict(changes)
    result = []
    for row in rows:
        key = row.split('=', 1)[0].strip() if '=' in row and not row.lstrip().startswith('#') else ''
        if key in changes:
            if key in remaining: result.append(f'{key}={remaining.pop(key)}')
        else: result.append(row)
    result.extend(f'{key}={value}' for key, value in remaining.items())
    temporary = path.with_suffix('.setup.tmp')
    temporary.write_text('\n'.join(result) + '\n', encoding='utf-8')
    temporary.replace(path)


def pull_model(base, model):
    request = urllib.request.Request(base + '/api/pull', data=json.dumps({'model': model, 'stream': True}).encode(), headers={'Content-Type':'application/json'})
    last = None
    with urllib.request.urlopen(request, timeout=3600) as response:
        for line in response:
            row = json.loads(line)
            if row.get('error'): raise RuntimeError(row['error'])
            percent = int(100 * row.get('completed', 0) / row['total']) if row.get('total') else None
            progress = (row.get('status'), percent)
            if progress != last:
                print(f"{model}: {row.get('status', '')}" + (f' {percent}%' if percent is not None else ''), flush=True)
                last = progress
    if not last or last[0] != 'success': raise RuntimeError(f'{model} download did not finish successfully. Run setup again to resume.')


def main():
    parser = argparse.ArgumentParser(description='Install and verify the local DocuMind workspace.')
    parser.add_argument('--check', action='store_true', help='Read-only prerequisite report; no downloads or changes.')
    args = parser.parse_args()
    required = {'Docker':'docker', 'Ollama':'ollama', 'Node.js':'node', 'npm':'npm.cmd' if os.name == 'nt' else 'npm'}
    found = {name:shutil.which(executable) for name, executable in required.items()}
    report = {name:'found' if value else 'missing' for name,value in found.items()}
    engine = subprocess.run(['docker','info','--format','{{.ServerVersion}}'], capture_output=True) if found['Docker'] else None
    report['Docker engine'] = 'ready' if engine and engine.returncode == 0 else 'not ready: start Docker Desktop and finish its first-run setup'
    report['Python'] = sys.version.split()[0]
    report['Free disk GB'] = round(shutil.disk_usage(ROOT).free / 2**30, 1)
    import launcher
    base = 'http://' + launcher.ollama_environment(launcher.ENVIRONMENT)['OLLAMA_HOST']
    installed = []
    try:
        with urllib.request.urlopen(base + '/api/tags', timeout=3) as response:
            installed = [row['name'] for row in json.load(response).get('models',[])]
    except OSError: pass
    for model in (CHAT_MODEL, EMBED_MODEL):
        report[model] = 'installed' if model in installed or model+':latest' in installed else 'download needed'
    report['Frontend build'] = 'ready' if (ROOT/'documind-web'/'.next'/'BUILD_ID').is_file() else 'build needed'
    report['Setup verification'] = 'complete' if (ROOT/'.venv'/'setup-ready.json').is_file() else 'setup needed'
    print(json.dumps(report, indent=2))
    if args.check: return 0 if all(found.values()) and engine and engine.returncode == 0 and all(report[m]=='installed' for m in (CHAT_MODEL,EMBED_MODEL)) and report['Setup verification']=='complete' and report['Frontend build']=='ready' else 1
    if not all(found.values()): raise RuntimeError('Run Install_DocuMind.cmd to install missing prerequisites.')
    if not engine or engine.returncode != 0: raise RuntimeError('Docker is not ready. Finish Docker Desktop first-run/WSL setup, reboot if requested, then rerun this installer. Existing progress is retained.')
    ensure_frontend_closed()
    if shutil.disk_usage(ROOT).free < 10 * 2**30: raise RuntimeError('Allow at least 10 GB free for models, dependencies and the Docker image.')
    port = choose_ollama_port(launcher.ENVIRONMENT)
    launcher.ENVIRONMENT['DOCUMIND_OLLAMA_PORT'] = str(port)
    update_environment(ROOT/'.env', {'DOCUMIND_OLLAMA_PORT':str(port)})
    owned = launcher.start_ollama_if_needed()
    base = 'http://' + launcher.ollama_environment(launcher.ENVIRONMENT)['OLLAMA_HOST']
    # Pull is resumable; Ollama verifies model blobs. No document leaves this computer.
    for model in (CHAT_MODEL, EMBED_MODEL): pull_model(base, model)
    changes = {'DOCUMIND_OLLAMA_PORT':str(port), 'OLLAMA_CHAT_MODEL':CHAT_MODEL, 'OLLAMA_EMBED_MODEL':EMBED_MODEL,
               'EMBED_VECTOR_DIM':'1024', 'DOCUMIND_QDRANT_COLLECTION':'pdf_chunks_bge_m3_1024',
               'DOCUMIND_LOCAL_ONLY':'1', 'DOCUMIND_UI':'next'}
    update_environment(ROOT / '.env', changes)
    environment = {**launcher.ENVIRONMENT, **changes}
    run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-launcher.txt'])
    npm = found['npm']
    run([npm, 'ci'], ROOT/'documind-web')
    run([npm, 'run', 'build'], ROOT/'documind-web')
    run(['docker','compose','build','pdf_backend'], environment=environment)
    # Cache small CPU retrieval assets now. Runtime uses offline mode and never fetches them.
    warmup = "from fastembed import SparseTextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; a=SparseTextEmbedding(model_name='Qdrant/bm25',cache_dir='/workspace/db_data/model_cache'); b=TextCrossEncoder(model_name='Xenova/ms-marco-MiniLM-L-6-v2',cache_dir='/workspace/db_data/model_cache'); list(a.embed(['setup check'])); list(b.rerank('setup check',['setup check']))"
    run(['docker','compose','run','--rm','--no-deps','-e','HF_HUB_OFFLINE=0','pdf_backend','python','-c',warmup], environment=environment)
    run(['docker','compose','up','-d','pdf_backend'], environment=environment)
    if not launcher.wait_for_url(launcher.BACKEND_URL + '/healthz', timeout=90): raise RuntimeError('The backend did not become ready. Run docker compose logs pdf_backend, then rerun setup.')
    with urllib.request.urlopen(launcher.BACKEND_URL + '/healthz', timeout=15) as response:
        health = json.load(response)
    if health.get('status') != 'healthy': raise RuntimeError('A local service is unavailable: ' + json.dumps(health))
    (ROOT/'.venv'/'setup-ready.json').write_text(json.dumps({'version':1,'chat_model':CHAT_MODEL,'embedding_model':EMBED_MODEL,
        'frontend_build':(ROOT/'documind-web'/'.next'/'BUILD_ID').read_text().strip()}, indent=2), encoding='utf-8')
    print('\nSetup complete. Double-click Start_DocuMind.bat. Internet is no longer needed for installed models and cached retrieval assets.')
    print('Optional vision/Docling models are separate; the core text/PDF exam workflow is ready.')
    # An Ollama server started here stays available for the launcher; never stop an existing server.
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f'\nSetup incomplete: {exc}\nRerun Install_DocuMind.cmd after fixing the issue. Your documents and downloaded model blobs are preserved.', file=sys.stderr)
        raise SystemExit(1)
