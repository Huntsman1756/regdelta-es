# Auditoría de ingeniería y seguimiento

Cierre documental: 2026-09-17. Base inicialmente observada: `cdd2079`, con
cambios locales y `.venv` preexistentes. Resultados verificados localmente.
No se hicieron commits. Este documento es un resumen de trabajo, no evidencia
de gate, nueva validación sellada ni certificación de release.

## Método, acceso a evidencia y límites

Inspección estática de código/config/docs y reportes públicos, seguida de la
suite completa local tras revisión estática de seguridad. **Sí hubo reutilización
semántica de evidencia G0-G/G1 ya abierta históricamente**, referenciada desde DEV.
El holdout G2 se accedió solo para hashes mediante guardas de sello; no hubo
apertura semántica del holdout actual G2 ni CNMV. El diff Git de evidencia quedó
vacío. No se reescriben manifests, sellos ni veredictos históricos.

No hubo escaneo exhaustivo de secretos en todo el historial ni verificación de
controles del hosting. Las referencias corresponden al código inspeccionado y
pueden desplazarse. Un hallazgo **STATIC** no es una regresión reproducida y un
PASS de tests no lo cierra automáticamente. La sospecha sobre `parents[2]` se
descartó: resuelve correctamente la raíz en los tests anidados inspeccionados.

## Gates y techo de afirmación

| Registro | Estado que debe conservarse |
|---|---|
| `AGENTS.md` | G0-G.2 = FAIL; G1.2 = FAIL; G2.0 = STOP; G2.0b = PASS; G2.2 = PASS. |
| `evidence/g2/g2.2/VERDICT.json:1–13` | Integridad acotada de ownership, locator y binding en el corpus fresco BdE evaluado, con abstención. |
| `evidence/g2/g2.2/report.md:12–37` | Cero falsas afirmaciones en categorías medidas; binding 24/286 y chains 3/45, con limitaciones/adquisición registradas. |
| `evidence/cov/cov2/FINAL.md:43–48,205–215` | COV-2_DEV PASS, 354 → 468 bindings CURRENT_OPERATIONAL; mejora DEV-only, NOT_READY_FOR_COV_3. |
| `evidence/cov/cov3-prospective/PREREG.md:1–15` | Protocolo preregistrado, ningún gate abierto ni autorización de captura/evaluación. |
| `evidence/port/PORT2-REPORT.md:3–17` | PORT-2 FAIL preservado, PORT-2R PASS, PROFILE_EXTRACTION_PROVEN. |
| `evidence/port-cnmv/PORT-CNMV-0R.md:125–161` | READY_FOR_ISOLATED_CNMV_PROFILE_PROBE; PORT-CNMV-1 requiere autorización. No soporte semántico CNMV validado. |

G2.2 y COV-2 usan contabilidad distinta de binding. No atribuir al runtime actual
validación nueva sobre holdout por pasar regresiones, reutilizar DEV o extraer
un perfil. No se declara cobertura jurídica general ni preparación para producción.

## Verificación local registrada

Entorno: **Windows, Python 3.11.15, uv 0.11.25**, usando `.venv` preexistente,
no una reconstrucción limpia de todo el entorno.

| Ejecución | Resultado y alcance |
|---|---|
| `uv lock` y `uv sync --locked` | PASS. |
| `uv run python scripts/check.py` | **281 passed**; selección de todos los `tests/test_*.py` de primer nivel, no sandbox. |
| `uv run pytest -q` | **584 passed en 288,64 s**, con los límites de acceso descritos arriba. |
| `uv run ruff check` | PASS; reglas críticas E9,F63,F7,F82 sobre src/tests/scripts. No lint exhaustivo de estilo/seguridad. |
| `uv run mypy` | PASS en tres módulos: `src/regdelta/http.py`, `rawstore.py`, `util.py`; tipado incremental, no de todo el código. |
| `uv build` | Wheel y sdist construidos correctamente. |
| Inventario de archivos | La comprobación inicial rechazó `.gitignore` auto-incluido; se añadió ese miembro seguro a la allowlist. `uv run python scripts/check_distribution.py`: **PASS** tras reconstruir; evidencia y configuración local excluidas. |
| Smoke de distribución | Wheel instalado con `uv pip install --python …` en venv temporal aislado; `python -I -m regdelta.cli --help` pasa desde fuera del checkout. No prueba cada operación del paquete. |
| `uvx pip-audit --path .venv/Lib/site-packages --progress-spinner off` | «No known vulnerabilities»; paquete local `regdelta` omitido. No auditoría del código propio ni de licencias. |
| Watcher | **71 passed**. La selección basal watcher+migration registró **27 failed, 65 passed**. |
| Aplicabilidad: integridad de carga | **6 tests sintéticos pasando** para verificación del hash del blob y manejo de `parse_error`. |
| Evidencia | Diff Git vacío; sin apertura semántica del holdout actual G2/CNMV. |

Los recuentos de selecciones parciales se solapan con la suite; no sumarlos.
Parte del hardening estaba heredado en el working tree y fue validado/corregido,
no todo fue escrito de nuevo por esta tarea. La comparación basal seleccionada
no debe presentarse como un baseline de toda la suite.

## Ingeniería implementada y límites restantes

- `scripts/check.py:9–15`: selección positiva de tests de primer nivel; no
  ejecuta automáticamente gates. Un test nuevo aún podría introducir efectos
  laterales: la selección no sustituye controles de acceso/red.
- `pyproject.toml:4–6,15–39`: descripción/readme actualizados, Hatchling fijado a
  1.27.0, selección explícita de sdist y configuración Ruff/mypy incremental.
  Versión alineada a `0.3.0a0` (PEP 440) frente al tag histórico
  `v0.3-alpha`; la política de correspondencia release/evidencia sigue
  por definir para releases formales futuras.
- `scripts/check_distribution.py:9–33`: inventario allowlist de wheel/sdist,
   rechazo de rutas inseguras y enlaces de sdist, `.gitignore` admitido.
   Inventario final verificado correctamente.
- `.github/workflows/checks.yml:8–39`: actions fijadas por SHA, permisos
  `contents: read`, checkout sin credenciales persistidas, sparse checkout sin
  evidencia; matriz Windows/Linux y Python 3.11/3.13 para checks operativos,
  lint/tipos/build/inventario. **No ejecutada/verificada en hosting**; no demuestra
  aún portabilidad Linux ni ejecuta replays de gates.
- `.gitignore:7–24`: ignora secretos habituales, configuración local, outputs y
  caches. `.gitattributes:1–4` fija Python LF en src/scripts/tests y fixtures
  binarios; evidencia no modificada. Ignore no elimina copias previas.
- `src/regdelta/applicability.py:114–132`: hash del blob verificado y manejo de
  `parse_error` corregido; seis tests sintéticos pasan. Esto no corrige la
  semántica de spans, continuaciones o scopes señalada abajo.
- README, CONTRIBUTING y SECURITY reflejan capacidades locales y techos de
  validación, sin declarar servidor web, UI, autenticación o deployment server.

## Bloqueos de seguridad y distribución

| Prioridad | Hallazgo / estado | Acción |
|---|---|---|
| Crítica | Claves locales plaintext saneadas a `{env:NAN_BUILDERS_API_KEY}` y `{env:OPENROUTER_API_KEY}`. No se confirmó fuga pública ni se hizo escaneo exhaustivo del historial. | Propietario debe rotar claves, tratar copias previas y reiniciar opencode; no verificado externamente. |
| Alta (resuelto) | La configuración de herramienta conservaba `permission: "allow"`; el watcher ignore no era control de acceso. | `opencode.json` fue eliminado del árbol de trabajo; ya no hay acceso irrestricto configurado. Si se recrea, restringir permisos/contexto frente a material privado/sellado. El runtime RegDelta no requiere esas claves. |
| Bloqueo de release (resuelto) | Sin licencia de proyecto en el momento de la inspección. | El propietario eligió **Apache-2.0** (ver `LICENSE`, `pyproject.toml`). Quedan pendientes los derechos de las fuentes oficiales. |
| Bloqueo de release (resuelto) | Port de esdata identificado en `scripts/port-cnmv/scout_cnmv.py:1–5,31`; `evidence/port-cnmv/OSS-RECON.md:6–13` no resolvía licencia/notices de ese upstream. | **A10 cerrado como PASS (2026-09-17, decisión del propietario):** el flujo `_discover_cnmv_circulares` entró en `esdata` con `80b9eb0` (el padre `0a50f13` aún tenía el crawler anterior); la búsqueda del identificador distintivo solo devuelve repos del propietario y este port; sin coautoría externa declarada. `origin = owner-controlled code`, `third-party provenance found = NO`, `additional attribution required = NO`. Due diligence razonable, no prueba jurídica absoluta. |
| Verificación abierta | Inventario final de wheel/sdist confirmado; build y smoke exitosos no sustituyen la decisión de licencia. | 

## Runtime: hallazgos STATIC sin resolver

Seguimiento del auditor de runtime, **no regresiones semánticas reproducidas ni
fallos nuevos demostrados por los tests actuales**. No se introdujeron cambios
semánticos para resolverlos bajo gates congelados. Reproducir con documentos
sintéticos/evidencia autorizada y admitir cambios por el gate correspondiente.

| ID | Riesgo estático | Punto de seguimiento |
|---|---|---|
| R01 | Span de nodos incorrecto para una frase de aplicabilidad. | `src/regdelta/applicability_parser.py:326–377`, `extract_clauses`: comprobar correspondencia frase/nodo, no solo texto emitido. |
| R02 | Continuaciones de aplicabilidad pueden atravesar límites de sección. | `src/regdelta/applicability_parser.py:395`, `assign_parents`: verificar cierre de contexto en cambio de sección. |
| R03 | Identidad de relación omite el target; posible colisión entre destinos. | `src/regdelta/history.py:74`, `modification_relation_id`: probar mismo modifier/locator para distintos targets. |
| R04 | Evidencia de ownership conflictiva puede acabar resuelta. | `src/regdelta/ownership.py:174`, `attribute_operation`: exigir ambigüedad/abstención ante señales incompatibles. |
| R05 | `upcoming` puede mezclar scope de frecuencia y de efectos. | `src/regdelta/query.py:396`, `upcoming`, y `src/regdelta/applicability_parser.py:514`, `frequency_table`. |
| R06 | Metadata placeholder y selección de snapshot obsoleto pueden propagarse. | `src/regdelta/history.py:298`, `_upsert_instrument`, y `src/regdelta/applicability.py:93`, `_diario_snapshot`. |
| R07 | Reconstrucción histórica puede hacer red mientras hay escrituras SQL pendientes. | `src/regdelta/history.py:124,821`, `_Ctx.get` / `reconstruct`. La separación HTTP/transacción del watcher no prueba la de history. |
| R08 | Fechas de publicación ausentes en modifiers afectan orden de reconstrucción. | `src/regdelta/history.py:926`: comprobar orden/abstención antes de encadenar. |
| R09 | En sección sin encabezado puede omitirse el primer nodo. | `src/regdelta/operations.py:895,1103`, `split_sections` / `_parse_section`. |
| R10 | Globs amplios en scripts standalone pueden leer holdout fuera del protocolo pretendido. | `scripts/g1/build_dev_manifest.py:31–50`, `scripts/g2/build_dev_manifest.py:42–59` y búsquedas de evidencia. La revisión de la suite no autoriza todos los scripts. |
| R11 | Provenance de runner puede nombrar HEAD aunque ejecute código local dirty. | `scripts/g0g/evaluate_sealed.py:250–265,297–305`: distinguir árbol ejecutado del commit declarado; no certificar equivalencia solo con HEAD. |

## Otros hallazgos estáticos abiertos

- **Aislamiento por paths:** manifests DEV de G1/G2 apuntan a holdouts históricos
  (`evidence/g1/dev/manifest.json:2909`, `evidence/g2/dev/manifest.json:457`;
  lectura en `tests/cov/test_cov2_subscope.py:42–55`). Reutilizar corpus ya abierto
  no demuestra contaminación actual, pero incumpliría una prohibición de todos
  los directorios holdout. Resolver/validar destinos; una futura vista pública
  autorizada debe conservar provenance sin reescribir evidencia histórica.
- **Guardas incompletas:** retornos/skips por sello/corpus ausente en
  `tests/g2/test_g2_holdout_sealed.py:41–44` y
  `tests/g1/test_g1_holdout_sealed.py:39–43`; distinguir corpus opcional de estado
  SEALED/PASS incompleto. El chequeo de tokens de
  `tests/g0g/test_holdout_sealed.py:67–88` no es control de acceso indirecto.
- **Replay POSIX:** paths con backslash combinados directamente con ROOT
  (`tests/cov/test_cov2_subscope.py:47–49`) requieren resolución portable.
  La suite Windows y la futura CI operativa sin evidencia no prueban replay Linux.
- **Recursos/tiempo:** PDF limitado y descompresión/recorrido pendientes de revisión
  (`src/regdelta/sources/boe_pdf.py:68–98`); DST moderno aplicado a todo año
  (`src/regdelta/util.py:69–74`). No son hallazgos de explotación demostrada.
- **Durabilidad:** hashes, fsync y reemplazo del raw-store
  (`src/regdelta/rawstore.py:21–41`) no son WORM ni garantía universal frente a
  corte de energía. Pendientes pruebas de backup/recuperación coherente DB/raw.

## Prerrequisitos de la suite completa

Python/pytest, Git con objetos históricos, capturas XML/HTML/PDF/imágenes,
manifests/gold/reportes y scripts del checkout. ZIP o clone shallow no sustituye
el entorno requerido por `tests/g2/test_g2_holdout_sealed.py:82–100`. Algunos
módulos omiten corpus ausente y otros leen manifests durante colección.

Hay escrituras de caches y SQLite/raw/output temporales, y subprocesos Python
(`tests/g0g/test_sealed_runner.py:37–49,112–139`). Los tests inspeccionados usan
fetch simulado/capturado; no se identificó red viva intencional, pero los mocks
locales y comprobaciones de imports no son una barrera de red general. No se
identificaron requisitos de OCR/Poppler/navegador/Docker ni servicio web externo.

Orden de seguimiento: rotación externa y licencias; confirmar inventario y CI
alojada; reproducir hallazgos STATIC con datos autorizados; planificar correcciones
semánticas mediante nuevos gates. Ninguno de esos pasos autoriza reabrir el
holdout actual ni alterar los resultados históricos.
