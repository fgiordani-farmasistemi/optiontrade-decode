# OptionTrade decode

Archivio personale di strategie in opzioni estratte da video YouTube.
Dai in pasto un link, l'app scarica i sottotitoli automatici, identifica la
strategia, produce una sintesi in italiano e indicizza tutto in un piccolo
database locale con ricerca full-text.

Gira **solo in locale** sul tuo PC (`http://127.0.0.1:5000`): nessun dato
esce dal computer, tranne le chiamate al provider AI quando elabori un video.

## Cosa fa

- **Aggiungi video**: incolli un URL YouTube, l'app scarica i sottotitoli e
  chiede al modello di estrarre nome della strategia, tag tematici e una
  sintesi in italiano.
- **Archivia tutto** in `data/videos.sqlite` (SQLite locale).
- **Cerca** per titolo, strategia, tag, parole nel testo della sintesi
  (ricerca full-text con highlight).
- **Si aggiorna da solo** dal menu Impostazioni, con backup automatico del
  database prima di ogni aggiornamento.

---

## Installazione su un PC nuovo

1. **Installa Python 3.11 o successivo** da <https://www.python.org/downloads/>.
   Durante l'installazione metti la spunta su *"Add Python to PATH"*.
2. **Scarica il progetto** da GitHub:
   <https://github.com/fgiordani-farmasistemi/optiontrade-decode>
   - pulsante verde **`Code` → `Download ZIP`**, poi scompatta in una cartella
     comoda (es. `C:\OptionTrade_decode`);
   - in alternativa, se hai git: `git clone https://github.com/fgiordani-farmasistemi/optiontrade-decode.git`
3. **Fai doppio clic su `install.bat`**. Crea un ambiente Python isolato in
   `.venv\` e installa le librerie necessarie.
4. **Avvia con `run.bat`**: si apre il browser su `http://127.0.0.1:5000`.

Il database parte **vuoto**: si crea da solo al primo avvio.

## Primo avvio: inserisci la chiave API

Senza chiave puoi solo consultare e cercare i video già presenti. Per
**aggiungere** nuovi video serve una chiave del provider AI:

1. Nell'app, in alto a destra, apri **⚙️ Impostazioni**.
2. Incolla la chiave nel campo del provider che usi e premi **Salva**.

La chiave viene salvata **cifrata** sul tuo PC (vault DPAPI di Windows, legato
al tuo utente): nel file non resta nulla in chiaro e non viene mai versionata
né condivisa.

## Uso

- **Aggiungere un video**: incolla l'URL nel form e premi "Elabora"
  (10–40 secondi a seconda della lunghezza).
- **Cercare**: barra in alto. Per nome strategia ("butterfly", "iron condor"),
  tag ("0DTE"), o parole chiave.
- **Modificare strategia/tag** di un video: nella scheda, espandi
  "Strategia / Tag" e clicca Salva.

## Aggiornare l'app

Dal menu **⚙️ Impostazioni → Versione e aggiornamenti**:

1. **Controlla aggiornamenti**: l'app confronta la tua versione con quella
   pubblicata sul repository.
2. Se c'è una versione nuova, **Aggiorna ora**: l'app fa un **backup
   automatico del database** (in `data/backups/`), scarica la nuova versione,
   sostituisce solo il codice e **si riavvia da sola**.

I tuoi dati non vengono mai toccati dall'aggiornamento: database, backup,
chiave API e ambiente Python restano intatti.

> Nota: l'auto-update è disponibile dalla **v1.1.0** in poi. Una versione
> precedente va portata alla 1.1.0 una volta sola riscaricando lo ZIP; da lì
> in poi gli aggiornamenti sono automatici.

## Impostazioni (⚙️)

- **Provider e modello**: OpenAI (default) o Anthropic, con il modello da usare.
- **Chiavi API**: salvate cifrate sul PC, mai in chiaro.
- **Ruolo del modello**: la prima frase che istruisce il modello (il suo
  "personaggio"). Modificala per sintesi più didattiche o più operative.
  Default: *"Sei un assistente esperto di trading in opzioni finanziarie."*

## Provider LLM: OpenAI o Anthropic

La sintesi può essere fatta da **OpenAI** (default) o **Anthropic**, scelto da
Impostazioni.

- **OpenAI**: chiave da <https://platform.openai.com/api-keys>.
  Modello di default `gpt-5.4-mini`. Costo indicativo 1–3 centesimi a video.
- **Anthropic**: chiave da <https://console.anthropic.com/>.
  Modello di default `claude-sonnet-4-6`. Costo indicativo 5–10 centesimi a video.

I video già nel database restano invariati se cambi provider: cambia solo chi
elabora i prossimi.

## Dati e privacy

- L'app gira solo in locale (`127.0.0.1`).
- La **chiave API** è cifrata con DPAPI e resta sul tuo PC.
- Il **database** (`data/videos.sqlite`) è locale e non viene mai versionato.
- I sottotitoli automatici di YouTube non sono perfetti: la sintesi può
  contenere imprecisioni quando l'audio originale è di bassa qualità.

## Struttura del progetto

```
OptionTrade_decode\
  app.py             Webapp Flask (route, template)
  ingest.py          Pipeline yt-dlp -> LLM -> SQLite
  clean_vtt.py       Pulizia trascrizione VTT
  db.py              Schema SQLite + FTS5
  config.py          Impostazioni + vault chiavi cifrate (DPAPI)
  updater.py         Auto-aggiornamento dal repo GitHub
  VERSION            Versione corrente
  requirements.txt   Dipendenze Python
  install.bat        Installazione one-click
  run.bat            Avvio app + apertura browser
  data\
    videos.sqlite    Database (creato al primo avvio, non versionato)
    secrets.json     Vault chiavi cifrate (non versionato)
    backups\         Backup automatici pre-aggiornamento
  templates\         Pagine HTML (Jinja2)
  static\
    style.css        Tema chiaro
```

## Disinstallazione

Cancella semplicemente la cartella del progetto. Non vengono toccati altri
file di sistema.
