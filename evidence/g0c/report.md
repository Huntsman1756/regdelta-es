# G0-C — Historical Reconstruction Discovery

- **Fase**: G0-C Discovery (solo discovery; sin pipeline definitivo)
- **HEAD base**: `fb0dc676dd4ca8e17c211a12f5507cc526588e14`
- **Fecha de captura**: 2026-09-13 (UTC), red real contra `boe.es` y `bde.es`
- **Alcance**: exclusivamente `BOE-A-2017-14334` (Circular 4/2017) como target y sus
  modificadores; `BOE-A-2025-26847` (Circular 1/2025) como caso secundario.
- **Nada de producto**: no se ha tocado `src/regdelta/`, ni el esquema SQLite, ni
  G0-A/B. Todo el trabajo vive en `evidence/g0c/`, `scripts/g0c/`, `tests/g0c/`.

## 0. Resumen ejecutivo

La pregunta de la fase era si el historial de modificaciones de la Circular 4/2017
puede reconstruirse de forma determinista, reproducible y auditable **aunque la
norma no esté en la colección de la API de legislación consolidada del BOE**.

Resultado: **PARTIAL**.

- El discovery de modificadores **sí** es determinista y oficial: el XML de la
  publicación diaria (`diario_boe/xml.php`) incluye un bloque `<analisis>` con
  `<referencias><posteriores>`. Se encontraron **7 modificaciones + 1 corrección de
  errores**, cada una con identificador oficial, palabra de relación y cross-check
  simétrico en la propia norma modificadora. Es el hallazgo principal de G0-C y
  matiza la premisa de que "no hay API": el canal consolidado
  `datosabiertos/api/legislacion-consolidada` está **ausente para el target** y para
  la mayoría de sus modificadores (404), pero **presente para un subconjunto**
  (`BOE-A-2020-6187`, `BOE-A-2020-15602`, con `estado_consolidacion=3`). El canal
  **`diario_boe/xml.php?id=...` sí devuelve XML estructurado oficial** para el target
  e incluye el análisis jurídico actualizado.
- Para **texto de normas y disposiciones**, `old_text` (publicación original) y
  `new_text` (norma modificadora) están **ambos disponibles como texto estructurado**
  y la reconstrucción `old → new` es PROVEN en los casos 1, 3, 4 y 6.
- Para **anejos y estados financieros**, el texto original en la publicación oficial
  **solo existe como imágenes** (326 `<img>` y únicamente 3 tablas en todo el XML de
  4/2017). Por tanto `old_text` de un anejo/estado **no es reconstruible** de forma
  textual desde fuentes oficiales BOE. `new_text` sí es estructurado en las normas
  modificadoras modernas. Esto impide declarar GO.
- Las **correcciones/erratas** son discoverables, traen `old` y `new` literales
  (`donde dice … debe decir …`) y deben tratarse como una clase aparte.

Veredicto: **PARTIAL** (artículos/normas/disposiciones = PROVEN; anexos/estados =
NOT_PROVEN para old_text). No es FAIL porque una parte material y toda la cadena de
discovery/ordenación queda demostrada.

---

## 1. Fuentes oficiales inspeccionadas

| Canal | URL | Formato | Uso |
|---|---|---|---|
| A — Publicación original | `https://www.boe.es/buscar/doc.php?id=BOE-A-2017-14334` | HTML | texto original + imágenes de anejos |
| A — Publicación diaria XML | `https://www.boe.es/diario_boe/xml.php?id=BOE-A-2017-14334` | XML | **texto estructurado + `<analisis>`** |
| A — Publicación diaria HTML | `https://www.boe.es/diario_boe/txt.php?id=BOE-A-2017-14334` | HTML | texto original |
| A — PDF oficial | `https://www.boe.es/boe/dias/2017/12/06/pdfs/BOE-A-2017-14334.pdf` | PDF (~39 MB) | copia visual; no usado para texto |
| B — ELI | `https://www.boe.es/eli/es/cir/2017/11/27/4` | HTML | navegación; mismo original que A |
| B — ELI `dof/spa/xml` | `https://www.boe.es/eli/es/cir/2017/11/27/4/dof/spa/xml` | XML | **idéntico byte a A XML** |
| B — ELI corrigendum | `https://www.boe.es/eli/es/cir/2017/11/27/4/corrigendum/20180215/dof` | HTML | corrección de errores |
| C — doc.php DOM | (mismo que A HTML) | HTML | 326 `img` / 3 `table`; sin texto de anejos |
| D — Modificadores | `https://www.boe.es/diario_boe/xml.php?id=<modificador>` | XML | `new_text` + locators |
| E — API consolidada | `https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/<id>/{metadatos,analisis,texto/indice}` | XML | **404 para el target**; 200 para un subconjunto (2020-6187/15602) |
| F — BdE índice | `https://www.bde.es/wbe/es/areas-actuacion/normativa/circulares-banco-de-espana/circulares-banco-espana-indice-cronologico/` | HTML | discovery complementario |
| F — BdE CLF | `https://app.bde.es/clf_www/leyes.jsp?...id=163651...` | JSP/HTML | consolidado actual (adaptado), **no autoridad** |
| F — BdE "a una Fecha" | `https://app.bde.es/clf_www/leyes.jsp?id=163651&fc=01-01-2018&tipoEnt=0` | JSP/HTML | **no fiable** (ver §8/§10) |

Comprobaciones de disponibilidad consolidada (evidencia negativa):

```
404  .../legislacion-consolidada/id/BOE-A-2017-14334/{metadatos,analisis,texto/indice}
404  .../legislacion-consolidada/id/BOE-A-2025-26847/{metadatos,analisis,texto/indice}
404  .../legislacion-consolidada/id/BOE-A-2023-5481/{metadatos,analisis,texto/indice}
404  .../legislacion-consolidada/id/BOE-A-2004-21845 (Circular 4/2004, misma familia)
200  .../legislacion-consolidada/id/BOE-A-2015-11430/metadatos   (control: API operativa)
200  .../legislacion-consolidada/id/BOE-A-1978-31229/metadatos   (control: API operativa)
200  .../legislacion-consolidada/id/BOE-A-2020-6187/{metadatos,analisis,texto/indice}
200  .../legislacion-consolidada/id/BOE-A-2020-15602/{metadatos,analisis,texto/indice}
200  https://www.boe.es/buscar/act.php?id=BOE-A-2020-6187   (HTML consolidada real)
404  https://www.boe.es/eli/es/cir/2017/11/27/4/consolidado     (no hay versión consolidada ELI)
302  /buscar/act.php?id=BOE-A-2017-14334 -> /buscar/doc.php?... (no hay "act" consolidado para el target)
```

`estado_consolidacion` en los raws capturados: `codigo="0"` para el target y para
la mayoría de los modificadores; `codigo="3" ("Finalizado")` para
`BOE-A-2020-6187` y `BOE-A-2020-15602`, que **sí** están en la colección
consolidada. Es decir, el 404 no es un fallo genérico del canal: la colección
consolidada simplemente **no incluye el target**, que es precisamente el problema
de G0-C.

---

## 2. Raws + SHA-256

Manifiesto completo: `evidence/g0c/raw/manifest.json`. Todos los bytes están
almacenados bajo `evidence/g0c/raw/` y verificados por test
(`tests/g0c/test_probe_evidence.py`). SHA-256 (primeros y últimos capturados):

| Raw | HTTP | bytes | SHA-256 |
|---|---|---|---|
| `boe_diario_xml__BOE-A-2017-14334` | 200 | 1379715 | `4f995cd7d647216658ec9a1cfe5b0096b25281b3efbc11f35aff9faa8dce38b2` |
| `boe_eli_dof_spa_xml__C4-2017` | 200 | 1379715 | `4f995cd7d647216658ec9a1cfe5b0096b25281b3efbc11f35aff9faa8dce38b2` |
| `boe_doc_html__BOE-A-2017-14334` | 200 | 1227821 | `8b0c269100e2e0ce93a47e605b376199fdd4c73b5c39ec50d12551e118eee194` |
| `boe_diario_txt_html__BOE-A-2017-14334` | 200 | 1228097 | `347160491a71b7f0c46b07db507be81099d1a73327b3010e4677d6a14721188e` |
| `boe_eli_html__C4-2017` | 200 | 1227765 | `9f5f2c1ad874471caa3b32a8f9a4258ee0a4a3a708629baa4fe61daeb3834ee6` |
| `boe_eli_corrigendum_html__C4-2017` | 200 | 36251 | `f2c2456483cf35f9b4a8708aa8dbd73841d4e5499ff20de75bc2a44b958f02aa` |
| `boe_dias_pdf__BOE-A-2017-14334` | 200 | 39355759 | `0923cc0a16241a23e7d4237443d29fdf14a8dce37818c4c00278ab00b14bf16e` |
| `boe_diario_xml__BOE-A-2018-2041` (corrección) | 200 | 16433 | `5c223ae4d24c4408c3468f3cd87fc93a942e038686f9bdf03fa2678a44fb7696` |
| `boe_diario_xml__BOE-A-2018-17880` | 200 | 201591 | `349d4cf294843190096bf8ebe5c945d7a0b7b3d299f2a4440e7082d087ea8ff5` |
| `boe_diario_xml__BOE-A-2020-6186` | 200 | 72226 | `d18d50d1e275f4a5952bb734b79e1650ab634b5ab6be776b11b3386c5f8a6de8` |
| `boe_diario_xml__BOE-A-2020-6187` | 200 | 45617 | `e66bed6b8c86e1da1cd209a3bbd55512715143d4bb8df7523435399be8ab04cd` |
| `boe_diario_xml__BOE-A-2020-15602` | 200 | 130330 | `eee7da6beae37c597d2bcbfc2d1cf4e0b97d8a622ac9ebd7b0a65dafd7364936` |
| `boe_diario_xml__BOE-A-2021-21666` | 200 | 115950 | `8c18efe7c4bf1634f3d00e223a850daaabdd7c2a72f713fb9b61b96a860cd48a` |
| `boe_diario_xml__BOE-A-2023-5481` | 200 | 253268 | `896e73c3c4bd6f4bdc4c5eea4375383ee7acb26c8e269d4e4bdd24c144a931a7` |
| `boe_diario_xml__BOE-A-2025-26847` | 200 | 234162 | `689fbe5e47569045d3bbd99738cae8a4c31583d733ade0e454ed4eb08ca9aa91` |
| `boe_doc_html__BOE-A-2025-26847` | 200 | 250871 | `fa679f84a2817fe0573e5eb6096b5020f05f5d16acebf42e9751255900ae55fa` |
| `boe_eli_html__C1-2025` | 200 | 250835 | `54828de6e94f9225293e3e929adfa35fb255ce4063426d992cd160bae6b8a1fa` |
| `boe_api_consolidada_*__2017/2023/2025` (9 raws) | 404 | 170 | `af8a60024ae378ae0f96e823639c937abe9f147b4446f362d95211ad85dc2bc6` |
| `boe_api_consolidada_metadatos__BOE-A-2020-6187` | 200 | 1391 | `a8827072024bf597…` |
| `boe_api_consolidada_analisis__BOE-A-2020-6187` | 200 | 1250 | `e4637553afb0ac3b…` |
| `boe_api_consolidada_texto_indice__BOE-A-2020-6187` | 200 | 1708 | `c1ed6d7c9607f1af…` |
| `boe_api_consolidada_*__BOE-A-2020-15602` (3 raws) | 200 | 1640/2191/9347 | `09e61d8d…` / `dc553508…` / `7ba4153a…` |
| `boe_buscar_act_html__BOE-A-2020-6187` | 200 | 69518 | `f8e4144cd254ddfd…` |
| `bde_clf_leyes_art__163763` | 200 | 18426 | `51b4cc13ab7fd47d74d430464e575ffb97baddc5ee3617c0d9c49be07ace8a1b` |
| `bde_clf_norma_a_fecha__163651__2018-01-01` | 200 | 1601950 | `fad0dd18ef7838293a113fc3745aa122a452a4cb2037f6cd890d96bf41a5eebe` |
| `bde_clf_art_prev__163763__2025-12-29` | 200 | 13809 | `52f92341b4b035ff17b0d26951eadd50dc51fc35ab88802501cd533935a5f485` |
| `bde_indice_cronologico_circulares` | 200 | 466966 | `5ec993cd256ffb09f44af6ff66a2b93efe2369ab7ad5950f61ecb368526cec36` |
| `bde_info_banco_espana_c4_2017` | 200 | 377483 | `0710fa789e236867dfe1a21a384d7c45dbde50ffe3e9910f3308d8c092db6fc2` |

Igualdades medidas:

```text
eli_dof_spa_xml  == diario_xml (target)      -> True
eli_dof_html     == eli_html                 -> True
eli_html         == doc_html                 -> False (solo difiere el chrome de plantilla)
doc_html         == diario_txt_html          -> False (solo difiere el chrome de plantilla)
```

Conclusión: **ELI no aporta una representación distinta**; expone el mismo original
y no ofrece versión consolidada.

---

## 3. Lista reproducible de modificadores encontrados

Generada por `scripts/g0c/probe_relations.py` → `evidence/g0c/modifiers.json`.
Fuente: `<analisis><referencias><posteriores>` del target, con cross-check en el
`<anteriores>` de cada modificador.

| Fecha pub. | Fecha vigencia | Instrumento | Relación (`<palabra>`) | Locators | Cross-check |
|---|---|---|---|---|---|
| 2018-02-15 | — | `BOE-A-2018-2041` | CORRECCIÓN de errores | 2 | sí |
| 2018-12-28 | 2019-01-01 | `BOE-A-2018-17880` | SE MODIFICA | 38 | sí |
| 2020-06-16 | 2020-06-17 | `BOE-A-2020-6186` | SE MODIFICA | 42 | sí |
| 2020-06-16 | 2020-06-17 | `BOE-A-2020-6187` | SE MODIFICA | 1 | sí |
| 2020-12-04 | 2021-01-01 | `BOE-A-2020-15602` | SE MODIFICA | 7 | sí |
| 2021-12-29 | 2021-12-30 | `BOE-A-2021-21666` | SE MODIFICA | 3 | sí |
| 2023-03-02 | 2023-03-31 | `BOE-A-2023-5481` | SE MODIFICA | 5 | sí |
| 2025-12-29 | 2025-12-30 | `BOE-A-2025-26847` | SE MODIFICA | 11 | sí |

También se registra una relación *anterior*: `BOE-A-2004-21845` (Circular 4/2004),
`<palabra codigo="210">DEROGA</palabra>`.

**Exhaustividad (OBSERVED + límite explícito)**: el canal enumera *todas las
relaciones explícitas que el BOE registra* para el instrumento. No puede demostrarse
de forma independiente que sea exhaustivo sin recorrer todas las normas posteriores
(no se ha hecho y no se declara). Efectos tácitos quedan fuera por diseño. Por eso
no se usa la palabra "todas" sin matiz: se dice "todas las registradas por el
análisis oficial".

---

## 4. Matriz comparativa de canales

Generada por `scripts/g0c/probe_matrix.py` → `evidence/g0c/channel-matrix.json`.
Criterios declarados explícitamente en `criteria` (coverage, determinism,
granularity, raw_evidence, reconstruction_difficulty, fragility, licensing).

| Canal | Coverage | Determinism | Granularity | Raw | Fragility |
|---|---|---|---|---|---|
| A2 `diario_boe/xml.php` | texto original + `<analisis>` + RDF ELI; sin consolidado; anejos = imágenes | HIGH | PROVISION (vía modificador) | FULL | LOW |
| A1/C `doc.php` / `txt.php` | texto original; anejos = imágenes | HIGH | TEXT_ONLY | FULL | LOW |
| A4 PDF | visual, incl. anejos | HIGH | NONE sin extracción | FULL (~39 MB) | LOW |
| B ELI | mismo original; sin consolidado | HIGH | INSTRUMENT / = A2 en `/xml` | FULL | LOW |
| D modificadores | `new_text` + locators por precepto | HIGH | PROVISION/BLOCK | FULL | LOW |
| E1 API consolidada (target) | **NONE** para el target (404) | fallo explícito | N/A | 404 almacenado | N/A |
| E1b API consolidada (subconjunto) | presente solo en 2020-6187 / 2020-15602 | HIGH | bloques + relaciones `<id_norma>` | FULL | LOW |
| E2 `<analisis>` | 7 modif. + 1 corrección + anteriores | HIGH | INSTRUMENT + texto descriptivo | FULL | LOW* |
| F1 BdE índice | discovery complementario | MEDIUM | INSTRUMENT | FULL | MEDIUM |
| F2 BdE CLF | consolidado actual adaptado | **LOW** (respuestas inconsistentes) | artículo/anejo | HTML inestable | HIGH |
| F3 BdE "a una Fecha" | **no usable** | **UNRELIABLE** | N/A | inestable | HIGH |
| G correcciones | old+new literales | HIGH | PROVISION | FULL | LOW |

`*` el bloque `<analisis>` se regenera dinámicamente (`fecha_actualizacion`), por lo
que el raw debe hashearse en cada captura para fechar la observación.

---

## 5. Casos experimentales

Generados por `scripts/g0c/probe_cases.py` → `evidence/g0c/cases.json`.
`confidence` procede de una regla estructural de disponibilidad de fuentes, no de un LLM.

| # | Caso | Modificador | Locator | old | new | Confianza |
|---|---|---|---|---|---|---|
| 1 | Sustitución de norma | `BOE-A-2018-17880` | Norma 33 | 13103 B, `7efffb88…` | 38091 B, `50f56578…` | PROVEN |
| 2 | 1ª modificación de anejo (texto) | `BOE-A-2020-15602` | Anejo 9, punto 46 | **no disponible** | 941 B, `4d3036cf…` | PARTIAL |
| 3 | 2ª modificación de bloque ya modificado | `BOE-A-2020-6187` | Anejo 9, punto 99 | 1776 B, `102403a2…` | 917 B, `f400257a…` | PROVEN |
| 4 | Modificación de Circular 1/2025 | `BOE-A-2025-26847` | Norma 19, apartado 10 | 1343 B, `73d3e9cd…` | 3050 B, `8514d00d…` | PROVEN |
| 5 | Sustitución de estado (imagen) | `BOE-A-2025-26847` | Anejo 4, estado FI 105 | **no disponible** | 76597 B tablas, `1c3d1357…` | PARTIAL |
| 6 | Corrección de errata | `BOE-A-2018-2041` | Norma 64, ap. 9 | `norma 54`, `7aae5e6e…` | `norma 53`, `4875cd9e…` | PROVEN |

Ficha completa (con `publication_date`, `effective_date`, `evidence_urls`,
`evidence_raw_sha256`, `reconstruction_method`) en `cases.json`.

Casos obligatorios cubiertos: artículo/norma (1), anejo/estado (2 y 5), modificación
posterior de bloque ya modificado (3), relación con Circular 1/2025 (4), corrección (6).

---

## 6. Granularidad demostrable

- **INSTRUMENT_LEVEL**: `<analisis>` identifica la norma modificadora.
- **BLOCK_LEVEL**: el texto descriptivo del `<posterior>` nombra norma/anejo
  (p.ej. "las normas 4, 60, 70, el anejo 1 … el anejo 8").
- **PROVISION_LEVEL**: el `<texto>` de cada modificador contiene locators explícitos
  y regulares del tipo:
  - `En la norma 4 ... se modifican los apartados 5 y 6`
  - `En el anejo 9 ... se modifica el punto 46`
  - `En el estado FI 106-3 se modifica el primer párrafo de la nota (a)`
  - `Se suprime el punto 97`
  Extraíbles con regex (`scripts/g0c/probe_parse.py:locator_sentences`).
- **TEXT_ONLY / UNKNOWN**: la corrección da página + precepto, no un identificador
  estructurado; el `<analisis>` de 2021/2025 a veces dice "determinados preceptos"
  sin enumerarlos (hay que bajar al `<texto>` del modificador).

Conclusión: PROVISION_LEVEL es alcanzable para texto y para anejos textuales;
para estados financieros el locator es PROVISION_LEVEL pero el texto original no existe.

---

## 7. ¿Puede reconstruirse old → new? y cómo

Clasificación solicitada (A/B/C/D):

```text
A. la fuente ofrece ambas versiones         -> correcciones (caso 6) y old de texto (casos 1,4)
B. el modificador ofrece únicamente new_text -> es el caso general de las modificaciones
C. old_text debe reconstruirse desde original + modificaciones previas -> caso 3 (encadenado)
D. no puede reconstruirse determinísticamente -> anejos/estados del original (imágenes)
```

Detalle:

- **Casos 1 y 4 (texto)**: `old_text` = span del original con clase `articulo` o
  apartado numerado; `new_text` = span tras el locator en el modificador. Ambos textos
  existen y se hashean. PROVEN.
- **Caso 3 (bloque previamente modificado)**: `old_text` de la modificación de 2020 =
  `new_text` de la modificación de 2018 (el bloque quedó reescrito íntegro entonces).
  Encadenado determinista. PROVEN para el tramo 2018→2020; el original pre-2018
  del punto 99 sigue siendo imagen.
- **Caso 2 (anejo textual primera modificación)**: `new_text` existe; `old_text`
  **no** (el anejo original es imagen) → PARTIAL.
- **Caso 5 (estado FI)**: `new_text` son tablas estructuradas del modificador;
  `old_text` **no** existe como texto y ni siquiera hay etiqueta máquina que ligue
  cada imagen con su estado → PARTIAL / D.
- **Caso 6 (corrección)**: la propia corrección da `«…», debe decir: «…»`; PROVEN.

**Orden temporal**: `publication_date` y `effective_date` se obtienen del
`<metadatos>` de cada modificador (`fecha_publicacion`, `fecha_vigencia`), por lo que
la secuencia `original → 2018 → 2020 → … → 2025` es construible con fechas jurídicas
separadas. No se ha entrado en applicability (G0-D).

---

## 8. Comportamiento de anejos y tablas

OBSERVED en `boe_diario_xml__BOE-A-2017-14334`:

```text
<texto>: 4532 <p>, 3 <table>, 326 <img>
clases de imagen: frame-17 (326), imagen (186), imagen_girada (140)
tras "Disposición final única" (p. 4205) aparecen 326 <img> consecutivas (p. 4206..4531)
```

Es decir, **todo el bloque de anejos** (incluido el Anejo 9 textual y todos los modelos
de estados FI/FC/PI/UEM) está publicado como **imágenes**, sin texto. Las 3 únicas
tablas del XML son listas-índice de estados dentro de las normas, no los estados.

En las **normas modificadoras modernas** el anejo sí es estructurado: p.ej.
`BOE-A-2023-5481` tiene 32 `<table>`, `BOE-A-2025-26847` tiene 6 `<table>` y 0 `<img>`.

Consecuencia:

```text
artículos / normas / disposiciones / anejo 9 textual (si estuviera en texto) = reconstruible
anejos y estados de la Circular 4/2017 (imágenes)  = old_text NO reconstruible por texto
```

Para completar anejos haría falta OCR (no determinista, fuera de alcance) o el texto
adaptado del BdE (no es autoridad legal). Por eso la estrategia que funcione "solo
para párrafos" no basta, y G0-C no puede declararse GO.

---

## 9. Comportamiento de correcciones

OBSERVED en `BOE-A-2018-2041`:

- discoverable vía `<analisis><posteriores>` con `<palabra codigo="201">` =
  "CORRECCIÓN de errores"; `rango = "Corrección (errores o erratas)"`;
  `fecha_vigencia` vacía.
- relación explícita con el documento corregido (`<anterior referencia="BOE-A-2017-14334">`).
- el cuerpo da `old` y `new` literales, con página y precepto:
  `1. En la página 119679, en el apartado 9 de la norma 64, donde dice: «norma 54», debe decir: «norma 53».`
- también incluye supresiones ("se eliminan las líneas …") que **alteran el texto base**
  y no son modificaciones ordinarias.
- la ELI expone el corrigendum como recurso propio
  (`/eli/es/cir/2017/11/27/4/corrigendum/20180215/dof`), capturado como evidence.

Riesgo: confundir una corrección con una modificación normativa. Deben ordenarse
aparte y, si alteran el texto, aplicarse antes/entre las modificaciones según fecha,
sin computarse como cambio de vigencia.

---

## 9-bis. Pregunta secundaria: ¿el mismo mecanismo para Circular 1/2025?

OBSERVED sobre `boe_diario_xml__BOE-A-2025-26847`
(SHA-256 `689fbe5e47569045d3bbd99738cae8a4c31583d733ade0e454ed4eb08ca9aa91`):

- el XML diario responde 200 con la misma estructura que el target:
  `estado_consolidacion codigo="0"` y la API consolidada devuelve 404 en
  `/metadatos`, `/analisis` y `/texto/indice` (raws capturados);
- `<analisis><referencias>` presente: 2 `<anteriores>` (`MODIFICA`
  `BOE-A-2013-5720` — Circular 1/2013 — y `BOE-A-2017-14334` — el target de esta
  fase) y `<posteriores/>` vacío: a la fecha de captura ninguna norma posterior
  registrada la modifica;
- `<texto>` totalmente estructurado: 533 `<p>`, 6 `<table>`, 0 `<img>` — a
  diferencia del target, su propio contenido no depende de imágenes.

DERIVED: el mecanismo descubierto en esta fase se aplicaría a Circular 1/2025
exactamente igual que a Circular 4/2017 (mismo canal `diario_boe/xml.php`, mismo
esquema de `<analisis>`, mismo 404 en la colección consolidada). Si aparecen
modificadores futuros se enumerarán en su `<posteriores>` con el mismo formato.
Cuando C1/2025 actúe como **target**, la limitación de los anejos-imagen no le
afecta a su propio texto (todo estructurado); la limitación solo persiste en la
dirección en que C1/2025 modifica los estados-imagen de C4/2017 (caso 5).

---

## 10. Gaps y límites

1. **No hay texto consolidado oficial para el target**: API 404 para
   `BOE-A-2017-14334`, `act.php` redirige a `doc.php`, `/eli/.../consolidado` 404,
   `estado_consolidacion = 0`. La colección consolidada **sí existe** y cubre un
   subconjunto (p.ej. `BOE-A-2020-6187`), pero no al target.
2. **Anejos/estados originales son imágenes**: `old_text` no obtenible por texto.
3. **Exhaustividad**: no demostrable independientemente; solo "todas las registradas
   por el análisis del BOE".
4. **`<analisis>` dinámico**: `fecha_actualizacion` cambia; hay que versionar cada
   captura (se hace por SHA-256 + `retrieved_at`).
5. **BdE CLF no fiable**: la misma URL `...&fc=01-01-2018...` devolvió una vez
   "Error interno" y otra el texto consolidado actual; "Norma a una Fecha" no sirve
   como historial. No puede usarse como fuente de `old_text` determinista.
6. **Sin consolidado, el old_text de tramos antiguos** (p.ej. punto 99 antes de 2018)
   queda solo en la imagen original.
7. **Granularidad textual**, no identificadores estructurados: los locators son
   frases regulares; requieren parseo de texto (demostrado) pero no hay un esquema
   formal máquina-máquina de "qué bloque sustituye a cuál".

---

## 11. Clasificación OBSERVED / DERIVED / INFERRED

**OBSERVED**

- `BOE-A-2017-14334` existe como publicación oficial y su XML diario responde 200
  con texto + `<analisis>`.
- El `<analisis>` del target lista 8 posteriores y 1 anterior; cada modificador
  declara simétricamente al target.
- `datosabiertos/api/legislacion-consolidada` devuelve 404 para el target, para
  `BOE-A-2025-26847` y `BOE-A-2023-5481`; devuelve 200 para normas de control ajenas
  a la familia BdE y también para `BOE-A-2020-6187` y `BOE-A-2020-15602`
  (`estado_consolidacion=3`), que sí están en la colección consolidada.
- El XML original contiene 326 `<img>` y 3 `<table>`; los anejos no tienen texto.
- Las normas modificadoras contienen locators explícitos por norma/apartado/punto/
  estado y el `new_text`.
- La corrección contiene pares literales `donde dice / debe decir`.
- BdE CLF no sirvió de forma estable la vista a fecha 2018-01-01.

**DERIVED**

- Por las fechas de publicación/vigencia, el orden de las operaciones es
  2018-02, 2018-12, 2020-06 (x2), 2020-12, 2021-12, 2023-03, 2025-12.
- La cadena 2018→2020 del punto 99 es reconstruible porque el `new_text` de 2018
  es el `old_text` de 2020.
- La relación imagen↔estado en el original no es resoluble: no hay etiqueta.
- El canal `<analisis>` es la mejor cobertura disponible, pero no garantiza
  exhaustividad independiente.

**INFERRED** (no usable para declarar PASS)

- La correspondencia semántica entre alguna tabla del anejo de 2025 y el estado
  FI 105 concreto (se usó la denominación del índice + contenido de derivados).
- Que `BOE-A-2020-15602` punto 46 no había sido modificado antes (se asume por no
  aparecer en modificadores previos), luego su `old_text` original sería el de la
  imagen.

---

## 12. Veredicto

```text
G0-C Discovery = PARTIAL
```

Motivación:

- **No es GO**: la reconstrucción `old → new` de anejos/estados no es posible con
  fuentes oficiales estructuradas (el original es imagen); el requisito "tratar
  artículos y anexos/estados" no se cumple para la clase anejos.
- **No es FAIL**: existe una ruta oficial, reproducible y sin LLM que (1) descubre
  modificadores con cross-check, (2) identifica la disposición afectada a nivel de
  precepto, (3) reconstruye `old → new` en los casos textuales y encadenados,
  (4) mantiene provenance completa (URL + SHA-256), y (5) trata correctamente
  correcciones como clase aparte.

Cumple la definición de PARTIAL del enunciado: "puede reconstruirse una parte
material pero existen clases de cambio que requieren tratamiento diferenciado
(artículos = PROVEN, anexos complejos = NOT_PROVEN)".

---

## 12-ter. Addendum — G0-C.1 Annex/State Evidence Probe

> Este addendum corrige el encuadre de la limitación de anejos tras el probe
> posterior (`evidence/g0c1/`, `scripts/g0c1/`, `tests/g0c1/`). El veredicto
> `PARTIAL` de G0-C se mantiene para la reconstrucción **textual** `old → new`.

La formulación correcta de la limitación, ya no "reconstrucción imposible":

```text
old textual representation    NOT_PROVEN   (el XML porta <img>, sin texto)
old official representation   PROVEN       (imagen oficial de página BOE,
                                            SHA-256, ligada a estado y página)
change declaration            PROVEN       (cláusula del modificador, literal)
semantic old→new diff         NOT_PROVEN   (requeriría interpretar la imagen)
```

Hallazgos que modifican el análisis anterior:

- El PDF oficial contiene **capa de texto embebida** (OCR del propio BOE, no
  nuestro); el árbol `/Pages` ordena las 588 páginas = 119454–120041.
- `doc.php` numera las 326 imágenes con `alt="1..326"` (OBSERVED); la firma
  termina en p. 119715 → `alt=N ↔ página BOE 119715+N` (DERIVED).
- La corrección BOE-A-2018-2041 cita literalmente **(página, estado)** en 10
  ítems de anejos → 10/10 anclas independientes confirman el binding.
- Resultado: 99 estados → rangos de página → imágenes, en `annex-map.json`.
- Incluso los modificadores publican estados como imágenes (C.2/2020:
  9 `<p imagen>` en sus anejos) → la cadena debe admitir `IMAGE → IMAGE`.
- En cadenas, el hop posterior puede ser textual en ambos lados
  (FI 142-1.1: C.2/2018 la republicó como `<table>`; C.1/2025 la vuelve a
  sustituir → hop 2 = `TEXT_DIFF_PROVEN`).

Seis casos en `evidence/g0c1/state-cases.json` demuestran la cadena factual
`estado → old repr (imagen, SHA) → MODIFIED_BY → new repr (tabla/texto/
imagen, SHA)` con `diff_level ∈ {TEXT_DIFF_PROVEN, VISUAL_PREDECESSOR_PROVEN,
DECLARED_CHANGE_PROVEN, SEMANTIC_DIFF_NOT_AVAILABLE}`.

Consecuencia: el historial **factual** de modificaciones es reconstruible al
completo; lo que permanece no probado es el *diff textual de contenido* sobre
lados-imagen. Ítem DERIVED "la relación imagen↔estado no es resoluble" queda
**superado**: es resoluble a nivel de página, anclado por la corrección.

Implicación de diseño (no implementada aquí): los bloques necesitan
`representation_kind` (`TEXT`/`TABLE`/`IMAGE`/`PDF_PAGE`) +
`content_sha256` + `artifact_locator`; `text_content` nullable.

---

## 12-bis. Comparativa de estrategias

Dimensiones medidas contra los canales ya caracterizados (no puntuación subjetiva):

| Estrategia | coverage | determinism | granularity | raw evidence | reconstruction difficulty | fragility | licensing |
|---|---|---|---|---|---|---|---|
| A — Target-centric | relaciones + texto original del target; **sin consolidado** | HIGH (XML) | INSTRUMENT + BLOCK (texto `<analisis>`) | FULL | ALTA: old/new no salen del target; anejos = imagen | LOW | BOE |
| B — Modifier-centric | los 8 modificadores registrados; **exhaustividad no garantizada** sin el índice del target | HIGH (XML) | PROVISION/BLOCK | FULL | MEDIA: aplicar secuencialmente; encadenar `new`→`old` | LOW | BOE |
| C — BdE-assisted | índice cronológico ayuda al discovery; CLF da consolidado actual adaptado; **sin historial fiable** | **LOW** (respuestas inconsistentes observadas) | artículo/anejo | HTML inestable | ALTA: no da `old_text` determinista | **HIGH** | BdE (texto adaptado, no autoridad) |
| D — Hybrid | la mayor: `<analisis>` + XML modificadores + XML target + correcciones; BdE solo cross-check | HIGH | PROVISION (texto) / BLOCK (anejos) | FULL | MEDIA en texto; **BLOQUEADA en anejos por imagen** | LOW | BOE autoridad; BdE complementario |

Criterios: las mismas definiciones de `channel-matrix.json` (`criteria`). A y B
comparten el canal BOE; su diferencia real es la *dirección del discovery*, y B
depende de A para no mantener una lista manual. C no supera el listón de
determinismo/fragilidad observado. D es la composición de A+B+G con F degradado a
verificación.

## 13. Estrategia recomendada (solo tras los experimentos)

**Strategy D — Hybrid, con BOE como autoridad y precedencia explícita**, pero
limitada a texto y con marca de límite para anejos:

1. **Discovery (E2)**: `<analisis><referencias>` del `diario_boe/xml.php` del target
   + cross-check en `<anteriores>` de cada modificador. Registrar `fecha_actualizacion`.
2. **new_text (D)**: XML diario de cada modificador; locators por regex +
   delimitación estructural (`parrafo_2` / `sangrado_articulo`).
3. **old_text (A2)**: XML diario del original por bloques (`articulo`/apartado/punto);
   encadenar `new_text` previo para bloques reescritos (caso 3).
4. **Correcciones (G)**: clase separada, orden por fecha, `old/new` literales.
5. **Anejos/estados**: marcar `NOT_PROVEN` mientras el original sea imagen; abrir
   línea técnica diferenciada (OCR o fuente complementaria) sin declararla autoridad.
6. **BdE (F)**: solo como verificación manual/cross-check; nunca como autoridad ni
   como historial (no fiable).
7. **Licensing**: BOE es la fuente autoritativa con condiciones de reutilización;
   no redistribuir el consolidado sin metadatos; BdE se cita como adaptado.

Descartadas: Strategy A pura (no hay consolidado target-céntrico), Strategy B pura
(no hay garantía de descubrir modificadores no registrados), Strategy C (BdE no es
autoridad ni fiable históricamente).

---

## 14. Reproducción y `git status --short`

```powershell
# capturas (solo red; escribe evidence/g0c/raw + manifest con SHA-256)
python scripts/g0c/probe_channels.py
python scripts/g0c/probe_bde.py

# artefactos de discovery
python scripts/g0c/probe_relations.py   # modifiers.json
python scripts/g0c/probe_cases.py       # cases.json
python scripts/g0c/probe_matrix.py      # channel-matrix.json

# verificación offline
uv run pytest
```

Estados de confianza: `PROVEN` / `PARTIAL` / `NOT_PROVEN` calculados por regla de
disponibilidad de fuentes, nunca por modelo.

```text
$ git status --short
?? evidence/
?? scripts/
?? tests/g0c/
```

Sin cambios en ficheros ya versionados. El freeze G0-A/B permanece intacto
(`fb0dc676dd4ca8e17c211a12f5507cc526588e14`). No se ha hecho commit.
