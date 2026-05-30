"""Convert a YouTube auto-caption VTT into deduplicated plain text."""
from __future__ import annotations

import re
from pathlib import Path

_inline_tag = re.compile(r"<[^>]+>")
_timestamp = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> ")


def clean_vtt_text(vtt: str) -> str:
    out: list[str] = []
    last = None
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        if _timestamp.match(raw):
            continue
        line = _inline_tag.sub("", line).strip()
        if not line or line == last:
            continue
        out.append(line)
        last = line
    return " ".join(out)


def clean_vtt_file(path: Path) -> str:
    return clean_vtt_text(path.read_text(encoding="utf-8"))
