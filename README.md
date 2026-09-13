# RegDelta (`regdelta-es`)

Ledger factual y auditable de cambios regulatorios financieros en España.
RegDelta no es un RAG, chatbot, buscador jurídico, MCP, frontend ni sistema de
interpretación legal. Representa qué norma cambió, qué bloque cambió, qué norma
lo produjo, cuándo, cuándo es aplicable, bajo qué condiciones y qué fuente
oficial demuestra cada hecho.

Estado actual: **G0-A (Live Observation) + G0-B (Immutable Evidence)**.
Fuera de alcance: G0-C/D/E/F, CNMV, EUR-Lex, MCP, LLM, frontend, embeddings,
vector DB, Parquet operativo, scheduler de producción.

## KNOWN LIMITATIONS

```text
1. BOE consolidated texts cover explicit amendments and explicit
   repeals. Tacit legal effects requiring interpretation are outside
   the deterministic scope of RegDelta.

2. Corrections and errata may alter legal text without behaving like
   ordinary consolidated amendment versions.

3. Historical backfill reconstructs legal valid-time but cannot
   reconstruct when RegDelta would historically have known a fact.

4. RegDelta provides factual provenance over official sources and
   does not constitute legal advice.
```

## Fuentes observadas (G0-A/B)

| Fuente | URL | Formato |
|---|---|---|
| Sumario diario BOE | `https://www.boe.es/datosabiertos/api/boe/sumario/{AAAAMMDD}` | XML (doc. oficial: `APIsumarioBOE.pdf`) |
| Consultas públicas BdE | `https://www.bde.es/wbe/es/punto-informacion/contenidos/consultas-publicas/` | HTML |

El filtro es **por departamento** (Banco de España, código BOE `1020`),
conservando sección y jerarquía originales; BdE publica en varias secciones
(I, III, 5B…). La API de legislación consolidada del BOE **no se consulta** en
G0-A/B. Nota de investigación registrada para G0-C: `BOE-A-2017-14334` y
`BOE-A-2025-26847` son publicaciones BOE oficiales (sumario) pero no fueron
recuperables en la colección de la API consolidada mediante las pruebas
realizadas; la existencia oficial nunca se infiere de la disponibilidad en una
colección derivada.

## Modelo de datos

```text
source_checks      cada comprobación HTTP real (checked_at UTC, status, http_status)
source_snapshots   contenido único observado por (fuente, URL): parse_status, source_date,
                   parser_name + parser_version (provenance del parser)
source_blobs       bytes content-addressed (SHA-256), inmutables, sin extensión
data/raw/sha256/ab/cd/<sha256>

boe_items + boe_item_placements            entidad oficial (BOE-A-*) + hechos por snapshot
bde_consultations + bde_snapshot_memberships entidad + hechos por snapshot
anomalies           anomalías explícitas (p.ej. duplicados dentro de un snapshot)
```

- Identidad BOE: identificador oficial (`BOE-A-2025-26847`).
- Identidad consulta BdE: `sha256("bde_consultation|" + title_normalized + "|" + published_on)`,
  con `title_normalized` = NFKC + casefold + colapso de espacios (los diacríticos
  se conservan; `false split > false merge`).
- Los atributos observables (títulos, fechas, URLs de PDF) viven en
  placements/memberships, no congelados en la entidad.
- `consultation_window_status` (OPEN/ENDED) es **derivado**, calculado sobre el
  último snapshot `COMPLETE` sin anomalías (por orden de comprobación), con
  fecha local `Europe/Madrid`. La desaparición del listado es un hecho distinto
  (`LISTING_REMOVED`, derivado), nunca `CONSULTATION_CLOSED`.
- Un snapshot con estructura inválida conserva raw y check, no genera hechos
  derivados ni puede provocar `LISTING_REMOVED`.
- Provenance del parser: cada snapshot almacena `parser_name` y `parser_version`
  (`boe_sumario/v1`, `bde_consultas/v1`). Un cambio que pueda alterar el
  resultado semántico del parser obliga a incrementar `parser_version`; así
  `mismos bytes + parser v1` no se confunde con `mismos bytes + parser v2`.
- Sin `change_events`: G0-A/B solo observa.

## Uso

```powershell
uv sync
uv run regdelta watch --date 2026-09-13 --data-dir data
uv run pytest
```

Códigos de salida: `0` OK; `2` anomalías (requiere inspección); `3` error de
fuente o estructura inválida. El watcher es idempotente: bytes idénticos no
producen nuevos blobs/snapshots/entidades; cada comprobación real sí deja su
`source_check`.

Orden de escritura: el fetch HTTP y el raw-store (`temp → fsync → rename`
content-addressed) ocurren **fuera** de la transacción SQLite; `BEGIN IMMEDIATE`
se abre después y cubre solo operaciones SQLite. Por tanto nunca hay un write
lock retenido durante I/O de red, nunca existe una referencia DB a un blob
inexistente, y un fallo SQLite puede dejar como máximo un raw blob huérfano
(inmutable, no referenciado y recuperable por GC futuro).

## Provenance y reutilización

Toda observación se resuelve hasta: URL oficial, `retrieved_at` real, SHA-256 y
raw content-addressed. El texto BOE procede del BOE; si se redistribuye texto
consolidado debe indicarse su carácter meramente informativo y conservarse los
metadatos de actualización exigibles por las condiciones de reutilización del
BOE. El HTML de consultas del BdE se almacena como evidencia con su fecha de
observación; no se redistribuye modificado.

## Ingeniería

Python ≥ 3.11. Dependencias runtime: ninguna (stdlib). Dev: `pytest`.
La zona `Europe/Madrid` se calcula con un conversor CET/CEST interno (Windows no
incluye base tz; se evita la dependencia `tzdata`). El User-Agent HTTP está
fijado empíricamente para compatibilidad con el gateway del BdE.
