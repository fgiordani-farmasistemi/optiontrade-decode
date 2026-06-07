"""Gestione impostazioni dell'app: lettura/scrittura .env e versione.

La pagina /settings usa questo modulo per salvare chiave API, provider,
modello e "ruolo" del modello direttamente dall'interfaccia, senza che
l'utente debba aprire il file .env a mano.

Principio: i SEGRETI e la configurazione restano nel file .env locale
(mai versionato su git). Qui c'e' solo la logica per leggerlo/scriverlo
in modo sicuro, preservando commenti e righe non gestite.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
VERSION_PATH = BASE_DIR / "VERSION"

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
