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

echo [1/5] Creo l'ambiente virtuale .venv ...
if not exist ".venv" (
  python -m venv .venv
  if errorlevel 1 (
    echo [ERRORE] Impossibile creare l'ambiente virtuale.
    pause
    exit /b 1
  )
)

echo [2/5] Aggiorno pip ...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [3/5] Installo le dipendenze (puo' richiedere qualche minuto) ...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRORE] Installazione dipendenze fallita.
  pause
  exit /b 1
)

echo [4/5] Preparo il file di configurazione .env ...
if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
)

echo [5/5] Creo il collegamento nel menu Start ...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut([Environment]::GetFolderPath('Programs') + '\OptionTrade decode.lnk'); $lnk.TargetPath = '%~dp0OptionTrade.exe'; $lnk.WorkingDirectory = '%~dp0'; $lnk.IconLocation = '%~dp0icon.ico'; $lnk.Description = 'OptionTrade decode'; $lnk.Save()" >nul 2>&1

echo.
echo ============================================================
echo  Installazione completata.
echo.
echo  Avvia l'app dal menu Start  ->  "OptionTrade decode"
echo  oppure con doppio clic su   ->  OptionTrade.exe
echo.
echo  Al primo avvio, apri Impostazioni e inserisci la chiave API.
echo ============================================================
echo.
pause
