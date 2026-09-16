# PORT-CNMV-0 — Metadata-only corpus scout & sealed split

```text
BASE
  3470f69

QUESTION
  ¿Existe un corpus CNMV-Circular suficientemente denso para
  falsar SourceProfile sobre targets nunca usados por RegDelta,
  manteniendo BOE como autoridad documental y sin abrir todavía
  contenido normativo?

RUNTIME CHANGES
  0

REUSE
  PORT Huntsman1756/esdata@80b9eb0 discovery logic
  DO NOT rewrite CNMV year-range discovery

DISCOVERY
  CNMV official Circular index
    -> year-range pages
    -> official BOE links
    -> canonical BOE-A id

BOE INSPECTION ALLOWED
  <metadatos>
  <analisis>/<referencias>
  anteriores/posteriores
  title/date/status metadata

BOE INSPECTION FORBIDDEN
  <texto>
  annex semantic content
  operative clauses

ELIGIBLE
  issuer = CNMV
  rango = Circular
  BOE id resolvable
  diario XML captured
  declared_modifier_count >= 1

STRESS RANK
  declared_modifier_count DESC
  multi_target_modifier_event_count DESC
  corrigendum_count DESC
  sha256("regdelta-port-cnmv-v1|" + boe_id) ASC

SEEN
  BOE-A-2020-14107 = SEMANTICALLY_SEEN
  (we opened its BOE text during this architecture review)
  therefore DEV-only / never HOLDOUT

SPLIT
  require >= 8 unseen eligible targets, else STOP

  take top 8 unseen by frozen stress rank
  odd rank  -> DEV
  even rank -> SEALED_HOLDOUT

  BOE-A-2020-14107 may be an additional DEV fixture,
  never part of the 8-case blind split

CAPTURE
  capture all official raw artifacts
  hashes + manifest
  HOLDOUT bytes sealed before DEV semantic opening

OUTPUT
  evidence/port-cnmv/corpus-frame.json
  evidence/port-cnmv/selection.json
  evidence/port-cnmv/semantic-seen-set.json
  evidence/port-cnmv/holdout/SEAL
  evidence/port-cnmv/OSS-RECON.md
  evidence/port-cnmv/PORT-CNMV-0.md

TERMINAL
  READY_FOR_CNMV_PROFILE_PROBE
  |
  INSUFFICIENT_CORPUS
  |
  ACQUISITION_BLOCKED
```

## Follow-on (preregistered shape, not yet authorized)

```text
PORT-CNMV-1
  abrir SOLO DEV
  crear profiles/cnmv.py + boundary/discovery package
  core semantic modules: ZERO changes
  (operations/ownership/binding/history/document/db/
   applicability_parser + core taxonomies untouchable;
   needing a new LocatorKind/OperationKind/proof policy =
   CORE_EXTENSION_REQUIRED, the experiment's result)

PORT-CNMV-2
  freeze profile + evaluator
  abrir SEALED_HOLDOUT una sola vez

terminal:
  PROFILE_PORTABLE | PROFILE_LIMIT | CORE_EXTENSION_REQUIRED
```

PASS may not come from silence: the eventual holdout requires zero
`FALSE_*`, 100% operation accounting and a minimum positive count of
relations/bindings per target; the exact threshold is set after
PORT-CNMV-0 once the frame volume is known.

## Execution record

(filled at run time — see selection.json / SEAL for the result)
