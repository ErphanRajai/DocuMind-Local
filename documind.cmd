@echo off
setlocal DisableDelayedExpansion
if exist "%~dp0runtime\ollama\ollama.exe" set "PATH=%~dp0runtime\ollama;%PATH%"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0documind_cli.py" %*
) else (
  python "%~dp0documind_cli.py" %*
)
exit /b %errorlevel%
