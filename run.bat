@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtuale non trovato. Esegui prima install.bat
  pause
  exit /b 1
)

start "" "http://127.0.0.1:5000/"
".venv\Scripts\python.exe" app.py
