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

## 5. EXP-D1 falsification result (2026-09-21, pypdf 6.14.2)

**FAIL — byte equality falsified.** Experiment ledger:
`evidence/core-gap/wsd/exp-d1/run{1,2}/exp-d1-ledger.json` (two
fresh runs byte-identical).

- source: `boe_dias_pdf__BOE-A-2017-14334.pdf` (39,355,759 B,
  sha256 `0923cc0a…f16e`, 588 pages — the whole-issue signed PDF
  served at the document URL).
- `/Image` XObjects reachable from all 588 pages (recursive through
  Form XObjects) + inline `BI…ID…EI` scan: **2 unique objects**
  (refs 68/69, shared header logos, `/CCITTFaxDecode`), **0 inline
  images**, **0 image XObjects on the annex pages**.
- The annex figures are **vector content** in the signed PDF — there
  is no embedded raster stream to equate with the served PNG.
- 204 captured official PNG assets: **0 byte-equal matches** (raw
  stream or decoded derivative).

Consequence per the preregistered rule: channels stay independent
evidence classes. The served-PNG channel remains official
informative-grade; the signed-PDF channel provides page/object
association only (`REPRESENTATION_ASSOCIATION_ONLY`). **pypdf NOT
adopted** — the experiment's positive-gain condition did not hold,
and ObjStm/XObject access alone adds no provable evidence; stdlib
`boe_pdf` remains the only PDF parser.
