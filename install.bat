@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  OptionTrade decode - installazione
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRORE] Python non trovato.
  echo Scarica e installa Python 3.11 o successivo da:
  echo     https://www.python.org/downloads/
  echo IMPORTANTE: durante l'installazione spunta "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

echo [1/4] Creo l'ambiente virtuale .venv ...
if not exist ".venv" (
  python -m venv .venv
  if errorlevel 1 (
    echo [ERRORE] Impossibile creare l'ambiente virtuale.
    pause
    exit /b 1
  )
)

echo [2/4] Aggiorno pip ...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [3/4] Installo le dipendenze (puo' richiedere qualche minuto) ...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRORE] Installazione dipendenze fallita.
  pause
  exit /b 1
)

echo [4/4] Preparo il file di configurazione .env ...
if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo File .env creato. Aprilo e inserisci la tua chiave Anthropic
  echo se vuoi abilitare l'aggiunta di nuovi video.
) else (
  echo File .env gia' presente, lasciato invariato.
)

echo.
echo ============================================================
echo  Installazione completata.
echo  Avvia l'app con:   run.bat
echo ============================================================
echo.
pause
