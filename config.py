"""Gestione impostazioni dell'app: lettura/scrittura .env e versione.

La pagina /settings usa questo modulo per salvare chiave API, provider,
modello e "ruolo" del modello direttamente dall'interfaccia, senza che
l'utente debba aprire il file .env a mano.

Principio: i SEGRETI e la configurazione restano nel file .env locale
(mai versionato su git). Qui c'e' solo la logica per leggerlo/scriverlo
in modo sicuro, preservando commenti e righe non gestite.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
VERSION_PATH = BASE_DIR / "VERSION"
SECRETS_PATH = BASE_DIR / "data" / "secrets.json"

# Chiavi trattate come SEGRETI: non finiscono mai nel .env in chiaro, ma in
# un vault cifrato con DPAPI di Windows (legato all'utente di questo PC).
SECRET_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")

# Ruolo di default del modello (la prima frase del system prompt).
# Modificabile dall'utente nel menu Impostazioni.
DEFAULT_ROLE = "Sei un assistente esperto di trading in opzioni finanziarie."

# Chiavi gestite dal menu Impostazioni.
MANAGED_KEYS = {
    "LLM_PROVIDER",
    "OPENAI_MODEL",
    "CLAUDE_MODEL",
    "MODEL_ROLE",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
}


def app_version() -> str:
    """Versione corrente dell'app, letta dal file VERSION."""
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _format_value(value: str) -> str:
    """Quota il valore se contiene spazi o caratteri speciali, cosi' il
    parsing di python-dotenv resta corretto (es. il ruolo con spazi)."""
    if value == "" or re.search(r'[\s#"\'=]', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def write_env_values(updates: dict[str, str]) -> None:
    """Aggiorna (o aggiunge) le chiavi indicate nel file .env, preservando
    tutte le altre righe e i commenti. Aggiorna anche os.environ cosi' i
    nuovi valori sono attivi immediatamente, senza riavviare l'app."""
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    done: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={_format_value(updates[key])}"
            done.add(key)

    for key, value in updates.items():
        if key not in done:
            lines.append(f"{key}={_format_value(value)}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Applica subito i valori al processo in esecuzione.
    for key, value in updates.items():
        os.environ[key] = value


def get_settings() -> dict:
    """Stato corrente delle impostazioni per popolare il form.

    Le chiavi API NON vengono mai restituite in chiaro: solo un flag
    'impostata' e gli ultimi 4 caratteri come promemoria visivo.
    """
    return {
        "version": app_version(),
        "provider": (os.getenv("LLM_PROVIDER", "openai") or "openai").strip().lower(),
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "claude_model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        "role": (os.getenv("MODEL_ROLE", "") or "").strip() or DEFAULT_ROLE,
        "default_role": DEFAULT_ROLE,
        "openai_key": _key_state(os.getenv("OPENAI_API_KEY", "")),
        "anthropic_key": _key_state(os.getenv("ANTHROPIC_API_KEY", "")),
    }


def _key_state(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {"set": False, "hint": ""}
    tail = raw[-4:] if len(raw) >= 4 else raw
    return {"set": True, "hint": f"••••{tail}"}


# --------------------------------------------------------------------- #
# Vault segreti: chiavi API cifrate con DPAPI (Windows)                  #
# --------------------------------------------------------------------- #
#
# Le chiavi API non vengono salvate in chiaro. Su Windows usiamo DPAPI
# (CryptProtectData/CryptUnprotectData) che cifra i dati legandoli
# all'account utente del PC: solo lo stesso utente, sullo stesso PC, puo'
# decifrarli, senza bisogno di una password. Il file data/secrets.json
# contiene solo testo cifrato in base64 ed e' escluso da git.


def dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    # Tipi espliciti: evita il troncamento dei puntatori a 64 bit.
    for fn in (crypt32.CryptProtectData, crypt32.CryptUnprotectData):
        fn.restype = wintypes.BOOL
        fn.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR,
                       ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                       wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    func = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    ok = func(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI operation failed")
    size = blob_out.cbData
    out = ctypes.string_at(blob_out.pbData, size)
    kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))
    return out


def _read_secrets_file() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_secrets_file(store: dict) -> None:
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def save_secret(name: str, value: str) -> None:
    """Cifra e salva un segreto nel vault. Aggiorna anche os.environ cosi'
    il valore e' subito utilizzabile dal resto dell'app."""
    value = (value or "").strip()
    store = _read_secrets_file()
    if not value:
        store.pop(name, None)
        _write_secrets_file(store)
        os.environ.pop(name, None)
        return
    if dpapi_available():
        token = base64.b64encode(_dpapi(value.encode("utf-8"), decrypt=False)).decode("ascii")
        store[name] = {"enc": "dpapi", "data": token}
    else:
        # Fuori da Windows non c'e' DPAPI: salviamo comunque fuori dal .env,
        # ma solo offuscato in base64 (NON sicuro come DPAPI).
        store[name] = {"enc": "b64", "data": base64.b64encode(value.encode("utf-8")).decode("ascii")}
    _write_secrets_file(store)
    os.environ[name] = value


def _decrypt_secret(entry: dict) -> str | None:
    try:
        raw = base64.b64decode(entry["data"])
        if entry.get("enc") == "dpapi":
            return _dpapi(raw, decrypt=True).decode("utf-8")
        return raw.decode("utf-8")
    except (KeyError, ValueError, OSError):
        return None


def load_secrets_into_env() -> None:
    """Decifra i segreti del vault e li mette in os.environ, cosi' il resto
    dell'app (che legge os.getenv) li trova come prima."""
    for name, entry in _read_secrets_file().items():
        value = _decrypt_secret(entry)
        if value:
            os.environ[name] = value


def _remove_env_keys(names) -> None:
    """Rimuove righe KEY=... dal file .env (usato per la migrazione)."""
    if not ENV_PATH.exists():
        return
    names = set(names)
    kept = []
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in names:
                continue
        kept.append(line)
    ENV_PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")


def bootstrap_secrets() -> None:
    """Da chiamare all'avvio, dopo load_dotenv.

    1) Migra eventuali chiavi ancora in chiaro nel .env dentro il vault cifrato
       e le rimuove dal .env.
    2) Carica i segreti del vault in os.environ.
    """
    store = _read_secrets_file()
    to_migrate = []
    for name in SECRET_KEYS:
        plain = (os.getenv(name, "") or "").strip()
        if plain and name not in store:
            save_secret(name, plain)
            to_migrate.append(name)
    if to_migrate:
        _remove_env_keys(to_migrate)
    load_secrets_into_env()
