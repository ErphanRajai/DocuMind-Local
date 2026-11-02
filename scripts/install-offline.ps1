param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -Force
$bundleRoot=$PSScriptRoot
$manifest=Get-Content -LiteralPath (Join-Path $bundleRoot 'bundle.json') -Raw | ConvertFrom-Json
if($manifest.format -ne 'documind-offline-1'){throw 'Unsupported bundle format'}
Write-Host 'Verifying all bundle files. No downloads are performed.'
foreach($entry in $manifest.files.PSObject.Properties){
 $path=[IO.Path]::GetFullPath((Join-Path $bundleRoot $entry.Name))
 if(-not $path.StartsWith([IO.Path]::GetFullPath($bundleRoot)+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe manifest path'}
 if(-not (Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){throw "Bundle checksum mismatch: $($entry.Name)"}
}
if($CheckOnly){Write-Host 'Bundle integrity verified.';exit 0}
foreach($name in @('python.exe','docker.exe','wsl.msi')){if((Get-AuthenticodeSignature -LiteralPath (Join-Path $bundleRoot "prerequisites/$name")).Status -ne 'Valid'){throw "Untrusted prerequisite: $name"}}
$pythonMinor=($manifest.python.Split('.')[0..1] -join '.')
$pythonReady=$false
if(Get-Command py -ErrorAction SilentlyContinue){& py "-$pythonMinor" -V; $pythonReady=($LASTEXITCODE -eq 0)}
if(-not $pythonReady){Start-Process -FilePath (Join-Path $bundleRoot 'prerequisites/python.exe') -ArgumentList @('/passive','InstallAllUsers=0','Include_launcher=1','Include_test=0') -Wait -WindowStyle Hidden}
$env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')
if(-not(Get-Command docker -ErrorAction SilentlyContinue)){
 Write-Host 'Install WSL and Docker from the included vendor installers. Complete any feature/reboot prompts, then rerun this file.'
 Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i',('"'+(Join-Path $bundleRoot 'prerequisites/wsl.msi')+'"')) -Wait -WindowStyle Hidden
 Start-Process -FilePath (Join-Path $bundleRoot 'prerequisites/docker.exe') -Wait -WindowStyle Hidden
 throw 'Finish Docker first-run setup, restart if required, and rerun offline installation.'
}
& docker info --format '{{.ServerVersion}}'
if($LASTEXITCODE -ne 0){throw 'Start Docker Desktop and finish WSL/virtualization setup, then rerun. No files will be downloaded by this script.'}
$appRoot=Join-Path $bundleRoot 'app'
Set-Location -LiteralPath $appRoot
if(Test-Path -LiteralPath '.env'){throw 'Offline installation is already configured. Use Start_DocuMind.bat; do not overwrite live settings.'}
& py "-$pythonMinor" -m venv .venv
if($LASTEXITCODE -ne 0){throw 'Could not create Python environment. Reopen the installer after installing Python.'}
& .venv/Scripts/python.exe -m pip install --no-index --find-links (Join-Path $bundleRoot 'wheels') -r requirements-launcher.txt
if($LASTEXITCODE -ne 0){throw 'Offline wheel installation failed'}
& docker image load -i (Join-Path $bundleRoot 'containers.tar')
if($LASTEXITCODE -ne 0){throw 'Could not load bundled container images'}
$settings=@"
DOCUMIND_UI=next
DOCUMIND_LOCAL_ONLY=1
DOCUMIND_OFFLINE_BUNDLE=1
DOCUMIND_BACKEND_IMAGE=$($manifest.image)
DOCUMIND_OLLAMA_PORT=21434
OLLAMA_MODELS=$(Join-Path $appRoot 'runtime/models')
OLLAMA_CHAT_MODEL=qwen3:4b-instruct-2507-q4_K_M
OLLAMA_EMBED_MODEL=bge-m3
EMBED_VECTOR_DIM=1024
DOCUMIND_QDRANT_COLLECTION=pdf_chunks_bge_m3_1024
"@
[IO.File]::WriteAllText((Join-Path $appRoot '.env'),$settings,[Text.UTF8Encoding]::new($false))
@{version=1;offline=$true}|ConvertTo-Json|Set-Content -LiteralPath '.venv/setup-ready.json'
Write-Host 'Offline files installed. Start app/Start_DocuMind.bat. Health is checked by the launcher.'
