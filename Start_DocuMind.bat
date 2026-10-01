@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo        DocuMind Local AI Workspace
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3 was not found. Install Python 3.10 or newer and try again.
        echo Download: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Setting up the Python environment for the first launch...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto setup_failed
)

if not exist ".venv\frontend-ready" (
    echo Installing the DocuMind interface. This may take a minute...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    if errorlevel 1 goto setup_failed
    .venv\Scripts\python.exe -m pip install -r pdf-summarizer-frontend\requirements.txt
    if errorlevel 1 goto setup_failed
    type nul > ".venv\frontend-ready"
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
