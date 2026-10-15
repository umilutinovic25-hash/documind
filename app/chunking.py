"""Sentence-aware chunking: never exceeds max_chars (except a single unbreakable token run)."""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?…])\s+|\n+")


def _pieces(text: str, max_chars: int) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if not para:
            continue
        for s in _SENT.split(para):
            s = s.strip()
            while len(s) > max_chars:  # hard split a runaway "sentence"
                cut = s.rfind(" ", 0, max_chars)
                cut = cut if cut > max_chars // 2 else max_chars
                out.append(s[:cut].strip())
                s = s[cut:].strip()
            if s:
                out.append(s)
    return out


def chunk_text(text: str, max_chars: int = 600, overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for piece in _pieces(text, max_chars):
        if cur and len(cur) + 1 + len(piece) > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else ""
            cur = f"{tail} {piece}".strip()
            if len(cur) > max_chars:
                cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        chunks.append(cur)
    return chunks


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _table_chunks(rows: list[str], max_chars: int) -> list[str]:
    """Keep a markdown table together; split by rows (repeating the header) only when oversized."""
    whole = "\n".join(rows)
    if len(whole) <= max_chars * 2:
        return [whole]
    head, body = rows[:2], rows[2:]
    out, cur = [], list(head)
    for r in body:
        if len("\n".join(cur + [r])) > max_chars * 2 and len(cur) > len(head):
            out.append("\n".join(cur))
            cur = list(head)
        cur.append(r)
    if len(cur) > len(head):
        out.append("\n".join(cur))
    return out


def chunk_document(text: str, max_chars: int = 600, overlap: int = 100) -> list[tuple[str, str]]:
    """Structure-aware chunking: returns (heading, chunk).

    Markdown headings scope the chunks beneath them (the heading travels with each chunk as context)
    and tables are kept intact instead of being flattened into one run-on line.
    """
    out: list[tuple[str, str]] = []
    heading, prose, table = "", [], []
    in_code = False

    def flush_prose():
        if prose:
            out.extend((heading, c) for c in chunk_text("\n".join(prose), max_chars, overlap))
            prose.clear()

    def flush_table():
        if table:
            out.extend((heading, c) for c in _table_chunks(list(table), max_chars))
            table.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            flush_prose(); flush_table()
            heading = m.group(2)
        elif not in_code and line.lstrip().startswith("|"):
            flush_prose()
            table.append(line.strip())
        else:
            flush_table()
            prose.append(line)
    flush_prose(); flush_table()
    return out
