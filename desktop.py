"""Launcher desktop di OptionTrade decode.

Avvia il server Flask dietro le quinte (dai sorgenti, con il venv) e mostra
l'app in una finestra nativa via pywebview, invece che in una scheda del
browser. I sorgenti restano quelli di sempre, quindi l'auto-aggiornamento
dal menu Impostazioni continua a funzionare.

Avvio:  doppio clic su OptionTrade.exe  (oppure: python desktop.py)
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import webview

# Quando e' compilato in .exe (PyInstaller), i sorgenti e il venv stanno
# nella cartella dell'eseguibile; da script, accanto a questo file.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.getenv("PORT", "5000"))
URL = f"http://127.0.0.1:{PORT}/"


def _venv_python() -> str:
    """Python del venv, senza finestra console (pythonw) se disponibile."""
    for name in ("pythonw.exe", "python.exe"):
        cand = BASE_DIR / ".venv" / "Scripts" / name
        if cand.exists():
            return str(cand)
    return sys.executable


def _port_open() -> bool:
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _start_server() -> subprocess.Popen | None:
    """Avvia app.py come processo separato. None se la porta e' gia' servita."""
    if _port_open():
        return None
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    return subprocess.Popen([_venv_python(), str(BASE_DIR / "app.py")],
                            cwd=str(BASE_DIR), creationflags=flags)


def _wait_server(timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if _port_open():
            return True
        time.sleep(0.3)
    return False


def _kill_on_port() -> None:
    """Chiude il server sulla porta (best-effort), incluso un eventuale
    processo nuovo nato da un auto-aggiornamento."""
    if sys.platform != "win32":
        return
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    except OSError:
        return
    pids = set()
    for line in out.splitlines():
        if f":{PORT} " in line and "LISTENING" in line:
            pids.add(line.split()[-1])
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", pid],
                       capture_output=True, creationflags=0x08000000)


def main() -> None:
    proc = _start_server()
    if not _wait_server():
        webview.create_window(
            "OptionTrade decode",
            html="<body style='font-family:sans-serif;padding:40px'>"
                 "<h2>Impossibile avviare il server.</h2>"
                 "<p>Hai eseguito <code>install.bat</code>?</p></body>",
            width=700, height=400,
        )
        webview.start()
        return

    webview.create_window("OptionTrade decode", URL, width=1150, height=820)
    webview.start()  # blocca finche' la finestra resta aperta

    # Finestra chiusa: ferma il server.
    if proc and proc.poll() is None:
        proc.terminate()
    _kill_on_port()


if __name__ == "__main__":
    main()
