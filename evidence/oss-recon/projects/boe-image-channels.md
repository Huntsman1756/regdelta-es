# boe-image-channels (official BOE image evidence inventory)

## 1. Source freeze

- source: boe.es official endpoints, verified against captured
  evidence in `evidence/port-cnmv/split-v2/` and `evidence/**/raw`
- review date: 2026-09-19 (CORE-GAP recon)
- license: N/A (official source, not a software project)

## 2. Problem fit

- `problems/representation-binding-evidence.md` — primary

Verified inventory:

| endpoint | serves | status |
|---|---|---|
| `/diario_boe/xml.php?id=` | diario XML; `<p class="imagen"><img src="/datos/imagenes/disp/…">` | captured |
| `/buscar/doc.php?id=` | doc HTML; inline imgs + `alt="N"` page-strip channel | captured |
| `/boe/dias/{Y}/{M}/{D}/pdfs/{ID}.pdf` | electronically signed PDF — the ONLY authentic format since 2009 (RD 181/2008) | captured |
| `/datos/imagenes/disp/{Y}/{issue}/{file}.png` | document/annex images, stable URLs | confirmed live |
| `/diario_boe/epub.php?id=` | ePUB bundling images (sección I, since 2010) | documented |
| `/datosabiertos/api/boe/sumario/` | REST metadata: url_pdf/url_html + page ranges; NO image URLs | documented |
| `/datosabiertos/api/legislacion-consolidada/` | BOE's own consolidated text | synthetic consolidation — not evidence |

Authenticity hierarchy: signed PDF (authentic) > XML/HTML-declared
images (official, informative grade) > derived renderings.

Correction recorded: guessed endpoints `/diario_boe/imagenes/`,
`/boe/dias/.../images/` do NOT exist; the real image surface is
`/datos/imagenes/disp/` plus per-document declarations.

## 3. Key finding

Three byte-provable image channels, decreasing authenticity:

1. embedded raw image streams inside the signed PDF (authentic-grade;
   requires ObjStm-capable parsing — pypdf BSD or stdlib extension);
2. `/datos/imagenes/disp` PNGs declared inside the official XML blob
   (implemented: `boe_diario` → `Node.img_src` → `blob_sha256`);
3. doc.php `alt="N"` page-strip (implemented via annexmap).

Byte-equality falsification (WS-D): extract embedded PDF image stream
via pypdf, sha256-compare with served PNG. PASS upgrades the PNG
channel to authentic-corroborated; FAIL keeps them independent
evidence classes.

## 4. Verdict

**PATTERN** — the image-evidence model itself: representations whose
locator records both channels when available.
