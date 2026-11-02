"""Prepare a Windows x64 transfer folder; no private work or live settings copied."""
import argparse,hashlib,json,os,shutil,subprocess,sys,urllib.request,stat
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODELS={'qwen3:4b-instruct-2507-q4_K_M','bge-m3:latest'}

def run(args,**kwargs):subprocess.run(args,check=True,**kwargs)
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def copy(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.is_symlink():raise ValueError('Bundle destination cannot contain symlink files.')
    if not destination.exists() or source.stat().st_size!=destination.stat().st_size or digest(source)!=digest(destination):
        if destination.exists():destination.chmod(stat.S_IREAD|stat.S_IWRITE)
        shutil.copy2(source,destination)
def source_files():
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    for name in sorted(set(filter(None,paths))):
        if name.startswith(('.git/','.impeccable/','output/','db_data/','uploaded_pdfs/','ollama_storage/','qdrant_storage/')) or (Path(name).name.startswith('.env') and Path(name).name!='.env.example') or name in {'.npmrc'}:continue
        yield name
def copy_model(root,destination,model):
    name,tag=model.split(':',1)
    relative=Path('manifests/registry.ollama.ai/library')/name/tag
    manifest=root/relative
    value=json.loads(manifest.read_text())
    copy(manifest,destination/relative)
    for layer in [value['config'],*value['layers']]:
        key=layer['digest']
        import re
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',key):raise ValueError('Invalid model blob digest.')
        source=root/'blobs'/key.replace(':','-')
        if digest(source)!=key.split(':')[1]:raise ValueError('Model blob checksum mismatch.')
        copy(source,destination/'blobs'/source.name)
def download(url,path):
    if path.exists():return
    print('Downloading prerequisite:',path.name,flush=True)
    path.parent.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(url,timeout=120) as response, path.with_suffix('.part').open('wb') as out:shutil.copyfileobj(response,out)
    path.with_suffix('.part').replace(path)

def export_images(target):
    code=[ROOT/'pdf-summarizer-backend/Dockerfile',ROOT/'pdf-summarizer-backend/requirements.txt',*sorted((ROOT/'pdf-summarizer-backend/app').rglob('*.py'))]
    image='documind-offline-backend:'+hashlib.sha256(b''.join(p.read_bytes() for p in code)).hexdigest()[:12]
    run(['docker','build','-t',image,'-f',str(ROOT/'pdf-summarizer-backend/Dockerfile'),str(ROOT/'pdf-summarizer-backend')])
    run(['docker','image','save','-o',str(target/'containers.tar'),image,'qdrant/qdrant:latest'])
    return image

def refresh_code(target):
    """Retain immutable-asset hashes so changes to model/runtime files still fail verification."""
    if not target.is_relative_to(ROOT/'output') or (target/'app/.env').exists():raise ValueError('Code refresh requires an unused generated output bundle.')
    manifest=json.loads((target/'bundle.json').read_text())
    if manifest.get('format')!='documind-offline-1':raise ValueError('Unsupported bundle.')
    for name in source_files():
        source=ROOT/name;destination=target/'app'/name;copy(source,destination)
        manifest['files'][str(destination.relative_to(target)).replace('\\','/')]=digest(source)
    for source in (ROOT/'documind-web/.next').rglob('*'):
        if not source.is_file() or 'cache' in source.relative_to(ROOT/'documind-web/.next').parts:continue
        destination=target/'app'/source.relative_to(ROOT);copy(source,destination)
        manifest['files'][str(destination.relative_to(target)).replace('\\','/')]=digest(source)
    manifest['image']=export_images(target)
    copy(ROOT/'scripts/install-offline.ps1',target/'install-offline.ps1')
    for name in ['containers.tar','install-offline.ps1']:manifest['files'][name]=digest(target/name)
    (target/'bundle.json').write_text(json.dumps(manifest,indent=2))
    print('Code refreshed; run install-offline.ps1 -CheckOnly to verify every immutable asset.',flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'output/offline-bundle');parser.add_argument('--models-root',type=Path,default=Path(os.getenv('OLLAMA_MODELS',str(Path.home()/'.ollama/models'))));parser.add_argument('--download-prerequisites',action='store_true');parser.add_argument('--refresh',action='store_true');parser.add_argument('--refresh-code',action='store_true');args=parser.parse_args()
    target=args.output.resolve()
    if target==ROOT or ROOT.is_relative_to(target):raise ValueError('Choose a separate output directory, not the project or its parent.')
    if args.refresh_code:refresh_code(target);return
    target.mkdir(parents=True,exist_ok=True)
    if (target/'bundle.json').exists():
        if not args.refresh:raise ValueError('Use a new output folder, or --refresh your existing generated bundle.')
        if not target.is_relative_to(ROOT/'output') or json.loads((target/'bundle.json').read_text()).get('format')!='documind-offline-1':raise ValueError('Refresh is restricted to generated project output bundles.')
        (target/'bundle.json').unlink()
    if shutil.disk_usage(target).free<20*2**30:raise ValueError('Allow 20 GB free for the transfer folder.')
    app=target/'app';app.mkdir(exist_ok=True)
    for name in source_files():copy(ROOT/name,app/name)
    for folder in ['documind-web/.next','documind-web/node_modules','db_data/model_cache']:
        print('Copying local assets:',folder,flush=True)
        if not (ROOT/folder).is_dir():raise ValueError('Complete normal setup/build before bundling: '+folder)
        shutil.copytree(ROOT/folder,app/folder,dirs_exist_ok=True,copy_function=lambda a,b:copy(Path(a),Path(b)),ignore=shutil.ignore_patterns('cache','*.log') if folder.endswith('.next') else None)
    node=Path(shutil.which('node') or '').parent
    ollama=Path(shutil.which('ollama') or '').parent
    if not (node/'node.exe').is_file() or not (ollama/'ollama.exe').is_file():raise ValueError('Build on the configured Windows x64 installation.')
    print('Copying Node runtime',flush=True)
    shutil.copytree(node,app/'runtime/node',dirs_exist_ok=True,copy_function=lambda a,b:copy(Path(a),Path(b)))
    print('Copying Ollama runtime',flush=True)
    shutil.copytree(ollama,app/'runtime/ollama',dirs_exist_ok=True,copy_function=lambda a,b:copy(Path(a),Path(b)))
    for model in sorted(MODELS):print('Copying verified model',model,flush=True);copy_model(args.models_root,app/'runtime/models',model)
    run([sys.executable,'-m','pip','wheel','--wheel-dir',str(target/'wheels'),'-r',str(ROOT/'requirements-launcher.txt')])
    image=export_images(target)
    version=sys.version.split()[0]
    if args.download_prerequisites:
        download(f'https://www.python.org/ftp/python/{version}/python-{version}-amd64.exe',target/'prerequisites/python.exe')
        download('https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe',target/'prerequisites/docker.exe')
        # WSL's offline MSI; Windows features, virtualization and reboot remain vendor prerequisites.
        with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/microsoft/WSL/releases/latest',headers={'User-Agent':'DocuMind-bundle'}),timeout=30) as r:release=json.load(r)
        asset=next(a for a in release['assets'] if a['name'].endswith('.x64.msi'))
        download(asset['browser_download_url'],target/'prerequisites/wsl.msi')
    for name in ['python.exe','docker.exe','wsl.msi']:
        path=target/'prerequisites'/name
        if not path.is_file():raise ValueError('A complete bundle requires prerequisites; rerun with --download-prerequisites.')
        script="$ErrorActionPreference='Stop'; Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1'); $s=Get-AuthenticodeSignature -LiteralPath $env:DOCUMIND_VENDOR_FILE; if($s.Status -ne 'Valid'){exit 1}"
        security_environment={k:v for k,v in os.environ.items() if k.upper()!='PSMODULEPATH'}
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],env={**security_environment,'DOCUMIND_VENDOR_FILE':str(path)})
    copy(ROOT/'scripts/install-offline.ps1',target/'install-offline.ps1')
    (target/'Install_Offline.cmd').write_text('@echo off\ncd /d "%~dp0"\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-offline.ps1"\npause\n')
    (target/'README.txt').write_text('DocuMind Windows x64 offline transfer folder\nCopy this entire folder to a permanent local location before installation.\nRun Install_Offline.cmd. Vendor prompts, supported Windows, virtualization/WSL features and possible reboot remain prerequisites.\nThen run app/Start_DocuMind.bat. Do not move the folder after installation.\nNo private PDFs, database, credentials or live .env settings are included.\nModels and dependencies retain their original licenses. The bundle manifest checks integrity, not publisher identity.\n',encoding='utf-8')
    print('Hashing bundle manifest',flush=True)
    (target/'bundle.json').write_text(json.dumps({'format':'documind-offline-1','platform':'windows-x64','python':version,'image':image,'models':sorted(MODELS),'files':{str(p.relative_to(target)).replace('\\','/'):digest(p) for p in sorted(target.rglob('*')) if p.is_file()}},indent=2))
    print('Complete transfer folder:',target,flush=True)
if __name__=='__main__':main()
