# OptionTrade decode

Archivio personale di strategie in opzioni estratte da video YouTube.
Dai in pasto un link, l'app scarica i sottotitoli automatici, identifica la
strategia, produce una sintesi in italiano e indicizza tutto in un piccolo
database locale con ricerca full-text.

## Cosa fa

- **Aggiungi video**: incolli un URL YouTube, l'app scarica i sottotitoli e
  chiede a Claude di estrarre nome della strategia, tag tematici e una
  sintesi in italiano di 400–900 parole.
- **Archivia tutto** in `data/videos.sqlite` (SQLite locale).
- **Cerca** per titolo, strategia, tag, parole nel testo della sintesi
  (ricerca full-text con highlight).
- **Modalita' sola lettura**: senza chiave API funziona comunque la
  consultazione dei video gia' presenti nel database.

## Installazione su un PC nuovo

1. **Installa Python 3.11 o successivo** da <https://www.python.org/downloads/>.
   Durante l'installazione metti la spunta su *"Add Python to PATH"*.
2. **Scarica/copia la cartella** `OptionTrade_decode` in una posizione comoda
   (es. `C:\OptionTrade_decode`). Se ti e' stato dato un file ZIP, scompattalo.
3. **Fai doppio clic su `install.bat`**. Lo script:
   - crea un ambiente virtuale Python isolato in `.venv\`
   - installa le librerie necessarie (Flask, yt-dlp, anthropic, markdown, dotenv)
   - copia `.env.example` in `.env`
4. *(Opzionale)* Apri il file `.env` con il Blocco Note e inserisci la tua
   **chiave Anthropic** dopo `ANTHROPIC_API_KEY=`.
   Se non hai la chiave, salta questo passo: potrai comunque cercare e
   leggere i video gia' archiviati, ma non aggiungerne di nuovi.

## Uso

- **Avvio**: doppio clic su `run.bat`. Si apre automaticamente il browser su
  `http://127.0.0.1:5000/`.
- **Aggiungere un video**: incolla l'URL nel form e premi "Elabora".
  L'operazione richiede 10–40 secondi a seconda della lunghezza del video.
- **Cercare**: usa la barra in alto. Cerca per nome strategia
  (es. "butterfly", "iron condor"), tag (es. "0DTE"), o parole chiave.
- **Modificare strategia/tag** di un video: nella scheda del video, espandi
  la riga "Strategia / Tag" e clicca Salva.

## Provider LLM: OpenAI o Anthropic

La traduzione/sintesi puo' essere fatta da **OpenAI** (default) o **Anthropic**.
La scelta avviene nel file `.env` con la variabile `LLM_PROVIDER`:

```
LLM_PROVIDER=openai     # oppure: anthropic
```

### Configurazione OpenAI (default)

1. Vai su <https://platform.openai.com/api-keys>
2. Crea una chiave e copiala
3. Nel file `.env` incolla la chiave dopo `OPENAI_API_KEY=`
4. Modello di default: `gpt-5.4-mini` (modificabile con `OPENAI_MODEL=`).
   Alternative: `gpt-5-mini` (rodato), `gpt-5.4` (full, piu' caro).
   Nota: la serie `gpt-5.1` NON ha variante mini.

Costo indicativo: 1–3 centesimi per video (gpt-5.4-mini, video 10–30 min).

### Configurazione Anthropic (alternativa)

1. Vai su <https://console.anthropic.com/>
2. Sezione **API Keys**, crea una chiave e copiala
3. Nel file `.env` incolla la chiave dopo `ANTHROPIC_API_KEY=`
4. Imposta `LLM_PROVIDER=anthropic`
5. Modello di default: `claude-sonnet-4-6` (modificabile con `CLAUDE_MODEL=`)

Costo indicativo: 5–10 centesimi per video (Sonnet 4.6, video 10–30 min).

### Quale scegliere

- **OpenAI gpt-5.1-mini**: piu' economico, ottimo per estrazione strutturata,
  qualita' molto buona sulla maggior parte dei video.
- **Anthropic Claude Sonnet 4.6**: piu' costoso, tende a essere piu' sfumato
  su materiale tecnico specialistico. Buon "secondo parere" se la sintesi
  OpenAI ti sembra povera su un video specifico.

Puoi cambiare provider in qualunque momento modificando `.env`: i video gia'
nel database restano invariati, cambia solo chi elabora i prossimi.

## Senza chiave (modalita' archivio)

Se non vuoi aprire un account Anthropic, l'app rimane utile come archivio:
ricevi/scarichi il file `data/videos.sqlite` da un amico che ha gia'
elaborato dei video, lo metti nella cartella `data/` e puoi:

- consultare le sintesi gia' presenti
- cercare per strategia, tag, testo
- modificare strategia e tag manualmente

L'unica cosa disabilitata e' il form "Aggiungi un video".

## Struttura del progetto

```
OptionTrade_decode\
  app.py             Webapp Flask (route, template)
  ingest.py          Pipeline yt-dlp -> Claude -> SQLite
  clean_vtt.py       Pulizia trascrizione VTT
  db.py              Schema SQLite + FTS5
  requirements.txt   Dipendenze Python
  .env.example       Configurazione di esempio
  install.bat        Installazione one-click
  run.bat            Avvio app + apertura browser
  data\
    videos.sqlite    Database (creato al primo avvio)
  templates\         Pagine HTML (Jinja2)
  static\
    style.css        Tema dark
```

## Disinstallazione

Cancella semplicemente la cartella del progetto. Non vengono toccati altri
file di sistema.

## Note

- L'app gira solo in locale (`127.0.0.1`): nessun dato esce dal tuo PC,
  tranne le chiamate a Claude API quando elabori un nuovo video.
- I sottotitoli automatici di YouTube non sono perfetti; la sintesi puo'
  contenere imprecisioni quando l'audio originale e' di bassa qualita'.
- Per video senza sottotitoli automatici (rari), l'ingest fallisce con un
  messaggio chiaro.
