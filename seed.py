"""One-shot seed: inserisce il primo video gia' decodificato a mano,
cosi' l'app ha contenuto utile anche senza chiave API configurata.

Estrae i metadati YouTube via yt-dlp e combina la trascrizione gia' presente
in data/seed_*.txt con la sintesi italiana hardcoded qui sotto.
"""
from __future__ import annotations

from pathlib import Path

import yt_dlp

import db

VIDEO_URL = "https://www.youtube.com/watch?v=UoII79Y1qtA"
TRASCRIZIONE_FILE = Path(__file__).parent / "data" / "seed_UoII79Y1qtA.txt"

STRATEGIA = "Broken Wing Butterfly (Unbalanced Butterfly)"
AUTORE = "Tom Sosnoff"
TAG = "butterfly,broken wing,unbalanced butterfly,0DTE,credit spread,embedded vertical,index options,lottery ticket"

TOPICS = " | ".join([
    "Definizione di butterfly classica e payoff",
    "Trasformazione da butterfly simmetrica a broken wing",
    "Riconoscere lo short vertical embedded nella broken wing",
    "Gestione: chiudere lo short spread per restare con butterfly a credito",
    "Quando funziona (apertura 0DTE) e limiti (tarda giornata)",
    "Trade-off rispetto alla butterfly normale (margine, BPR, rischio)",
    "Mental model finale: pensarla come spread + lottery ticket",
])

SINTESI_IT = """## Broken Wing Butterfly / Unbalanced Butterfly (su 0 DTE su indici)

### Definizione di butterfly classica e payoff

E' una struttura a 4 contratti su 3 strike equidistanti: compri 1, vendi 2 (lo strike centrale), compri 1. Esempio del video sull'indice a 7410: butterfly 7405/7395/7385 sul lato put.

Caratteristiche:
- bassa probabilita' di profitto massimo
- basso rischio
- alto profitto potenziale

Si paga un piccolo **debito** (es. 1,10-1,20$); la perdita massima e' quel debito, il profitto massimo e' la distanza fra gli strike (10 punti) meno il debito.

### Trasformazione da butterfly simmetrica a broken wing

Sposti **piu' lontano OTM** lo strike long inferiore: invece di 7385 lo porti a 7365 (strike inferiore piu' distante, strike centrale e superiore restano dove sono).

La conseguenza chiave: la posizione passa **da debit a credit** (es. da -1,10$ a +0,55$). Il payoff diventa asimmetrico:
- stesso profitto massimo sopra (10 punti + credito)
- sotto compare una zona di **rischio reale** che nella butterfly simmetrica non c'era

### Riconoscere lo short vertical embedded nella broken wing

Tom (il presentatore) dice che la cosa importante e' smettere di pensarla come "butterfly storta". Una broken wing put butterfly, decomposta, e':

- una **butterfly simmetrica** (7405/7395/7385) - il "biglietto della lotteria"
- **+ uno short put spread** sintetico (vendi 7385, compri 7365) - da qui arrivano sia il credito che il rischio

Lo short put spread non lo vedi scritto fra le gambe della butterfly (non c'e' un short 7385 esplicito), ma c'e' - e' "fantasma", sintetico. **Il rischio della trade arriva tutto da li'.** E dove sta il rischio, sta anche l'opportunita'.

### Gestione: chiudere lo short spread per restare con butterfly a credito

Non gestisci la butterfly come pacchetto unico. Gestisci lo **short put spread embedded**, esattamente come gestiresti uno short put spread normale:

1. Apri la broken wing butterfly come **una sola trade** a credito (non in due gambe separate). Esempio: 0,50$ di credito.
2. Quando puoi, **ricompri lo short put spread embedded** (es. compri il put 7385 e vendi il put 7365) per un **debito inferiore al credito** incassato - ad es. lo richiudi per 0,20$.
3. Risultato: ti resta in mano la butterfly simmetrica 7405/7395/7385, ma **a credito netto** di 0,30$ (0,50 - 0,20).

A quel punto hai una "lottery ticket": una butterfly classica che ti rende il massimo se l'indice scade sullo strike centrale, ma per cui **non hai pagato nulla** - anzi sei a credito. Su index options cash-settled, una butterfly tenuta a credito non puo' strutturalmente perdere soldi.

### Quando funziona (apertura 0DTE) e limiti (tarda giornata)

- Funziona meglio **all'inizio della giornata** sugli 0 DTE: puoi tenere il long OTM piu' vicino e generare comunque credito. Piu' tardi nella giornata diventa difficile generare credito senza spingere lo strike molto lontano.
- Tom mostra di fare queste strutture **solo a credito**, mai a debito.
- Vale specularmente sul lato call: broken wing call butterfly = butterfly + **short call spread** embedded.

### Trade-off rispetto alla butterfly normale

- Piu' rischio (la wing rotta apre una zona di perdita)
- Piu' profitto potenziale (incassi il credito in piu')
- Piu' theta a favore
- **Margine e buying power reduction piu' alti** - il broker te lo conta come se ci fosse lo spread embedded
- Bias direzionale: una broken wing put e' in pratica **rialzista**, perche' vuoi che l'indice resti sopra lo short put spread

### Mental model finale: pensarla come spread + lottery ticket

"Unbalanced butterfly" e' il nome del prodotto, ma non descrive cio' che la guida. Cio' che la guida e' lo **short vertical embedded**. Tratta quello come la vera trade; la butterfly e' solo il biglietto della lotteria che resta in tasca quando hai chiuso lo spread in profitto.
"""


def fetch_metadata(url: str) -> dict:
    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def main() -> None:
    db.init_db()
    if db.find_by_url(VIDEO_URL):
        # Aggiorna i nuovi campi (autore + topics) sul record gia' presente.
        row = db.find_by_url(VIDEO_URL)
        if row and (not row["autore"] or not row["topics"]):
            db.update_meta(
                int(row["id"]),
                strategia=STRATEGIA,
                tag=TAG,
                autore=AUTORE,
                topics=TOPICS,
            )
            print(f"Aggiornati autore/topics sul record esistente id={row['id']}")
        else:
            print(f"Seed gia' presente e completo per: {VIDEO_URL}")
        return

    print("Estraggo metadati YouTube ...")
    info = fetch_metadata(VIDEO_URL)
    trascrizione = TRASCRIZIONE_FILE.read_text(encoding="utf-8")

    pk = db.insert_video(
        url=VIDEO_URL,
        video_id=info.get("id") or "UoII79Y1qtA",
        titolo=info.get("title") or "Unbalanced / Broken Wing Butterfly",
        canale=info.get("uploader") or info.get("channel") or "",
        autore=AUTORE,
        durata_sec=info.get("duration"),
        lingua_orig="en",
        strategia=STRATEGIA,
        tag=TAG,
        topics=TOPICS,
        trascrizione=trascrizione,
        sintesi_it=SINTESI_IT,
    )
    print(f"Seed completato. id={pk}")


if __name__ == "__main__":
    main()
