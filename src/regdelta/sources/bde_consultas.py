from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field

from ..util import normalize_ws, parse_ddmmyyyy

COMPLETE = "COMPLETE"
INVALID_STRUCTURE = "INVALID_STRUCTURE"

PARSER_NAME = "bde_consultas"
PARSER_VERSION = "v1"

EXPECTED_HEADERS = {"consulta", "fecha publicación", "fin de la consulta"}

TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.S | re.I)
TH_RE = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S | re.I)
TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
STRONG_RE = re.compile(r"<strong\b[^>]*>(.*?)</strong>", re.S | re.I)
ANCHOR_TAG_RE = re.compile(r"<a\b[^>]*>", re.I)
META_CHARSET_RE = re.compile(r"charset=[\"']?([\w-]+)", re.I)

TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ParseResult:
    parse_status: str
    parse_error: str | None
    entries: list = field(default_factory=list)


@dataclass(frozen=True)
class ConsultaEntry:
    title_raw: str
    published_on: str
    consultation_end_on: str
    anuncio_pdf_urls: tuple[str, ...]
    project_pdf_urls: tuple[str, ...]
    other_document_urls: tuple[str, ...]


def _invalid(message: str) -> ParseResult:
    return ParseResult(INVALID_STRUCTURE, message, [])


def _strip_tags(fragment: str) -> str:
    return normalize_ws(TAG_RE.sub(" ", fragment))


def _attr(tag: str, name: str) -> str | None:
    match = re.search(rf'{name}\s*=\s*"([^"]*)"', tag, re.I) or re.search(
        rf"{name}\s*=\s*'([^']*)'", tag, re.I
    )
    return match.group(1) if match else None


def decode_html(body: bytes, charset_hint: str | None) -> str:
    candidates: list[str] = []
    if charset_hint:
        match = re.search(r"charset=([\w-]+)", charset_hint, re.I)
        if match:
            candidates.append(match.group(1))
    probe = body[:4096].decode("latin-1", "replace")
    meta_match = META_CHARSET_RE.search(probe)
    if meta_match:
        candidates.append(meta_match.group(1))
    candidates.extend(["utf-8", "cp1252", "latin-1"])
    for encoding in candidates:
        try:
            codec = codecs.lookup(encoding)
        except LookupError:
            continue
        try:
            return codec.decode(body)[0]
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("latin-1", "replace")


def parse_consultas(body: bytes, charset_hint: str | None) -> ParseResult:
    text = decode_html(body, charset_hint)
    selected = None
    for table in TABLE_RE.findall(text):
        headers = {_strip_tags(h).casefold() for h in TH_RE.findall(table)}
        if EXPECTED_HEADERS.issubset(headers):
            selected = table
            break
    if selected is None:
        return _invalid("consultation table with expected headers not found")

    entries: list[ConsultaEntry] = []
    for row in TR_RE.findall(selected):
        if "<th" in row.casefold():
            continue
        cells = TD_RE.findall(row)
        if not cells:
            continue
        if len(cells) < 3:
            return _invalid("row with fewer than 3 cells")
        strong = STRONG_RE.search(cells[0])
        title_raw = _strip_tags(strong.group(1)) if strong else _strip_tags(cells[0])
        if not title_raw:
            return _invalid("row without title")
        published_on = parse_ddmmyyyy(cells[1])
        consultation_end_on = parse_ddmmyyyy(cells[2])
        if published_on is None or consultation_end_on is None:
            return _invalid("row without valid published/end dates")
        anuncio: list[str] = []
        proyecto: list[str] = []
        other: list[str] = []
        for anchor_tag in ANCHOR_TAG_RE.findall(cells[0]):
            href = _attr(anchor_tag, "href")
            if not href:
                continue
            link_title = (_attr(anchor_tag, "title") or "").casefold()
            if "anuncio" in link_title:
                anuncio.append(href)
            elif "proyecto" in link_title:
                proyecto.append(href)
            else:
                other.append(href)
        entries.append(
            ConsultaEntry(
                title_raw=title_raw,
                published_on=published_on,
                consultation_end_on=consultation_end_on,
                anuncio_pdf_urls=tuple(anuncio),
                project_pdf_urls=tuple(proyecto),
                other_document_urls=tuple(other),
            )
        )
    if not entries:
        return _invalid("consultation table has no entry rows")
    return ParseResult(COMPLETE, None, entries)
