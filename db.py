"""SQLite + FTS5 storage layer for OptionTrade_decode."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).parent / "data" / "videos.sqlite"

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT NOT NULL UNIQUE,
    video_id     TEXT NOT NULL,
    titolo       TEXT NOT NULL DEFAULT '',
    canale       TEXT NOT NULL DEFAULT '',
    autore       TEXT NOT NULL DEFAULT '',
    durata_sec   INTEGER,
    lingua_orig  TEXT NOT NULL DEFAULT '',
    strategia    TEXT NOT NULL DEFAULT '',
    tag          TEXT NOT NULL DEFAULT '',
    topics       TEXT NOT NULL DEFAULT '',
    trascrizione TEXT NOT NULL DEFAULT '',
    sintesi_it   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
    titolo, strategia, tag, topics, autore, sintesi_it,
    content='videos', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS videos_ai AFTER INSERT ON videos BEGIN
    INSERT INTO videos_fts(rowid, titolo, strategia, tag, topics, autore, sintesi_it)
    VALUES (new.id, new.titolo, new.strategia, new.tag, new.topics, new.autore, new.sintesi_it);
END;

CREATE TRIGGER IF NOT EXISTS videos_ad AFTER DELETE ON videos BEGIN
    INSERT INTO videos_fts(videos_fts, rowid, titolo, strategia, tag, topics, autore, sintesi_it)
    VALUES('delete', old.id, old.titolo, old.strategia, old.tag, old.topics, old.autore, old.sintesi_it);
END;

CREATE TRIGGER IF NOT EXISTS videos_au AFTER UPDATE ON videos BEGIN
    INSERT INTO videos_fts(videos_fts, rowid, titolo, strategia, tag, topics, autore, sintesi_it)
    VALUES('delete', old.id, old.titolo, old.strategia, old.tag, old.topics, old.autore, old.sintesi_it);
    INSERT INTO videos_fts(rowid, titolo, strategia, tag, topics, autore, sintesi_it)
    VALUES (new.id, new.titolo, new.strategia, new.tag, new.topics, new.autore, new.sintesi_it);
END;
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Crea schema e applica eventuali migration in modo idempotente."""
    with connect() as conn:
        conn.executescript(BASE_SCHEMA)
        _migrate_add_columns(conn)
        _ensure_fts(conn)


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Aggiunge colonne autore/topics ai DB pre-esistenti."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)")}
    if "autore" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN autore TEXT NOT NULL DEFAULT ''")
    if "topics" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN topics TEXT NOT NULL DEFAULT ''")


def _ensure_fts(conn: sqlite3.Connection) -> None:
    """Crea/aggiorna la virtual table FTS5. Se la struttura colonne e' cambiata
    rispetto a un'eventuale versione precedente, la ricostruiamo da zero."""
    needs_rebuild = False
    fts_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='videos_fts'"
    ).fetchone()
    if fts_exists:
        # Conta le colonne dichiarate per la fts.
        cols = conn.execute("PRAGMA table_info(videos_fts)").fetchall()
        expected = {"titolo", "strategia", "tag", "topics", "autore", "sintesi_it"}
        actual = {c[1] for c in cols}
        if not expected.issubset(actual):
            needs_rebuild = True
    if needs_rebuild:
        for trg in ("videos_ai", "videos_ad", "videos_au"):
            conn.execute(f"DROP TRIGGER IF EXISTS {trg}")
        conn.execute("DROP TABLE IF EXISTS videos_fts")
    conn.executescript(FTS_SCHEMA)
    if needs_rebuild:
        # Ripopola la FTS dai record esistenti.
        conn.execute(
            "INSERT INTO videos_fts(rowid, titolo, strategia, tag, topics, autore, sintesi_it) "
            "SELECT id, titolo, strategia, tag, topics, autore, sintesi_it FROM videos"
        )


def insert_video(
    *,
    url: str,
    video_id: str,
    titolo: str,
    canale: str,
    autore: str,
    durata_sec: int | None,
    lingua_orig: str,
    strategia: str,
    tag: str,
    topics: str,
    trascrizione: str,
    sintesi_it: str,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO videos (url, video_id, titolo, canale, autore, durata_sec,
                lingua_orig, strategia, tag, topics, trascrizione, sintesi_it, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url, video_id, titolo, canale, autore, durata_sec,
                lingua_orig, strategia, tag, topics, trascrizione, sintesi_it,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        return int(cur.lastrowid)


def get_video(video_pk: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM videos WHERE id = ?", (video_pk,)).fetchone()


def find_by_url(url: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM videos WHERE url = ?", (url,)).fetchone()


def list_recent(
    limit: int = 50,
    *,
    strategia: str | None = None,
    canale: str | None = None,
    autore: str | None = None,
) -> list[sqlite3.Row]:
    where, params = _filter_clauses(strategia, canale, autore)
    sql = (
        "SELECT id, titolo, strategia, tag, topics, canale, autore, created_at "
        "FROM videos"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def search(
    query: str,
    limit: int = 50,
    *,
    strategia: str | None = None,
    canale: str | None = None,
    autore: str | None = None,
) -> list[sqlite3.Row]:
    """Full-text search across titolo/strategia/tag/topics/autore/sintesi_it,
    with optional filters."""
    if not query.strip():
        return list_recent(limit, strategia=strategia, canale=canale, autore=autore)

    fts_query = _to_fts_query(query)
    where, params = _filter_clauses(strategia, canale, autore, table_alias="v")
    sql = (
        "SELECT v.id, v.titolo, v.strategia, v.tag, v.topics, v.canale, v.autore, v.created_at, "
        "snippet(videos_fts, 5, '<mark>', '</mark>', ' ... ', 12) AS snippet "
        "FROM videos_fts "
        "JOIN videos v ON v.id = videos_fts.rowid "
        "WHERE videos_fts MATCH ?"
    )
    params.insert(0, fts_query)
    if where:
        sql += " AND " + " AND ".join(where)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def _filter_clauses(
    strategia: str | None,
    canale: str | None,
    autore: str | None,
    table_alias: str = "",
) -> tuple[list[str], list]:
    prefix = f"{table_alias}." if table_alias else ""
    where: list[str] = []
    params: list = []
    if strategia:
        where.append(f"{prefix}strategia = ?")
        params.append(strategia)
    if canale:
        where.append(f"{prefix}canale = ?")
        params.append(canale)
    if autore:
        where.append(f"{prefix}autore = ?")
        params.append(autore)
    return where, params


def facets() -> dict[str, list[tuple[str, int]]]:
    """Conteggi distinct di strategia, canale e autore per chip filtro."""
    with connect() as conn:
        strategie = conn.execute(
            "SELECT strategia, COUNT(*) AS n FROM videos "
            "WHERE strategia != '' GROUP BY strategia ORDER BY n DESC, strategia"
        ).fetchall()
        canali = conn.execute(
            "SELECT canale, COUNT(*) AS n FROM videos "
            "WHERE canale != '' GROUP BY canale ORDER BY n DESC, canale"
        ).fetchall()
        autori = conn.execute(
            "SELECT autore, COUNT(*) AS n FROM videos "
            "WHERE autore != '' GROUP BY autore ORDER BY n DESC, autore"
        ).fetchall()
    return {
        "strategia": [(r["strategia"], r["n"]) for r in strategie],
        "canale": [(r["canale"], r["n"]) for r in canali],
        "autore": [(r["autore"], r["n"]) for r in autori],
    }


def update_meta(
    video_pk: int,
    *,
    strategia: str,
    tag: str,
    autore: str | None = None,
    topics: str | None = None,
) -> None:
    fields = ["strategia = ?", "tag = ?"]
    params: list = [strategia, tag]
    if autore is not None:
        fields.append("autore = ?")
        params.append(autore)
    if topics is not None:
        fields.append("topics = ?")
        params.append(topics)
    params.append(video_pk)
    with connect() as conn:
        conn.execute(f"UPDATE videos SET {', '.join(fields)} WHERE id = ?", params)


def _to_fts_query(raw: str) -> str:
    """Convert free-text input into an FTS5 prefix-match query."""
    tokens = [t for t in raw.replace('"', " ").split() if t]
    return " ".join(f'"{t}"*' for t in tokens) if tokens else raw
