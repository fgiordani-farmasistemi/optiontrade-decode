"""Pipeline: YouTube URL -> transcript -> LLM 2-step summary -> SQLite.

Provider LLM selezionabile via variabile d'ambiente LLM_PROVIDER:
- openai     -> usa OpenAI (default), modello da OPENAI_MODEL
- anthropic  -> usa Claude (Anthropic), modello da CLAUDE_MODEL

Pipeline a 2 step:
  Step 1 (outline)  - LLM legge la trascrizione e restituisce JSON con:
      strategia (principale), autore (se presentato), topics (lista),
      tag (lista).
  Step 2 (sintesi)  - LLM riceve outline + trascrizione e produce una
      sintesi italiana in markdown che copre tutti i topics dell'outline.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp

from clean_vtt import clean_vtt_file
from config import DEFAULT_ROLE
import db

# Sub language priority: original, English, Italian. Auto-captions only.
SUB_LANG_PRIORITY = ["en-orig", "en", "it-orig", "it"]


def _provider() -> str:
    return (os.getenv("LLM_PROVIDER", "openai") or "openai").strip().lower()


def _role() -> str:
    """Prima frase del system prompt: il 'ruolo' che diamo al modello.
    Personalizzabile dal menu Impostazioni (variabile MODEL_ROLE)."""
    return (os.getenv("MODEL_ROLE", "") or "").strip() or DEFAULT_ROLE


def has_api_key() -> bool:
    if _provider() == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def provider_label() -> str:
    p = _provider()
    if p == "anthropic":
        return f"Anthropic ({os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-6')})"
    return f"OpenAI ({os.getenv('OPENAI_MODEL', 'gpt-5.4-mini')})"


class IngestError(RuntimeError):
    pass


class NeedsWhisperConfirmation(Exception):
    """Sollevata quando il video non ha sub e serve conferma utente per Whisper.

    Porta con se' i metadati gia' raccolti (titolo, durata, canale, video_id)
    cosi' la UI puo' mostrare costi e info senza una seconda chiamata yt-dlp.
    """
    def __init__(self, info: dict[str, Any]):
        super().__init__("Sottotitoli non disponibili: serve conferma per Whisper.")
        self.info = info


# --------------------------------------------------------------------- #
# yt-dlp: metadati + sottotitoli                                        #
# --------------------------------------------------------------------- #


WHISPER_MAX_BYTES = 25 * 1024 * 1024  # 25 MB OpenAI limit


def _whisper_enabled() -> bool:
    return os.getenv("ENABLE_WHISPER_FALLBACK", "0").strip() in {"1", "true", "yes", "on"}


def fetch_metadata_and_subs(
    url: str,
    workdir: Path,
    *,
    force_whisper: bool = False,
) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)

    info_opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    auto_subs = info.get("automatic_captions") or {}
    chosen_lang = None if force_whisper else _pick_available_lang(auto_subs)
    video_id = info.get("id") or ""
    titolo = info.get("title") or ""
    canale = info.get("uploader") or info.get("channel") or ""
    durata = info.get("duration")

    if chosen_lang:
        trascrizione = _download_and_clean_subs(url, video_id, chosen_lang, workdir)
        lingua = chosen_lang.split("-")[0]
        fonte = "sub-auto"
    else:
        # Niente sub: serve conferma utente prima di passare a Whisper,
        # a meno che force_whisper=True (l'utente ha gia' confermato).
        if not force_whisper:
            raise NeedsWhisperConfirmation({
                "url": url,
                "video_id": video_id,
                "titolo": titolo,
                "canale": canale,
                "durata_sec": durata,
                "whisper_available": _whisper_enabled() and bool(os.getenv("OPENAI_API_KEY", "").strip()),
                "whisper_model": os.getenv("WHISPER_MODEL", "whisper-1"),
            })
        if not _whisper_enabled():
            raise IngestError(
                "Fallback Whisper disabilitato (imposta ENABLE_WHISPER_FALLBACK=1 nel .env)."
            )
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise IngestError(
                "Per usare il fallback Whisper serve una chiave OPENAI_API_KEY valida nel .env."
            )
        trascrizione, lingua = _whisper_pipeline(url, video_id, workdir)
        fonte = f"whisper:{os.getenv('WHISPER_MODEL', 'whisper-1')}"

    if len(trascrizione) < 200:
        raise IngestError("Trascrizione troppo corta o vuota.")

    return {
        "video_id": video_id,
        "titolo": titolo,
        "canale": canale,
        "durata_sec": durata,
        "lingua_orig": lingua,
        "trascrizione": trascrizione,
        "fonte_trascrizione": fonte,
    }


def _download_and_clean_subs(url: str, video_id: str, lang: str, workdir: Path) -> str:
    opts = {
        "skip_download": True,
        "writeautomaticsub": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "vtt",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        if "429" in msg or "Too Many Requests" in msg:
            raise IngestError(
                "YouTube ha rifiutato il download (429 Too Many Requests). "
                "Aspetta qualche minuto e riprova."
            ) from exc
        raise IngestError(f"Errore yt-dlp: {msg}") from exc

    vtt_path = workdir / f"{video_id}.{lang}.vtt"
    if not vtt_path.exists():
        raise IngestError(f"File sottotitoli atteso non trovato: {vtt_path.name}")
    return clean_vtt_file(vtt_path)


def _whisper_pipeline(url: str, video_id: str, workdir: Path) -> tuple[str, str]:
    """Scarica l'audio del video e lo trascrive con Whisper. Ritorna (testo, lingua)."""
    audio_path = _download_audio(url, video_id, workdir)
    size = audio_path.stat().st_size
    if size > WHISPER_MAX_BYTES:
        size_mb = size / (1024 * 1024)
        raise IngestError(
            f"Audio del video troppo grande per Whisper API ({size_mb:.1f} MB > 25 MB). "
            "Per ora i video oltre ~25 minuti senza sottotitoli non sono supportati. "
            "Se ti serve spesso, possiamo aggiungere lo split del file."
        )
    text, lingua = _transcribe_with_whisper(audio_path)
    return text, lingua


def _download_audio(url: str, video_id: str, workdir: Path) -> Path:
    """Scarica l'audio m4a nativo (no conversione, no ffmpeg richiesto)."""
    opts = {
        # bestaudio m4a se disponibile, altrimenti bestaudio qualsiasi.
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise IngestError(f"Errore download audio: {exc}") from exc

    # yt-dlp salva con estensione effettiva (m4a, webm, opus, ...).
    ext = info.get("ext") or "m4a"
    audio_path = workdir / f"{video_id}.{ext}"
    if not audio_path.exists():
        # Cerca qualunque file con quel prefisso, robustezza
        matches = list(workdir.glob(f"{video_id}.*"))
        matches = [m for m in matches if m.suffix.lower() not in {".vtt", ".json"}]
        if not matches:
            raise IngestError("File audio scaricato non trovato.")
        audio_path = matches[0]
    return audio_path


def _transcribe_with_whisper(audio_path: Path) -> tuple[str, str]:
    import openai
    client = openai.OpenAI()
    model = os.getenv("WHISPER_MODEL", "whisper-1")
    with audio_path.open("rb") as f:
        # response_format=verbose_json restituisce anche la lingua rilevata.
        try:
            resp = client.audio.transcriptions.create(
                model=model,
                file=f,
                response_format="verbose_json",
            )
            text = (getattr(resp, "text", None) or "").strip()
            lingua = (getattr(resp, "language", None) or "").strip().lower()[:2] or "en"
        except openai.BadRequestError:
            # gpt-4o-*-transcribe non supportano verbose_json: fallback semplice.
            f.seek(0)
            resp = client.audio.transcriptions.create(
                model=model,
                file=f,
                response_format="text",
            )
            text = str(resp).strip()
            lingua = "en"
    return text, lingua


def _pick_available_lang(auto_subs: dict[str, Any]) -> str | None:
    for lang in SUB_LANG_PRIORITY:
        if auto_subs.get(lang):
            return lang
    for key in auto_subs.keys():
        if key.startswith(("en", "it")):
            return key
    return None


# --------------------------------------------------------------------- #
# Step 1: outline                                                       #
# --------------------------------------------------------------------- #

OUTLINE_PROMPT = """Ricevi la trascrizione (in inglese o altra lingua) di un video YouTube su
opzioni. Tuo compito: leggere attentamente e produrre un OUTLINE strutturato
del contenuto. NON tradurre ancora: stai solo mappando.

Identifica:

1. STRATEGIA PRINCIPALE
   La strategia in opzioni di cui il video parla esplicitamente
   (es. "Broken Wing Butterfly", "Iron Condor", "Jade Lizard").
   Se il video parla di concetti operativi generali senza una strategia
   centrale, usa una etichetta generica
   (es. "Concetti operativi - call selling", "Volatilita' implicita").

2. AUTORE / PRESENTATORE
   Solo se la persona si presenta esplicitamente nel video (es.
   "Hi, I'm Tom"). Altrimenti stringa vuota. Niente inferenze dal canale.

3. TOPICS (3-8 voci)
   Ogni topic deve essere un concetto/argomento sostanziale trattato
   nel video, non solo una keyword. Per ogni topic fornisci:
     - "titolo": etichetta breve (es. "Differenza fra butterfly simmetrica e broken wing")
     - "descrizione": 1-2 frasi che riassumono COSA dice il video su quel topic
   I topics devono coprire l'intero contenuto del video, non solo la strategia
   principale. Includi anche concetti operativi, regole di gestione, mental
   models, esempi numerici se centrali.

4. TAG (3-8 etichette tecniche per la ricerca)
   Singole parole o brevi sintagmi tecnici utili come filtri:
   es. "butterfly", "0DTE", "credit spread", "iron condor", "delta neutral".

Rispondi SOLO con un oggetto JSON valido con questa struttura esatta:

{
  "strategia": "...",
  "autore": "...",
  "topics": [
    {"titolo": "...", "descrizione": "..."},
    ...
  ],
  "tag": ["...", "..."]
}
"""


# --------------------------------------------------------------------- #
# Step 2: sintesi italiana che copre l'outline                          #
# --------------------------------------------------------------------- #

SYNTHESIS_PROMPT = """Ricevi la trascrizione di un video YouTube + un OUTLINE gia' estratto che
elenca strategia, topics e tag.

Tuo compito: produrre una SINTESI IN ITALIANO del contenuto del video, in
formato Markdown, che:

- usi un titolo `##` per la strategia principale
- abbia un sottotitolo `###` per OGNI topic dell'outline, nello stesso ordine
- per ogni topic spieghi il concetto in italiano con elenchi puntati o
  paragrafi brevi, includendo esempi numerici se il video li fornisce
- mantenga in inglese i termini gergali del trading (butterfly, vertical,
  theta, delta, credit, debit, strike, OTM, ATM, ITM...) quando aiutano
  la chiarezza
- non ometta topics dell'outline: se uno e' trattato superficialmente
  spiegalo brevemente, ma DEVE essere presente
- lunghezza complessiva 500-1200 parole

Rispondi SOLO con un oggetto JSON valido con questa struttura esatta:

{
  "sintesi_it": "## Strategia\\n\\n### Topic 1\\n\\n..."
}
"""


# --------------------------------------------------------------------- #
# Dispatcher provider                                                   #
# --------------------------------------------------------------------- #


def summarize(trascrizione: str, titolo: str) -> dict[str, Any]:
    """Pipeline a 2 step. Restituisce dict con i campi DB pronti."""
    if not has_api_key():
        raise IngestError(
            f"Chiave API mancante per il provider '{_provider()}'. "
            "Configura il file .env."
        )

    role = _role()
    outline = _call_llm(
        system=f"{role}\n\n{OUTLINE_PROMPT}",
        user=f"TITOLO VIDEO: {titolo}\n\nTRASCRIZIONE:\n{trascrizione}\n\n"
             "Produci ora l'outline JSON.",
    )

    outline_json = _parse_json_loose(outline)
    strategia = str(outline_json.get("strategia", "")).strip()
    autore = str(outline_json.get("autore", "")).strip()
    topics_list = outline_json.get("topics") or []
    tag_list = outline_json.get("tag") or []

    # Step 2: passiamo l'outline come spec da rispettare.
    outline_compact = json.dumps(
        {"strategia": strategia, "autore": autore, "topics": topics_list},
        ensure_ascii=False,
        indent=2,
    )
    sintesi_raw = _call_llm(
        system=f"{role}\n\n{SYNTHESIS_PROMPT}",
        user=(
            f"TITOLO VIDEO: {titolo}\n\n"
            f"OUTLINE DA COPRIRE:\n{outline_compact}\n\n"
            f"TRASCRIZIONE COMPLETA:\n{trascrizione}\n\n"
            "Produci ora il JSON con sintesi_it."
        ),
    )
    sintesi_json = _parse_json_loose(sintesi_raw)
    sintesi_it = str(sintesi_json.get("sintesi_it", "")).strip()

    topics_csv = " | ".join(
        f"{t.get('titolo', '').strip()}" for t in topics_list
        if isinstance(t, dict) and t.get("titolo")
    )
    tag_csv = ",".join(str(t).strip() for t in tag_list if str(t).strip())

    return {
        "strategia": strategia,
        "autore": autore,
        "topics": topics_csv,
        "tag": tag_csv,
        "sintesi_it": sintesi_it,
    }


def _call_llm(*, system: str, user: str) -> str:
    if _provider() == "anthropic":
        return _call_anthropic(system=system, user=user)
    return _call_openai(system=system, user=user)


def _call_openai(*, system: str, user: str) -> str:
    import openai
    client = openai.OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=6144,
    )
    return (resp.choices[0].message.content or "").strip()


def _call_anthropic(*, system: str, user: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    resp = client.messages.create(
        model=model,
        max_tokens=6144,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _parse_json_loose(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise IngestError(
            f"Risposta LLM non e' JSON valido: {exc}\n{cleaned[:500]}"
        )


# --------------------------------------------------------------------- #
# Entry point                                                           #
# --------------------------------------------------------------------- #


def ingest_url(url: str, *, force_whisper: bool = False) -> int:
    existing = db.find_by_url(url)
    if existing:
        return int(existing["id"])

    with tempfile.TemporaryDirectory() as tmp:
        meta = fetch_metadata_and_subs(url, Path(tmp), force_whisper=force_whisper)
        summary = summarize(meta["trascrizione"], meta["titolo"])

    return db.insert_video(
        url=url,
        video_id=meta["video_id"],
        titolo=meta["titolo"],
        canale=meta["canale"],
        autore=summary["autore"],
        durata_sec=meta["durata_sec"],
        lingua_orig=meta["lingua_orig"],
        strategia=summary["strategia"],
        tag=summary["tag"],
        topics=summary["topics"],
        trascrizione=meta["trascrizione"],
        sintesi_it=summary["sintesi_it"],
    )
