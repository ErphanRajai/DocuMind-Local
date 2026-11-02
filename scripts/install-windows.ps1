param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
function Refresh-TaskPath {
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}
function Ensure-Tool([string]$Command, [string]$Package) {
  if (Get-Command $Command -ErrorAction SilentlyContinue) { Write-Host "$Command found"; return }
  if ($CheckOnly) { Write-Host "$Command missing ($Package)"; return }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Windows App Installer/winget is missing. Install App Installer from Microsoft, then rerun setup.' }
  Write-Host "Installing $Package from the Windows package repository. Complete any vendor installer or permission prompt."
  & winget install --id $Package --exact --source winget --interactive
  if ($LASTEXITCODE -ne 0) { throw "$Package installation did not finish. A reboot or vendor first-run setup may be needed; rerun this installer afterward." }
  Refresh-TaskPath
  if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) { throw "$Command is not available yet. Open this installer again in a new session." }
}
try {
  Write-Host 'DocuMind local setup: initial downloads need internet; documents and answers stay local.'
  Ensure-Tool 'py' 'Python.Python.3.12'
  Ensure-Tool 'node' 'OpenJS.NodeJS.LTS'
  Ensure-Tool 'docker' 'Docker.DockerDesktop'
  Ensure-Tool 'ollama' 'Ollama.Ollama'
  if ($CheckOnly) {
    if (Test-Path -LiteralPath '.venv/Scripts/python.exe') { & .venv/Scripts/python.exe setup_documind.py --check; exit $LASTEXITCODE }
    Write-Host 'Python environment not created yet. Run without -CheckOnly to install.'
    exit 1
  }
  $nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
  if ($nodeMajor -lt 22) {
    & winget upgrade --id OpenJS.NodeJS.LTS --exact --source winget --interactive
    if ($LASTEXITCODE -ne 0) { throw 'Node.js update did not finish. Update Node.js LTS and rerun setup.' }
    Refresh-TaskPath
    if ([int]((& node --version).TrimStart('v').Split('.')[0]) -lt 22) { throw 'The old Node.js is still on PATH. Reopen this installer after updating Node.js LTS.' }
  }
  if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & py -3.12 -c 'import sys; print(sys.version_info[:2])' 2>$null
    if ($LASTEXITCODE -ne 0) {
      & winget install --id Python.Python.3.12 --exact --source winget --interactive
      if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 installation did not finish. Rerun setup afterward.' }
      Refresh-TaskPath
    }
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the launcher Python environment.' }
  }
  & docker info --format '{{.ServerVersion}}' 2>$null
  if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
    if (Test-Path -LiteralPath $dockerDesktop) { Start-Process -FilePath $dockerDesktop -WindowStyle Hidden }
    Write-Host 'Waiting for Docker Desktop. Complete vendor first-run prompts if shown.'
    for ($attempt=0; $attempt -lt 60; $attempt++) {
      & docker info --format '{{.ServerVersion}}' 2>$null
      if ($LASTEXITCODE -eq 0) { break }
      Start-Sleep -Seconds 2
    }
  }
  & .venv/Scripts/python.exe -u setup_documind.py
  if ($LASTEXITCODE -eq 0) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'DocuMind Local.lnk'
    if (-not (Test-Path -LiteralPath $shortcutPath)) {
      $shell = New-Object -ComObject WScript.Shell
      $shortcut = $shell.CreateShortcut($shortcutPath)
      $shortcut.TargetPath = Join-Path $projectRoot 'Start_DocuMind.bat'
      $shortcut.WorkingDirectory = $projectRoot
      $shortcut.Description = 'Open the local DocuMind study workspace'
      $shortcut.Save()
      Write-Host 'Created the DocuMind Local desktop shortcut.'
    }
    exit 0
  }
  exit $LASTEXITCODE
} catch { Write-Error $_; exit 1 }
