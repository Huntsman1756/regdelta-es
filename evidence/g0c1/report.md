# G0-C.1 — Annex/State Evidence Probe

Scope: determine whether the annexed **estados** of Circular 4/2017
(BOE-A-2017-14334) — published as page images, which G0-C classified as
`old_text NOT_PROVEN` — can nonetheless participate in a deterministic,
reproducible, auditable modification chain **without OCR**.

Verdict: **PROVEN at representation level.** The factual chain

```text
estado FI XXX
  → old official representation  (BOE page image, SHA-256)
  → MODIFIED_BY
  → Circular N/AAAA              (official locator clause)
  → new official representation  (structured table / literal text / image, SHA-256)
```

is reconstructible end-to-end from official sources for every case tried,
including chained, correction, provision-level, and image→image cases. A
textual `old→new` *content* diff remains unavailable on image sides —
that is now expressed as a diff-level taxonomy, not as a reconstruction
failure.

## 1. The correction to G0-C's framing

G0-C conflated "no old text" with "no old representation". The correct
decomposition, demonstrated here:

```text
old textual representation    NOT_PROVEN   (XML carries <img>, no text)
old official representation   PROVEN       (official BOE page image, SHA-256,
                                            bound to estado + BOE page)
change declaration            PROVEN       (modifier's locator clause, literal)
semantic old→new diff         NOT_PROVEN   (would require interpreting the image)
```

## 2. How the binding works (all mechanical, no LLM)

```text
diario XML        326 consecutive <p class="imagen"> after the signature
doc.php           each <img> carries alt="1..326"   (explicit sequence, OBSERVED)
metadatos         pagina_inicial=119454, pagina_final=120041   (OBSERVED)
official PDF      /Pages tree = exactly 588 pages = 119454..120041   (OBSERVED)
                  embedded text layer shows the signature ends on p.119715
    ⇒ alt=N ↔ BOE page 119715+N                     (DERIVED)
PDF text layer    estado code printed on each content page
                  ("FI 105-1", "FI 142-1.1", "FC 201-2", "UEM 3", …)   (DERIVED)
correction        BOE-A-2018-2041 cites (página, estado) literally for
                  10 items inside the annex                        (OBSERVED)
```

The embedded text layer is part of the official PDF artifact (BOE's own
OCR layer); we extract it, we do not perform OCR.

## 3. Anchor validation — 10/10

Every page the correction cites was cross-checked against the code detected
in the PDF text layer (`annex-map.json → correction_anchors`):

| correction page | estado | detected code | image |
|---|---|---|---|
| 119822 | FI 101 | FI 101 | alt 107 |
| 119824 | FI 102-2 | FI 102-2 | alt 109 |
| 119827 | FI 103-2 | FI 103-2 | alt 112 |
| 119862 | FI 131-1.1 | FI 131 (root page) | alt 147 |
| 119864 | FI 131-2.1 | FI 131-2.1 | alt 149 |
| 119865 | FI 131-2.2 | FI 131-2.2 | alt 150 |
| 119882 | FI 132 | none — continuation page inside FI 132 span | alt 167 |
| 119901 | FI 140-3 | FI 140-3 | alt 186 |
| 119914 | FI 150-7 | FI 150-7 | alt 199 |
| 119938 | FC 140-3 | FC 140-3 | alt 223 |

Three of the bound images were also verified visually (FI 102-2, FI 105-1,
FI 142-1.1, FI 100-14 of C.2/2020). Two OCR quirks documented and handled:
letter-spaced codes ("F I  101") normalized by the detector; índice pages
(≥10 distinct codes, 8 pages) excluded from estado spans.

## 4. Estado map

`annex-map.json`: 99 estado roots across 326 annex pages
(250 CONTENT + 68 CONTINUATION + 8 INDEX). Examples:

```text
FI 102  → pages 119823–119824   (imgs alt 108–109)
FI 105  → pages 119835–119836   (imgs alt 120–121)
FI 106  → pages 119837–119843   (imgs alt 122–128)
FI 142  → pages 119907–119908   (imgs alt 192–193)
FI 150  → pages 119911–119917   (imgs alt 196–202)
```

Granularity is **page-level**: a page may hold a whole estado, part of one,
or the tail of one plus the head of the next. Sub-page regions are not
separable without rendering — recorded per case as `granularity_note`.

## 5. Experimental cases (`state-cases.json`)

| case | estado | modifier | old repr | new repr | diff levels |
|---|---|---|---|---|---|
| S1 | FI 102-2 | 2018-2041 corr. item 5 | IMAGE p.119824 | deletion declared literally | DECLARED + VISUAL_PREDECESSOR |
| S2 | FI 131-2.2 | 2018-2041 corr. item 9 | IMAGE p.119865 | literal nota (b) text | DECLARED + VISUAL_PREDECESSOR |
| S3 | FI 142-1.1 | 2/2018 → 1/2025 | IMAGE p.119907 → TABLE | TABLE (2018) → TABLE (2025) | hop1 VISUAL_PREDECESSOR; hop2 **TEXT_DIFF_PROVEN** |
| S4 | FI 105 | 1/2025 | IMAGE pp.119835–836 | structured table (C1/2025 kid 213) | VISUAL_PREDECESSOR |
| S5 | FI 100-14 | 2/2020 | IMAGE p.119818 | **IMAGE** p.40313 of C.2/2020 | VISUAL_PREDECESSOR |
| S6 | FI 106-1.1 nota (a) | 2/2018 | IMAGE p.119837 | literal paragraph text | DECLARED + VISUAL_PREDECESSOR |

Findings:

- **Chained modification works**: hop 2 of S3 has structured text on both
  sides because C.2/2018 republished FI 142-1.1 as a `<table>`; the
  image-bound predecessor only limits hop 1.
- **Image→image exists**: C.2/2020's own anejos 4–5 are 9 page images —
  even modifiers publish estados visually. S5 shows the chain still closes
  at artifact level (both sides SHA-256'd).
- **Corrections are dual anchors**: they declare the change literally *and*
  cite the BOE page, independently validating the image↔estado binding.
- **Region-level changes** (S6: a nota inside a page) bind at page level;
  the literal new text is auditable, the old note stays inside the image.

## 6. Consequences for RegDelta

1. Blocks need a `representation_kind` (`TEXT` / `TABLE` / `IMAGE` /
   `PDF_PAGE`) with `content_sha256` + `artifact_locator` (URL, BOE page,
   alt); `text_content` nullable. This is now *demonstrated* necessary —
   modifiers themselves publish image annexes (C.2/2020, C.5/2020).
2. `change_events` need `diff_level` with the four-value taxonomy above;
   `SEMANTIC_DIFF_NOT_AVAILABLE` is a normal outcome, not an error.
3. G0-C's verdict stands as `PARTIAL` for *textual* reconstruction, but the
   *factual* modification history is reconstructible in full: every change
   is discovered, located, dated, and bound to hashed official artifacts on
   both sides.

## 7. Remaining gaps (honest list)

- Page↔estado binding is DERIVED (anchored by 10/10 correction citations +
  PDF text layer + sequential alt numbering), not declared anywhere as a
  machine-readable mapping. If a future target's correction cites no annex
  pages, the anchor set may be weaker; the alt→page rule still holds.
- The PDF text layer is BOE's OCR: adequate for estado-code detection,
  **not** promoted to legal `old_text` (it is evidence for *location*, not
  *content*). Content-level old→new on image sides would need OCR (out of
  scope) or a future structured republication.
- Modifier-annex image→estado binding requires running the same page-map
  machinery per modifier PDF (demonstrated once for C.2/2020, p.40313).
- Sub-page granularity (which part of a page is the estado) is not
  representable without rendering; the artifact is the page.

## 8. Evidence

```text
evidence/g0c1/
  page-map.json         588 pages, text layer, true /Pages order
  image-inventory.json  326 imgs: alt -> src -> BOE page
  annex-map.json        99 estados -> page spans -> imgs; 10/10 anchors
  state-cases.json      6 representation-level chain fichas
  raw/                  23 artifacts (11 target images, 9 modifier images,
                        2 PDFs [1 already in g0c], 1 doc.html) + manifest.json
```

All raws SHA-256-verified by `tests/g0c1/test_probe_g0c1.py` (7 tests,
offline). Total new evidence ≈ 4.6 MB.
