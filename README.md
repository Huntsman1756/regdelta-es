# RegDelta (`regdelta-es`)

Prototipo experimental de ledger factual y auditable de cambios regulatorios,
centrado en fuentes del Banco de España (BdE) y del BOE. Registra hechos con
provenance y se abstiene cuando la evidencia no permite probarlos. No es un
RAG, chatbot, buscador jurídico ni sistema de interpretación legal.

Python 3.11 como referencia; el paquete declara Python ≥ 3.11 y usa únicamente
la biblioteca estándar en runtime. Es una biblioteca/CLI local con SQLite y
archivos raw: no incluye backend web, UI, autenticación de usuarios ni servidor
de despliegue. No se declara preparado para producción.

## Estado y límites de las afirmaciones

El código incluye observación HTTP, almacenamiento content-addressed,
reconstrucción estructural experimental de modificaciones, aplicabilidad,
consultas y diffs. Que una capacidad exista no implica cobertura jurídica
completa ni validación sobre cualquier emisor.

| Gate | Resultado registrado y alcance |
|---|---|
| G0-G.2 / G1.2 | **FAIL / FAIL**, historia permanente. |
| G2.0 / G2.0b | **STOP / PASS**; la enmienda no sustituye el STOP original. |
| G2.2 | **PASS**: integridad factual acotada en el corpus BdE fresco evaluado, con abstención y cobertura medida. |
| COV-2 | **COV-2_DEV = PASS**: mejoras de binding validadas en DEV, no generalización externa de esas mejoras. |
| COV-3 | **NOT_READY_FOR_COV_3** retrospectivo. El protocolo prospectivo está preregistrado, sin gate abierto. |
| PORT-2 / PORT-2R | **FAIL / PASS**; resultado global **PROFILE_EXTRACTION_PROVEN**, no portabilidad semántica general. |
| PORT-CNMV-0R | **READY_FOR_ISOLATED_CNMV_PROFILE_PROBE**: corpus/split preparado. PORT-CNMV-1 requiere autorización explícita; no se afirma soporte semántico CNMV validado. |

G2.2 registró cero falsos hechos/bindings/atribuciones/declaraciones de locator,
pero representation binding fue **24/286 (8,39%)** y chain reconstruction
**3/45 (6,67%)**. COV-2 elevó las afirmaciones positivas de binding
CURRENT_OPERATIONAL de **354 a 468**, exclusivamente en DEV. Son métricas con
contabilidad distinta: no deben compararse como si fueran el mismo porcentaje.

Fuentes: `evidence/g2/g2.2/VERDICT.json:1–13`,
`evidence/g2/g2.2/report.md:21–37`, `evidence/cov/cov2/FINAL.md:205–215`,
`evidence/cov/cov3-prospective/PREREG.md:1–15`,
`evidence/port/PORT2-REPORT.md:3–17` y
`evidence/port-cnmv/PORT-CNMV-0R.md:156–161`.
Estos resultados corresponden a estados congelados, no certifican cambios
locales posteriores. Véase [AUDIT.md](AUDIT.md) para resultados locales, hallazgos estáticos abiertos y bloqueos de distribución.

## Limitaciones conocidas

- Los efectos tácitos que requieren interpretación quedan fuera del alcance
  determinista; no es un motor completo de consolidación ni asesoramiento legal.
- Correcciones y erratas pueden cambiar texto sin comportarse como versiones
  consolidadas ordinarias.
- El backfill reconstruye tiempo jurídico, no cuándo RegDelta habría conocido
  históricamente un hecho. Importar evidencia no es una comprobación HTTP nueva.
- PDF/imagen no equivale a texto jurídico extraído y probado. El extractor PDF
  interno usa una capa textual limitada para localizar páginas; no hace OCR.
- El conversor CET/CEST interno aplica reglas modernas: no es una base completa
  de historia de la zona `Europe/Madrid`.
- EUR-Lex, MCP, LLM en runtime, embeddings, vector DB, Parquet operativo y
  scheduler de producción no forman parte del producto actual.

## Fuentes observadas por `watch` (G0-A/B)

| Fuente | URL | Formato |
|---|---|---|
| Sumario diario BOE | `https://www.boe.es/datosabiertos/api/boe/sumario/{AAAAMMDD}` | XML |
| Consultas públicas BdE | `https://www.bde.es/wbe/es/punto-informacion/contenidos/consultas-publicas/` | HTML |

El filtro es **por departamento** (Banco de España, código BOE `1020`),
conservando sección y jerarquía originales; BdE publica en varias secciones
(I, III, 5B…). El watcher no consulta la API consolidada. Las pruebas históricas
no recuperaron `BOE-A-2017-14334` y `BOE-A-2025-26847` en esa colección derivada;
su publicación oficial nunca se infiere de su disponibilidad en ella.

## Modelo de observación

```text
source_checks      comprobaciones HTTP reales: checked_at UTC, status, http_status
source_snapshots   contenido observado: parse_status, source_date, parser y versión
source_blobs       bytes content-addressed SHA-256, sin extensión
data/raw/sha256/ab/cd/<sha256>

boe_items + boe_item_placements               identidad BOE + hechos por snapshot
bde_consultations + bde_snapshot_memberships  identidad consulta + hechos por snapshot
anomalies                                    anomalías explícitas
```

- Identidad BOE: identificador oficial (`BOE-A-*`).
- Identidad consulta: `sha256("bde_consultation|" + title_normalized + "|" + published_on)`.
  Normalización NFKC + casefold + espacios colapsados, conservando diacríticos;
  `false split > false merge`.
- Atributos observables viven en placements/memberships, no congelados en la entidad.
- `consultation_window_status` (OPEN/ENDED) se deriva del último snapshot
  `COMPLETE` sin anomalías, por orden de comprobación y fecha local de Madrid.
  Desaparecer del listado significa `LISTING_REMOVED`, no `CONSULTATION_CLOSED`.
- Una estructura inválida conserva raw/check, pero no produce esos hechos derivados.
- Un cambio semántico de parser exige versionado: mismos bytes con parsers
  diferentes no son la misma interpretación.
- Este esquema resume G0-A/B. La reconstrucción añade instrumentos, subjects,
  representaciones, relaciones y pruebas; `watch` por sí solo no puebla ese ledger.

## Uso local

Requiere Python y uv. La sincronización puede descargar dependencias de desarrollo
y herramientas de build; no necesita credenciales de proveedores de IA.

```powershell
uv sync
uv run regdelta --help
uv run regdelta watch --date 2026-09-13 --data-dir data
```

`watch` hace solicitudes reales a BOE/BdE y escribe SQLite/raw bajo `data`.
Códigos del watcher: `0` OK, `2` anomalías, `3` error de fuente/estructura.
Bytes idénticos no crean nuevos blobs/snapshots/entidades; cada comprobación
real sí deja un `source_check`.

La CLI también expone `changes`, `affects`, `upcoming`, `as-of` y `diff`
(`src/regdelta/cli.py:37–74`). Consultan un ledger previamente reconstruido;
no descargan ni reconstruyen automáticamente el historial. La preparación de
ese ledger usa biblioteca/scripts de investigación y necesita un corpus
expresamente autorizado. No ejecutar capturas ni evaluadores históricos como
paso de instalación.

El watcher prepara HTTP/raw fuera de la transacción SQLite. El raw-store usa
archivo temporal, `fsync` y reemplazo por dirección de contenido. «Inmutable»
describe el contrato de la aplicación, no protección WORM ni inmunidad frente
a modificaciones externas o pérdida de energía. Respaldar DB y blobs juntos.

## Verificación de desarrollo

Comandos operativos del checkout:

```powershell
uv run python scripts/check.py
uv run ruff check
uv run mypy
uv build
```

- `check.py`: todos los `tests/test_*.py` de primer nivel, sin suites de gates
  ni apertura automática de holdout. Es selección de tests, no sandbox.
- Ruff: `E9,F63,F7,F82` sobre `src`, `tests` y `scripts`.
- mypy incremental: solo `src/regdelta/http.py`, `rawstore.py` y `util.py`,
  no todo el proyecto.
- Build: wheel/sdist con selección explícita; comprobar inventario mediante
  `uv run python scripts/check_distribution.py`. Construir no autoriza distribuir.

Resultados locales comunicados por la tarea principal: **281 tests de primer
nivel** y **584 tests de la suite completa (288,64 s)** pasando; Ruff y mypy
(tres módulos) pasan. Windows, Python 3.11.15, uv 0.11.25, `.venv` preexistente.
Wheel/sdist construidos y smoke test del wheel instalado en venv temporal
fuera del checkout pasando. El inventario final de archivos requiere aún la
repetición principal tras admitir `.gitignore` como miembro seguro del sdist.

La suite completa se ejecutó tras revisión estática: reutilizó evidencia G0-G/G1
ya abierta históricamente en DEV; G2 holdout fue hash-only mediante guardas de
sello. No hubo apertura semántica del holdout actual G2/CNMV y el diff de
evidencia quedó vacío. No es una alternativa segura sin revisión si una sesión
prohíbe todos los holdouts. [CONTRIBUTING.md](CONTRIBUTING.md) detalla la separación.

La CI incorporada (`.github/workflows/checks.yml`) configura Windows/Linux con
Python 3.11/3.13, checks operativos, lint, tipos, build e inventario, excluyendo
evidencia del sparse checkout. No se ha verificado su ejecución alojada.

## Provenance, licencia y seguridad

Las observaciones conservan URL oficial, fecha real de recuperación, SHA-256 y
raw. Para redistribuir texto BOE consolidado hay que revisar las condiciones de
reutilización, indicar su carácter informativo y conservar metadatos exigibles.
El HTML BdE se conserva como evidencia de observación; esto no concede una
licencia general de redistribución.

El código del proyecto se distribuye bajo la licencia Apache-2.0
([LICENSE](LICENSE)).
Esa licencia no cubre los derechos de las fuentes oficiales observadas.

El runtime no depende de `opencode.json`. El archivo local que contenía claves
fue saneado y después eliminado; la rotación de `NAN_BUILDERS_API_KEY` y
`OPENROUTER_API_KEY` sigue siendo una acción externa pendiente. Véase
[SECURITY.md](SECURITY.md).
