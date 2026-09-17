# pypdf

## 1. Source freeze

- repo: py-pdf/pypdf — https://github.com/py-pdf/pypdf
- commit inspected: `095d5af1dacc` (main HEAD, review 2026-09-19)
- license: BSD-3-Clause (LICENSE file; GitHub API reports
  NOASSERTION — pin file hash at adoption time)

## 2. Problem fit

- `problems/representation-binding-evidence.md` — primary

Component: `page.images` → `ImageFile(name, data, image,
indirect_reference)`; raw `/Subtype /Image` XObject stream accessible
without decode. Handles `/ObjStm` compressed object streams — which
RegDelta's stdlib `boe_pdf.py` (`N 0 obj` scan only) cannot reach:
captured `boe_dias_pdf__BOE-A-2018-17708.pdf` has no plaintext
`/XObject`/`/Image`/`xref` markers (object-stream compressed).

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | YES (raw stream inside signed PDF blob) |
| exact structural span | YES (object ref = byte range) |
| deterministic | YES (pure python; fails on unsupported filters) |
| fail closed | YES (raises on unparseable) |
| normalized content | NO |

## 4. Verdict

**PORT candidate — gated on falsification.** Extract embedded image
streams from a captured image-heavy BOE PDF; sha256-compare with the
served `/datos/imagenes/disp` PNGs. PASS (≥1 byte-equal stream):
fetched-PNG channel upgrades to authentic-corroborated and pypdf
enters as an optional dependency. FAIL: channels stay independent;
pypdf still usable for PDF_PAGE-level evidence or the verdict
degrades to DISCARD if adoption brings no provable gain.

Determinism requirement: pin version; extraction must be byte-stable
across runs (no decode/re-encode — raw stream bytes only).
