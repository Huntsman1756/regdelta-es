# eurlex-cellar-formex

## 1. Source freeze

- source: op.europa.eu CELLAR + "Retrieving EUR-Lex documents in
  structured, machine-readable formats" (eur-lex.europa.eu)
- review date: 2026-09-19
- license: © EU, reuse-permitted; specs public

## 2. Problem fit

- `problems/representation-binding-evidence.md` — primary

Findings:

- WEMI/FRBR model; resource URIs under
  `publications.europa.eu/resource/`; e-OJ authentic via advanced
  electronic signature (Reg. 216/2013), PDF/A + `_SIG` resources.
- MIME inventory includes `application/xml;type=fmx4` (Formex — the
  OJ's official production XML): **fmx4 manifestation = ZIP with XML
  source + associated image files** — image content ships as
  first-class referenced files inside a byte-stable package.
- `image/png|jpeg|tiff` manifestations exist per-document.
- No ALTO/OCR layer published.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | YES (signature-protected manifestations) |
| exact structural span | PARTIAL |
| deterministic | YES |
| fail closed | PARTIAL |
| normalized content | YES |
| original preserved | YES (WEMI) |
| temporal provenance | YES |

## 4. Verdict

**PATTERN** — confirms official journals ship image-form content as
referenced byte-stable files (Formex zip ≈ BOE XML `<img>`
declarations). RegDelta's XML-declared-image channel is the normal
pattern, not exotic. TEST-CORPUS secondary if an EU profile ever
lands (fmx4 zips are real image-bearing legal XML fixtures).
