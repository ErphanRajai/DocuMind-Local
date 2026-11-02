@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0runtime\node\node.exe" set "PATH=%~dp0runtime\node;%~dp0runtime\ollama;%PATH%"

echo ==========================================
echo        DocuMind Local AI Workspace
echo ==========================================
echo.

if not exist ".venv\setup-ready.json" (
    echo First-time setup is needed. Starting the resumable installer...
    call Install_DocuMind.cmd
    if errorlevel 1 exit /b 1
)

.venv\Scripts\python.exe launcher.py
if errorlevel 1 (
    echo.
    echo DocuMind could not start. See the message above for the next step.
    pause
)
exit /b %errorlevel%

:setup_failed
echo.
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
