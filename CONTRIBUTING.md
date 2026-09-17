# Contribuir a RegDelta

## Antes de cambiar código

Leer `AGENTS.md`. Los resultados históricos son permanentes: no corregir un
fallo nuevo editando informes, métricas, manifests, seals o baselines congelados.
Las decisiones ADOPT/PORT entran por la preregistración del siguiente gate.
Antes de un nuevo subsistema de parsing, identidad, amendments, versionado,
consolidación, diff o perfiles, revisar `evidence/oss-recon/` y su `RUBRIC.md`.

No abrir evidencia actualmente sellada durante desarrollo ordinario. Un hash
no es una apertura semántica ni concede autorización para evaluar. Los DEV
reutilizan evidencia G0-G/G1 ya abierta históricamente: comprobar destinos y
estado del corpus antes de ejecutarlos. Si la autorización de la sesión prohíbe
todos los `*/holdout/*`, tampoco ejecutar esos replays históricos.

## Entorno

Python 3.11 es la referencia; `pyproject.toml` declara ≥ 3.11. Runtime stdlib,
desarrollo mediante uv. `uv sync` puede descargar paquetes y modificar el
entorno; una `.venv` preexistente no demuestra reproducibilidad desde cero.
No se requieren claves de IA para usar ni probar RegDelta.

## Comandos y alcance

El runner y la configuración están incorporados. Sincronizar con `uv sync --locked`
y ejecutar los checks siguientes; los resultados locales registrados y sus
límites están en `AUDIT.md`.

```powershell
uv run python scripts/check.py
uv run ruff check
uv run mypy
uv build
```

| Comando | Contrato |
|---|---|
| `scripts/check.py` | Ejecutar todos los `tests/test_*.py` de primer nivel, sin recorrer suites de gates. No ejecutar capturas/evaluadores ni abrir holdout automáticamente. |
| `ruff check` | Reglas `E9,F63,F7,F82`, sobre `src`, `tests`, `scripts`; no equivale a revisión completa de estilo/seguridad. |
| `mypy` | Alcance incremental explícito: `src/regdelta/http.py`, `src/regdelta/rawstore.py`, `src/regdelta/util.py`. No declarar todo el repositorio tipado. |
| `uv build` | Construir wheel/sdist; después revisar inventario e instalación. No es aprobación de licencia ni de publicación. |

El runner evita mantener una lista larga de `--ignore=tests/g0c` hasta
`--ignore=tests/cov`. La selección positiva de archivos de primer nivel debe
seguir siendo su límite aunque aparezcan nuevos directorios de gates.
Si se añade un test de primer nivel, asegurar que tampoco acceda a evidencia
sellada indirectamente.

## Separación de pruebas

- **Unitarias/primer nivel:** fake fetch, HTTP simulado, parsers y SQLite/raw
  temporales. `tests/conftest.py:29–59` y `tests/test_http.py:35–41` muestran los
  mecanismos existentes. Es selección por ubicación, no sandbox de seguridad.
- **Replay público autorizado:** requiere capturas, manifests y a veces scripts
  importados desde el checkout. Verificar todos los destinos antes de ejecutar.
- **Integridad histórica:** puede requerir Git y commits antiguos; ZIP o clone
  shallow no sustituye ese entorno. Hashing y evaluación son actividades distintas.
- **Evaluación sellada:** solo mediante protocolo y autorización del gate;
  nunca como efecto colateral de la suite ordinaria o CI general.

`uv run pytest` recopila también gates. Hay tests que omiten corpus ausente y
otros que leen manifests durante colección. Los DEV de G1/G2 referencian raw
bajo holdouts históricos; véanse `scripts/g1/build_dev_manifest.py:31–50`,
`scripts/g2/build_dev_manifest.py:42–59` y
`tests/cov/test_cov2_subscope.py:30–55`. Por ello no se recomienda la suite
completa para una sesión con prohibición de holdout.

La ejecución local registrada pasó 584 tests tras revisión estática de seguridad:
reutilización DEV de G0-G/G1 ya abiertos, guardas de G2 hash-only y ninguna apertura
semántica del holdout actual G2/CNMV. No confundir esa revisión con una garantía
general para scripts standalone: varios aún usan globs amplios. El diff de
evidencia quedó vacío.

La CI (`.github/workflows/checks.yml:8–39`) usa actions fijadas por SHA, permisos
read-only y checkout sin credenciales persistidas. Su matriz Windows/Linux,
Python 3.11/3.13, ejecuta checks operativos/lint/tipos/build/inventario sin evidence
en el sparse checkout. No ejecuta gates ni ha sido verificada en hosting.

Después de `uv build`, ejecutar `uv run python scripts/check_distribution.py`.
La primera revisión rechazó `.gitignore` auto-incluido; se admitió ese archivo
seguro. La repetición final del inventario sigue pendiente en la tarea principal;
no confundir build exitoso con inventario aprobado. El wheel sí se instaló en
un venv temporal aislado y su CLI respondió desde fuera del checkout.

Los tests pueden escribir caches y datos temporales. Los replays deben usar
salidas temporales fuera de evidencia, con entradas solo lectura. Bloquear red
en trabajos offline; los mocks actuales no son una barrera de proceso general.
No regenerar evidencia para eliminar un skip o ajustar un resultado esperado.

## Revisión y entrega

- Distinguir bug reproducido, hallazgo estático e hipótesis; conservar evidencia
  del comando, entorno, salida y alcance realmente probado.
- Verificar no regresión con corpus autorizado y justificar cambios semánticos
  de parser/versiones según el gate. No convertir abstención en certeza sin prueba.
- Registrar skips y fallos, no solo un total de PASS. Un resultado histórico no
  valida el working tree actual ni tests aún sin seguimiento Git.
- No mezclar modificaciones locales ajenas ni commits sin autorización.
- No incluir secretos, entornos virtuales, DB operativa, caches ni outputs de
  build en una entrega. Revisar diferencias sin imprimir valores sensibles.

## Distribución bloqueada

Falta la decisión de licencia del propietario. Revisar también la licencia y
notices del upstream que `scripts/port-cnmv/scout_cnmv.py:1–5` identifica como
portado; `evidence/port-cnmv/OSS-RECON.md:6–13` no resuelve esa obligación.
No publicar paquetes antes de resolver derechos e inventariar sus contenidos,
especialmente la exclusión de holdouts. No reescribir evidencia para hacerlo.
