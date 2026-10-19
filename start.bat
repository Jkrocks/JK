@echo off
REM Start Tejas. Open http://localhost:8000 here, or the https:// address on other screens.
cd /d "%~dp0"
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1 || start "" /min ollama serve
start "" http://localhost:8000
.venv\Scripts\python -m tejas_ai %*
