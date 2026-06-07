"""Auto-aggiornamento dell'app dal repo GitHub pubblico.

Flusso (tutto in-app, dal menu Impostazioni):
  1. check_for_update()  - confronta VERSION locale con quella sul repo
  2. backup_database()   - copia di sicurezza del DB prima di toccare i file
  3. apply_update()      - scarica lo ZIP del branch e sostituisce SOLO il
                           codice, mai i dati/segreti/ambiente
  4. restart()           - riavvio automatico del server

Cosa NON viene mai toccato dall'aggiornamento: la cartella data/ (database,
backup, vault chiavi), il file .env, l'ambiente .venv, la cartella .git.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import config

BASE_DIR = config.BASE_DIR

# Nomi di primo livello che l'update non deve MAI sovrascrivere.
# OptionTrade.exe e' il launcher in esecuzione: su Windows non si puo'
# sovrascrivere un eseguibile in uso, e comunque l'auto-update aggiorna i
# sorgenti, non il guscio launcher.
PROTECTED = {".env", ".venv", ".git", "__pycache__", "data", "OptionTrade.exe"}


def _parse_version(v: str) -> tuple[int, ...]:
    """'1.2.3' -> (1, 2, 3). Robusto a suffissi non numerici."""
    parts: list[int] = []
    for chunk in (v or "").strip().split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def remote_version(timeout: int = 10) -> str:
    req = urllib.request.Request(config.raw_url("VERSION"), headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8").strip()


def check_for_update() -> dict:
    """Ritorna lo stato dell'aggiornamento per la UI."""
    current = config.app_version()
    try:
        latest = remote_version()
    except Exception as exc:  # noqa: BLE001 - rete: mostriamo l'errore all'utente
        return {"ok": False, "error": str(exc), "current": current}
    available = _parse_version(latest) > _parse_version(current)
    return {"ok": True, "current": current, "latest": latest, "available": available}


def backup_database() -> Path | None:
    """Copia data/videos.sqlite in data/backups/ con timestamp. None se non c'e'."""
    db = BASE_DIR / "data" / "videos.sqlite"
    if not db.exists():
        return None
    backups = BASE_DIR / "data" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = backups / f"videos_{ts}.sqlite"
    shutil.copy2(db, dest)
    return dest


def _download_zip(timeout: int = 120) -> bytes:
    req = urllib.request.Request(config.zip_url(), headers={"User-Agent": "optiontrade-decode-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def apply_update(target_dir: str | os.PathLike | None = None) -> list[str]:
    """Scarica lo ZIP del branch e copia i file sopra l'installazione,
    saltando tutto cio' che e' in PROTECTED. Ritorna i nomi copiati."""
    target = Path(target_dir) if target_dir else BASE_DIR
    payload = _download_zip()

    tmp = Path(tempfile.mkdtemp(prefix="otd_update_"))
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            zf.extractall(tmp)
        roots = [p for p in tmp.iterdir() if p.is_dir()]
        if not roots:
            raise RuntimeError("Archivio di aggiornamento vuoto o non valido.")
        src = roots[0]  # es. optiontrade-decode-main/

        copied: list[str] = []
        for item in src.iterdir():
            if item.name in PROTECTED:
                continue
            dest = target / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
            copied.append(item.name)
        return copied
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restart() -> None:
    """Avvia un processo separato che attende la chiusura di questo server
    (porta libera) e poi rilancia app.py. Il chiamante deve poi terminare
    il processo corrente per liberare la porta."""
    port = int(os.getenv("PORT", "5000"))
    python = sys.executable
    app_py = str(BASE_DIR / "app.py")

    relauncher = (
        "import socket, time, subprocess\n"
        f"port = {port}\n"
        "for _ in range(100):\n"
        "    s = socket.socket()\n"
        "    try:\n"
        "        s.bind(('127.0.0.1', port)); s.close(); break\n"
        "    except OSError:\n"
        "        s.close(); time.sleep(0.2)\n"
        f"subprocess.Popen([{python!r}, {app_py!r}], cwd={str(BASE_DIR)!r})\n"
    )

    flags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: sopravvive al parent.
        flags = 0x00000008 | 0x00000200

    subprocess.Popen(
        [python, "-c", relauncher],
        cwd=str(BASE_DIR),
        creationflags=flags,
        close_fds=True,
    )
