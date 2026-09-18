# uslm (US Legislative Markup)

## 1. Source freeze

- repo: usgpo/uslm — https://github.com/usgpo/uslm
- commit inspected: `100338992150` (main HEAD, review 2026-09-19)
- license: US Government work — public domain/CC0-1.0
  (LICENSE pin pending at write; 17 U.S.C. 105 applies)
- artifacts: `uslm-2.x.xsd`, `USLM-User-Guide.md` §12–13

## 2. Problem fit

- `problems/stable-node-identity.md` — primary
- `problems/amendment-actions.md` — secondary (redesignation vocab)

Components:

- Four-attribute identity model: `@id` (minted immutable GUID,
  "should not reflect any aspect subject to change"), `@identifier`
  (evolving URL-path context), `@temporalId` (computed current
  spelling), `@name` (template). Unnumbered content is *typed* (`<p>`
  vs `<paragraph>`), never implicitly numbered.
- `AmendingActionTypeEnum.redesignate` — "changes the number of an
  existing provision" (first-class bill action).
- `StatusEnum.renumbered`/`transferred` — code-side tombstone: the
  provision element remains at the old locator with status deferring
  state to the new location.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | N/A→PARTIAL (it IS the source format) |
| exact structural span | YES (identifier addressing) |
| deterministic | YES (schema) |
| ambiguity unresolved | PARTIAL (`unknown` action enum exists) |
| fail closed | PARTIAL |
| synthetic consolidation | YES (represents consolidated code) |
| normalized content | YES |
| original preserved | YES |
| temporal provenance | YES (startPeriod/endPeriod, temporalId) |

## 4. Verdict

**PATTERN** — vocabulary prior art on both sides of redesignation:
bill-side `redesignate` action + code-side `renumbered` tombstone
status ("not in effect in the old location; status defined in the new
location" — prior art for old locator persisting as a relation
endpoint). The three-slot identity split (durable handle / current
address / current spelling) confirms locator ≠ identity ≠ address.
Nothing binds these to source-span evidence; no code to port.

Falsification idea (WS-A): check frozen corpus for old-locator
residues — tombstone state needed only where the source declares one.
