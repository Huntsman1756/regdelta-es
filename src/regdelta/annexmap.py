"""Deterministic annex binding: estado/anejo -> BOE page -> official image.

Ported from the G0-C.1 probe. Inputs are all official artifacts:

* the PDF embedded text layer (per page, in ``/Pages`` order) — used ONLY
  to locate printed BOE page numbers and estado headers; never stored as
  representation text;
* the doc.php image sequence (``alt`` numbering, document order);
* the ``pagina_inicial`` metadata of the daily XML;
* optional correction anchors: ``(boe_page, estado_code)`` pairs cited
  literally by a correction instrument.

The page <-> image rule is DERIVED: annex images fill the document's
trailing pages in order (image i of N <-> page (last_page - N + 1 + i)).
It becomes ANCHORED only when independent official anchors (correction
page+estado citations) all match; otherwise UNANCHORED_DERIVED and the
binding must not be silently promoted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PARSER_NAME = "annexmap"
PARSER_VERSION = "v1"

# estado code at the start of a page's text layer; the embedded layer
# sometimes letter-spaces codes ("F I  101"), so the prefix tolerates
# optional inner spaces and numeric tails are stripped of spaces.
CODE_RE = re.compile(
    r"\b(F\s*I|F\s*C|P\s*I|P\s*C|P\s*A|U\s*E\s*M|A\s*V\s*E|A\s*N\s*E\s*J\s*O)"
    r"\s+(\d[\d\- .]*\d|\d)"
)

_PAGE_NUM_RE = re.compile(r"P[áa]g\.\s*([\d\s]+)")
_ANEJO_RE = re.compile(
    r"A\s*N\s*E\s*J\s*O\s+(\d+(?:\s*\.\s*\d+)*)")

# pages listing >= this many distinct codes are "índice" pages
INDEX_CODE_THRESHOLD = 10

_CODE_PREFIXES = ("FI", "FC", "PI", "PC", "PA", "UEM", "AVE")


def _norm_code(prefix: str, tail: str) -> str:
    prefix = re.sub(r"\s+", "", prefix)
    tail = re.sub(r"\s+", "", tail).rstrip(".")
    # "FI 150.9" == "FI 150-9"
    if "." in tail and "-" not in tail:
        tail = tail.replace(".", "-", 1)
    return f"{prefix} {tail}"


def estado_root(code: str) -> str:
    """'FI 105-1' -> 'FI 105'; 'FI 142-1.1' -> 'FI 142'; 'UEM 3' -> 'UEM 3'."""
    m = re.match(r"([A-Z]+)\s*(\d+)", code)
    if m and m.group(1) in _CODE_PREFIXES:
        return f"{m.group(1)} {m.group(2)}"
    return code.split("-")[0].strip()


def distinct_codes(text: str) -> list[str]:
    seen: list[str] = []
    for m in CODE_RE.finditer(text):
        c = _norm_code(m.group(1), m.group(2))
        if c not in seen:
            seen.append(c)
    return seen


def first_code(text: str) -> str | None:
    m = CODE_RE.search(text[:600])
    if not m:
        return None
    return _norm_code(m.group(1), m.group(2))


def page_number(text: str) -> int | None:
    m = _PAGE_NUM_RE.search(text[:200])
    if not m:
        return None
    digits = re.sub(r"\s+", "", m.group(1))
    return int(digits) if digits.isdigit() else None


def anejo_headings(text: str) -> list[str]:
    """All 'ANEJO N(.M)' headings on a page -> ['7', '7.1']."""
    return [re.sub(r"\s+", "", m.group(1))
            for m in _ANEJO_RE.finditer(text[:500])]


@dataclass
class PageEntry:
    pdf_index: int
    boe_page: int
    kind: str            # PREANNEX | INDEX | CONTENT | CONTINUATION
    code_detected: str | None
    span_root: str | None = None   # estado family owning the page
    img_alt: int | None = None
    anejo: str | None = None       # top-level anejo number owning the page


@dataclass
class AnnexMap:
    pages: list[PageEntry]
    # exact code -> ordered boe pages where that code heads the page
    # (continuation pages attach to the open span)
    code_pages: dict[str, list[int]] = field(default_factory=dict)
    # estado root -> ordered pages (all sub-codes)
    root_pages: dict[str, list[int]] = field(default_factory=dict)
    # 'N' or 'N.M' -> ordered pages; 'N.indice' -> index run pages
    anejo_pages: dict[str, list[int]] = field(default_factory=dict)
    img_by_page: dict[int, int] = field(default_factory=dict)  # boe_page->alt
    anchors: list[dict] = field(default_factory=list)
    anchored: bool = False

    def subject_pages(self, locator_key: str) -> list[int] | None:
        """Pages bound to a subject locator, or None if unresolvable."""
        if locator_key.startswith("estado:"):
            code = locator_key[7:]
            if code in self.code_pages:
                return self.code_pages[code]
            root = estado_root(code)
            return self.root_pages.get(root)
        if locator_key.startswith("anejo:"):
            return self.anejo_pages.get(locator_key[6:])
        return None


def build_annex_map(
    page_texts: list[str],
    start_boe_page: int,
    n_images: int,
    anchors: list[tuple[int, str]],
) -> AnnexMap:
    """Build the page/state/image map for one instrument's annex.

    ``page_texts``: embedded text layer per PDF page, in /Pages order.
    ``n_images``: number of annex images in doc order (they occupy the
    trailing pages).
    """
    n_pages = len(page_texts)
    first_img_pdf = n_pages - n_images

    pages: list[PageEntry] = []
    for i, text in enumerate(page_texts):
        boe = page_number(text)
        # daily-issue pages are strictly sequential; the embedded layer
        # occasionally garbles the printed number, so it is only trusted
        # when it matches the expected sequence
        if boe is None or boe != start_boe_page + i:
            boe = start_boe_page + i
        if i < first_img_pdf:
            pages.append(PageEntry(i, boe, "PREANNEX", None))
            continue
        codes = distinct_codes(text)
        kind = ("INDEX" if len(codes) >= INDEX_CODE_THRESHOLD
                else "CONTENT" if codes else "CONTINUATION")
        pages.append(PageEntry(
            i, boe, kind, first_code(text) if kind == "CONTENT" else None,
            img_alt=i - first_img_pdf + 1))

    img_by_page = {p.boe_page: p.img_alt for p in pages if p.img_alt}

    # --- estado spans ------------------------------------------------------
    code_pages: dict[str, list[int]] = {}
    root_pages: dict[str, list[int]] = {}
    current_root: str | None = None
    current_code: str | None = None
    for pg in pages:
        if pg.kind in ("PREANNEX", "INDEX"):
            current_root = current_code = None
            continue
        if pg.kind == "CONTENT" and pg.code_detected:
            # a detected header opens a new span; a CONTENT page whose
            # header was not detected (letter-spacing glitches) keeps the
            # open span — same rule as the G0-C.1 probe
            current_code = pg.code_detected
            current_root = estado_root(current_code)
            code_pages.setdefault(current_code, [])
        pg.span_root = current_root
        if current_code:
            code_pages[current_code].append(pg.boe_page)
        if current_root:
            root_pages.setdefault(current_root, []).append(pg.boe_page)

    # --- anejo spans -------------------------------------------------------
    # Detected 'ANEJO N(.M)' headings; missing top-level headings are
    # filled positionally between known boundaries and family index runs.
    headings: list[tuple[int, str]] = []   # (pdf_index, 'N' or 'N.M')
    for pg in pages:
        for h in anejo_headings(page_texts[pg.pdf_index]):
            headings.append((pg.pdf_index, h))

    # index runs: maximal INDEX runs; each opens the anejo whose content
    # follows, so its start is a block boundary when no heading was detected
    index_runs: list[tuple[int, int]] = []   # (first_pdf_index, last)
    run_start = None
    for pg in pages:
        if pg.kind == "INDEX":
            if run_start is None:
                run_start = pg.pdf_index
        elif run_start is not None:
            index_runs.append((run_start, pg.pdf_index - 1))
            run_start = None
    if run_start is not None:
        index_runs.append((run_start, pages[-1].pdf_index))

    annex_first = pages[first_img_pdf].pdf_index if n_images else n_pages
    heading_at = {i: h for i, h in headings}
    top_boundaries: list[int] = []
    sub_boundaries: list[tuple[int, str]] = []
    for i, h in headings:
        if "." in h:
            sub_boundaries.append((i, h))
        else:
            top_boundaries.append(i)
    for s, _e in index_runs:
        if s not in heading_at:
            top_boundaries.append(s)
    top_boundaries = sorted(set(top_boundaries))

    anejo_of_index: dict[int, str] = {}
    # positional numbering: block starts map to anejos 1..N in order when
    # no heading declares the number; declared headings win
    declared = {i: h for i, h in headings if "." not in h}
    ordered_starts = top_boundaries + ([pages[-1].pdf_index + 1]
                                       if top_boundaries else [])
    spans: dict[str, list[int]] = {}
    if top_boundaries:
        # assign numbers: declared numbers fixed; the gaps filled
        # sequentially among the unlabeled starts
        expected = sorted(set(declared.values()), key=lambda x: [
            int(p) for p in x.split(".")])
        next_num = 1
        for pos, start in enumerate(top_boundaries):
            end = ordered_starts[pos + 1] - 1
            if start in declared:
                num = declared[start]
                next_num = int(num.split(".")[0]) + 1
            else:
                while str(next_num) in declared.values():
                    next_num += 1
                num = str(next_num)
                next_num += 1
            for pg in pages:
                if start <= pg.pdf_index <= end and pg.pdf_index >= annex_first:
                    pg.anejo = num
                    spans.setdefault(num, []).append(pg.boe_page)
            # this anejo's index run, if it begins with one
            for s, e in index_runs:
                if s == start:
                    key = f"{num}.indice"
                    spans[key] = [p.boe_page for p in pages
                                  if s <= p.pdf_index <= e]
    # sub-anejo headings within their parent span
    for pos, (start, h) in enumerate(sorted(sub_boundaries)):
        nxt = (sub_boundaries[pos + 1][0]
               if pos + 1 < len(sub_boundaries) else None)
        parent_end = None
        for i, hh in headings:
            if "." not in hh and i > start:
                parent_end = i - 1
                break
        end = min(x for x in (nxt - 1 if nxt else None, parent_end,
                              pages[-1].pdf_index) if x is not None)
        spans[h] = [p.boe_page for p in pages
                    if start <= p.pdf_index <= end]

    # --- correction anchors ------------------------------------------------
    anchor_rows = []
    for boe, code in anchors:
        pg = next((p for p in pages if p.boe_page == boe), None)
        detected = pg.code_detected if pg else None
        match = bool(pg) and (
            (detected is not None
             and estado_root(detected) == estado_root(code))
            or (pg.span_root is not None
                and pg.span_root == estado_root(code)))
        anchor_rows.append({
            "page": boe, "code": code, "detected": detected,
            "span_root": pg.span_root if pg else None,
            "img_alt": pg.img_alt if pg else None, "match": match,
        })

    return AnnexMap(
        pages=pages,
        code_pages=code_pages,
        root_pages=root_pages,
        anejo_pages=spans,
        img_by_page=img_by_page,
        anchors=anchor_rows,
        anchored=bool(anchor_rows) and all(a["match"] for a in anchor_rows),
    )
