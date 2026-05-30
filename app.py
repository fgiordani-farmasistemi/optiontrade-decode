"""Flask UI for OptionTrade_decode."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
import markdown as md

load_dotenv(Path(__file__).parent / ".env")

import db  # noqa: E402  (load env first)
from ingest import (  # noqa: E402
    IngestError,
    NeedsWhisperConfirmation,
    has_api_key,
    ingest_url,
    provider_label,
)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "optiontrade-decode-local")

db.init_db()


@app.context_processor
def inject_globals():
    return {
        "api_key_present": has_api_key(),
        "provider_label": provider_label(),
    }


@app.template_filter("md")
def render_markdown(text: str) -> str:
    return md.markdown(text or "", extensions=["fenced_code", "tables"])


@app.template_filter("hms")
def format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@app.route("/")
def index():
    strategia = (request.args.get("strategia") or "").strip() or None
    canale = (request.args.get("canale") or "").strip() or None
    autore = (request.args.get("autore") or "").strip() or None
    recenti = db.list_recent(50, strategia=strategia, canale=canale, autore=autore)
    return render_template(
        "index.html",
        recenti=recenti,
        facets=db.facets(),
        filtro_strategia=strategia,
        filtro_canale=canale,
        filtro_autore=autore,
    )


@app.route("/ingest", methods=["POST"])
def ingest_route():
    if not has_api_key():
        flash("Chiave API non configurata per il provider attivo.", "error")
        return redirect(url_for("index"))
    url = (request.form.get("url") or "").strip()
    if not url:
        flash("Inserisci un URL YouTube.", "error")
        return redirect(url_for("index"))
    force_whisper = request.form.get("force_whisper") == "1"
    try:
        video_pk = ingest_url(url, force_whisper=force_whisper)
    except NeedsWhisperConfirmation as exc:
        return render_template("whisper_confirm.html", info=exc.info)
    except IngestError as exc:
        flash(f"Errore: {exc}", "error")
        return redirect(url_for("index"))
    except Exception as exc:  # noqa: BLE001
        flash(f"Errore inatteso: {exc}", "error")
        return redirect(url_for("index"))
    return redirect(url_for("video_detail", video_pk=video_pk))


@app.route("/search")
def search():
    query = (request.args.get("q") or "").strip()
    strategia = (request.args.get("strategia") or "").strip() or None
    canale = (request.args.get("canale") or "").strip() or None
    autore = (request.args.get("autore") or "").strip() or None
    risultati = db.search(query, strategia=strategia, canale=canale, autore=autore)
    return render_template(
        "search.html",
        query=query,
        risultati=risultati,
        facets=db.facets(),
        filtro_strategia=strategia,
        filtro_canale=canale,
        filtro_autore=autore,
    )


@app.route("/v/<int:video_pk>")
def video_detail(video_pk: int):
    row = db.get_video(video_pk)
    if not row:
        abort(404)
    return render_template("video.html", v=row)


@app.route("/v/<int:video_pk>/edit", methods=["POST"])
def video_edit(video_pk: int):
    row = db.get_video(video_pk)
    if not row:
        abort(404)
    strategia = (request.form.get("strategia") or "").strip()
    tag = (request.form.get("tag") or "").strip()
    autore = (request.form.get("autore") or "").strip()
    topics = (request.form.get("topics") or "").strip()
    db.update_meta(video_pk, strategia=strategia, tag=tag, autore=autore, topics=topics)
    flash("Modifiche salvate.", "ok")
    return redirect(url_for("video_detail", video_pk=video_pk))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
