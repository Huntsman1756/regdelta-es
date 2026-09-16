# PORT-CNMV-0 — OSS reconnaissance record

Prior-art review for the CNMV discovery surface, performed on GitHub
before this gate. Recorded per AGENTS.md OSS-first rule.

| Project | Verdict for RegDelta | Reuse |
|---|---|---|
| `Huntsman1756/esdata @ 80b9eb0` | **PORT / REUSE** | Deterministic discovery of historical CNMV Circular year-range pages + BOE link extraction, with fixtures. Ported to `scripts/port-cnmv/scout_cnmv.py` (same index → year-range → BOE-link flow, stdlib). No new crawler written. |
| `Ansvar-Systems/spanish-financial-regulation-mcp @ 772d04b` | **PATTERN + TEST-CORPUS** | Independently confirms the same CNMV surface: index → year pages → BOE/CNMV document links. Apache-2.0. Semantics not ported. |
| same Ansvar `ingest-cnmv.ts` | **negative evidence** | Marks every Circular `en_vigor` and takes `effective_date` from listing context — incompatible with proof-or-abstain. Practical evidence of what not to copy. |
| `regulatory-workstation @ 3d73011` | **PATTERN / cross-check** | Official CNMV search + explicit interactive-page/CAPTCHA handling. Second discovery channel, not the canonical enumerator. |
| `plis2100/cnmv-rss` | **DISCARD for this gate** | CNMV records/notifications, not the Circular legal lifecycle; no root license declared. |
| PDMR/XBRL/funds/sanctions CNMV scrapers | **DISCARD here** | Acquisition lessons only; different document family. Arelle/PDF parsing would contaminate this probe. |

## Key architectural consequence

For Circulares, CNMV is the discovery layer and BOE remains the
primary legal evidence: CNMV circulars publish in BOE with BOE-ID,
ELI, PDF/EPUB/XML (e.g. `BOE-A-2020-14107` = Circular 2/2020). The
existing `boe_diario` parser keeps producing the canonical
`document.DiarioDoc` node stream; what PORT-CNMV-1/2 falsify is
whether the grammar/identity/adjudication *profile* ports — not the
document model.

## Corpus stress signal (official source)

The CNMV circulars page shows multi-target amendment chains already:
Circular 2/2025 modifies 1/2021, 1/2010, 5/2009; Circular 1/2025
modifies 6/2008, 11/2008, 4/2016; Circular 3/2021 modifies 4/2013,
5/2013. Comparable to the cases that stressed G2.
