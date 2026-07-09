@echo off
echo ==========================================
echo   Starting DocuMind Local AI Engine...
echo ==========================================

REM ۱. روشن کردن تمام کانتینرها
docker compose up -d

echo.
echo ⏳ Waiting 8 seconds for AI Engine and Database to initialize...
timeout /t 8 /nobreak >nul

echo.
echo Starting Streamlit Client UI in background...
start /b python -m streamlit run pdf-summarizer-frontend/app.py --server.headless=true

echo.
echo Launching Desktop Interface...
python launcher.py

echo.
echo Shutting down AI Engine background containers...
docker compose down
exit