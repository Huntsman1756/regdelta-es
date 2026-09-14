# G0-G DEV evaluator contract (frozen at first baseline run)

Operationalization of `evidence/g0g/protocol.md`. It changes no metric
names, denominators, or definitions; it fixes only how each frozen term
is computed. Any deviation discovered later is recorded as a deviation,
not edited here.

## Scope and isolation

- DEV allowlist is derived at runtime from `selection.json`
  (`GENERALIZATION_DEV` entries only). Passing a `SEALED_HOLDOUT`
  boe_id aborts the evaluator (FAIL CLOSED).
- Evidence fetch serves bytes exclusively from
  `evidence/g0g/dev/manifest.json` entries, as
  `FetchResult(..., via=EVIDENCE_IMPORT)`. A URL not present in the
  manifest returns `error_class="MISSING"`. Zero network.
- Gold is read only for keys in the DEV allowlist.
- One fresh `data/regdelta.sqlite` per target; metrics never mix DBs.
- `COMBINED_DEV_SMOKE` runs all eight targets sequentially in one
  additional fresh DB; it is diagnostic, never a metric source.

## Pipeline per target

1. `history.reconstruct(conn, data_dir, target, evidence_fetch)` —
   exceptions recorded per stage; a raised exception is itself a
   failure (`stage=reconstruct`).
2. Declared-modifier discovery: `report["modifiers"]` is the
   runtime-discovered set; gold is
   `gold/declared_modifiers.json[target].declared`.
   Reverse cross-check: an `instrument_relations` row exists with
   `declaring_instrument_id = modifier`, `direction='ANTERIOR'`,
   `other_boe_id = target`.
3. Relation inventory straight from `modification_relations`.
4. Applicability: for each modifier of the target whose diario XML
   (dev raw) contains a `<p>`/heading node whose text matches
   `^disposici[oó]n (final|transitoria)` (case/accents-insensitive,
   independent regex over the raw bytes — `applicability_parser` is
   NOT used to decide eligibility), run
   `applicability.build(conn, data_dir, modifier, target)`; record
   success/exception and clause/effect/target counts.
5. Query execution: run, without requiring non-empty output —
   `changes(since=first_pub-1d, until=last_pub+1d, target)`,
   `affects(target)`, `upcoming(from_date=first_pub, days=365,
   target)`, `as_of(target, last_pub)`, `diffing.diff(target,
   from=first_pub-1d, to=last_pub)`. Each is `OK` or records the
   exception class.

## Metrics (formulas frozen)

```text
declared_modifier_recall =
  |{m ∈ gold: m ∈ discovered ∧ reverse-link(m,target) exists}|
  / |gold(target)|
  per target; cell/aggregate = same formula over pooled sets.

operation_parsing_rate =
  |relations with operation_kind ∈ {SUBSTITUTE, MODIFY, ADD, DELETE,
   CORRECT}| / |relations emitted|

subject_locator_resolution =
  |relations whose locator_key independently resolves to ≥1 node or
   image in the official target diario XML| / |relations emitted|
  Independent resolver (evaluator-side, NOT operations code):
  normalize (lower, strip accents, collapse spaces); token = the
  distinguishing suffix of the key (e.g. '33' for norma:33,
  'fi 105' for estado:FI 105, '3' for anejo:3); resolves iff a target
  node heading/text or an <img>/<imagen> node's alt/src contains the
  token with the locator-kind prefix (norma/estado/anejo/etc.)
  consistent.

representation_binding =
  |relations whose REQUIRED sides are bound| / |relations|
  required(op): ADD→after only; DELETE→before only; SUBSTITUTE→both;
  MODIFY|CORRECT|other→before always, after required only when no
  declared_literals pair exists (mirrors history._resolution).

chain_reconstruction =
  |subjects with verdict CHAIN_PROVEN| / |subjects with >1 relation|
  per subject: hops ordered by (publication_date, relation_id);
  per consecutive pair: both sides present → equal→PROVEN-hop,
  different→BROKEN; either side missing → NOT_PROVABLE-hop.
  subject verdict: any BROKEN→CHAIN_BROKEN; all hops PROVEN→
  CHAIN_PROVEN; else CHAIN_NOT_PROVABLE.

applicability_extraction =
  |eligible modifier-target pairs with ≥1 persisted clause|
  / |eligible pairs|   (eligible = independent detector positive)

query_execution = 5/5 surfaces without exception per target
  (fraction reported per target and pooled).

false_positive_facts = |relations with verdict FALSE_FACT| (audit).

source_limitations = |failures classified SOURCE_LIMITATION|.
```

## Audit (mechanical, per relation, 100 %)

For every emitted `modification_relations` row the auditor checks the
positive claims actually present:

```text
modifier_declared          modifier boe ∈ gold[target] declared set
kind_matches_palabra       CORRECTION iff gold palabra ~ /CORR/
operation_verb_consistent  independent verb regex over locator_raw
                           (sustituy→SUBSTITUTE, añad|adicion→ADD,
                           suprim|derog→DELETE, modific|redact|
                           queda→MODIFY, correg→CORRECT);
                           UNMATCHED_VERB → NOT_CHECKABLE (never fail)
target_locator_resolves    independent resolver (above) finds the
                           locator in the official target XML
before_binding             if bound: node_span re-extraction from the
                           source XML reproduces text_content exactly
                           (TABLE: rows joined ' | ', nodes '\n'),
                           or IMAGE: every locator page src ∈ source
                           XML img set ∧ blob_sha256 == sha256 of the
                           captured artifact bytes
after_binding              same checks against the modifier XML
resolution_consistent      resolution == recomputed rule from
                           (operation_kind, before?, after?, literals?)
publication_date_matches   == modifier XML <fecha_publicacion>
subject_in_target          subject.instrument_id == target iid
declared_literals_sane     each literal pair non-empty when present
```

Verdicts: any CONTRADICTED claim → relation verdict `FALSE_FACT`;
otherwise `PASS`. A claim is `NOT_CHECKABLE` when the auditor lacks a
mechanical path (e.g. verb vocabulary, unstructured locator); these are
counted and listed, never auto-failed, and never counted as verified.
Doubtful manual cases → `FALSE_FACT` per protocol.

Register: `evidence/g0g/audit.jsonl` — one JSONL row per relation
(`run_id, target, relation_id, claims_checked{}, verdict,
evidence_locator{}, evidence_quote`).

## Failure classes

Exactly one of `SOURCE_LIMITATION | ACQUISITION_FAILURE |
PARSER_FAILURE | SCHEMA_FAILURE | EVALUATION_FAILURE` per discrepancy.
`SOURCE_LIMITATION` only when the dev raw provably lacks the datum
(the classifier emits the inspected quote/locator proving absence).
A fetch of an uncaptured-but-needed artifact is `ACQUISITION_FAILURE`
(stage=acquire). Missing evidence is never downloaded mid-run.

## Combined DEV smoke checks

After sequential reconstruction of all eight targets in one DB:

```text
PRAGMA foreign_key_check → empty
no relation_id shared across different target instruments
every subject.instrument_id ∈ the 8 target iids
every relation's subject.instrument_id == its target
all five query surfaces execute per target
zero anomalies referencing a different target's instruments
```

## Run artifacts

Each run writes `evidence/g0g/dev/runs/NNN-<slug>/` with
`run.json` (runtime_head, src_tree_sha, evaluator_sha256,
dev_manifest_sha256, selection_sha256, gold_sha256, started_at,
finished_at), `metrics.json`, `targets.json`, `failures.jsonl`,
`relations.jsonl`, `report.md`, plus `combined-dev.json` in the run
dir. `audit.jsonl` is appended at `evidence/g0g/audit.jsonl` with the
run_id.
