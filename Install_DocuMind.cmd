@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1" %*
if errorlevel 1 (
  echo Setup is incomplete. Read the message above and rerun this file to resume.
  pause
  exit /b 1
)
echo Setup finished. Use Start_DocuMind.bat to open the app.
pause
