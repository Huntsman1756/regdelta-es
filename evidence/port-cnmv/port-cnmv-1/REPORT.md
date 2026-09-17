# PORT-CNMV-1 — DEV report

**Proposed terminal state: `PROFILE_LIMIT`**

The second `SourceProfile` (`cnmv-circular`) operates end-to-end on the
four DEV targets with zero core changes — but enumerated CNMV
constructs admit only documented abstention under the frozen contract
(register below). Adjudication of this proposal is the gate decision;
`PROFILE_LIMIT` preregisters a narrower PORT-CNMV-2 scope.

**Evaluator remediation (PORT-CNMV-1R):** the first evaluator revision
defaulted every relation to `CONFIRMED_POSITIVE` and only demoted on
contradiction — unverified O1/O2/binding dimensions were silently
accepted. The adjudicator rejected that semantic under prereg §8. The
current evaluator defaults every relation to `EVALUATOR_NOT_PROVABLE`
and promotes to `CONFIRMED_POSITIVE` only when all of the following
independently succeed: clause presence, O1 attribution (clause-level
`Circular N/YYYY` ref, else containing-section head ref, else doc title
target, else doc-wide unique head ref), exact `locator_key` equality
(root-only agreement is not confirmation), bound-representation
fidelity (`content_sha256` + node-span text / ordered table-line
containment / image `blob_sha256` against the captured blob), and
independent subject resolution. Dimensions the evaluator cannot check
become `EVALUATOR_NOT_PROVABLE` — inability to falsify is not
confirmation — and are journaled to `failures.jsonl` with
`CNMV_EVALUATOR_MODEL_ERROR`. Per-relation verdicts are persisted in
`verdicts.jsonl`.

## Freeze record

| artifact | sha256 / ref |
|---|---|
| profile `src/regdelta/profiles/cnmv.py` | `b10473487d18065b823df5c1637cc6a7103e5d019b4ff4f74ca7b1897333a8b9` |
| runtime `src/regdelta` tree | `b67755f73912217242921f0c8c8cc5babd4b0e97` (git tree @ `3f713cc`) |
| boundary adapter `scripts/port-cnmv/cnmv_boundary.py` | `d5af7efcd52f3753baddd61e507cd40b6cd17675e4a70d550738ad174e3f5ff1` |
| runner `scripts/port-cnmv/run_dev_probe.py` | `5777f1ea469d7cdc9aa61869e7518348cafc49ba364feb20a8b3afb9fc19d690` |
| evaluator `scripts/port-cnmv/evaluate_dev.py` | `ac40e78c31aa96d8da1a78e9f71232bfaa10dc5d98df97a51ec382c8da5a960d` |
| materializer `scripts/port-cnmv/materialize_run.py` | `3d89c3023256dc94ea4aa68506876bca1a6f8a6ca31028e498240fed6f02d661` |
| journal `journal.jsonl` | `928f44891567feffbd7000c6a50dfe3e2bac8bdfc2b307e758fcd1aad19518e7` |
| DEV run envelope | `dev-run-013.json` (materialized: `runs/013-dev-final/`) |
| evaluator output | `eval-dev-006.json` |

Evaluator import manifest (firewall audit — complete transitive
project-module set): `regdelta`, `regdelta.document`,
`regdelta.sources`, `regdelta.sources.boe_diario`,
`regdelta.sources.boe_doc`, `regdelta.sources.boe_pdf`. No profile,
registry, `active_profile`, or profile-backed helper is imported.
`EVALUATOR_INDEPENDENCE_BROKEN` does not apply.

## DEV observed volume

| target | modifiers | leaf ops | accounting | relations | RESOLVED | PARTIAL | UNRESOLVED |
|---|---|---|---|---|---|---|---|
| BOE-A-2008-16091 | 10 | 68 | 17+39+12=68 ✓ | 18 | 4 | 4 | 10 |
| BOE-A-2008-20895 | 9 | 116 | 54+57+4+1=116 ✓ | 70 | 20 | 24 | 26 |
| BOE-A-2010-13162 | 6 | 55 | 14+39+2=55 ✓ | 30 | 9 | 6 | 15 |
| BOE-A-1994-28725 | 6 | 12 | 3+3+6=12 ✓ | 1 | 1 | 0 | 0 |

## Evaluator verdicts (remediated, eval-dev-006)

| target | relations | CONFIRMED_POSITIVE | ABSTENTION_CONFIRMED | ABSTENTION_DISPUTED | EVALUATOR_NOT_PROVABLE | FALSE_* |
|---|---|---|---|---|---|---|
| BOE-A-2008-16091 | 18 | 3 | 1 | 12 | 2 | 0 |
| BOE-A-2008-20895 | 70 | 16 | 18 | 18 | 16 | 2 FLD |
| BOE-A-2010-13162 | 30 | 3 | 15 | 6 | 6 | 0 |
| BOE-A-1994-28725 | 1 | 1 | 0 | 0 | 0 | 0 |
| **total** | **119** | **23** | **34** | **36** | **24** | **2** |

- `CONFIRMED_POSITIVE` 23 — every required dimension independently
  re-derived: clause found in the modifier, O1 TARGET via clause /
  section / title evidence, exact locator equality, all bound sides'
  representations verified against raw evidence, subject resolved in
  the target.
- `ABSTENTION_CONFIRMED` 34 — runtime abstention reproduced by the
  evaluator (subject genuinely absent / no after-content declared).
- `ABSTENTION_DISPUTED` 36 — runtime abstained where the evaluator sees
  the evidence (subject resolves, or after-content present in the
  modifier). Reported as coverage gaps, not false claims.
- `EVALUATOR_NOT_PROVABLE` 24 — exact reasons in `failures.jsonl`
  (`CNMV_EVALUATOR_MODEL_ERROR`): image-only `estado:*` subjects (6),
  two-level `apartado X) → número N` locators (7), deep anejo/letra
  sub-keys beyond evaluator extraction (8), sub-items inside
  tables/continuations (2), O1 undetermined (1).
- `FALSE_FACT` 0, `FALSE_SUBJECT_ATTRIBUTION` 0, `FALSE_BINDING` 0.
- `FALSE_LOCATOR_DECLARATION` 2 — genuine disagreements on renumbering
  clauses in 20895: "la letra n) del número 3 … pasa a ser el número 4"
  emitted as `norma:49.apartado:4.letra:n` (evaluator derives
  `norma:49.apartado:3.letra:n`), and "el número 4 … pasa a ser el
  número 5" emitted as `norma:49.apartado:5` (evaluator derives
  `norma:49.apartado:4`). The runtime locators denote the post-change
  identity; the clause names the pre-change subject. Recorded as
  findings for adjudication.

Independent clause census: 2002.

## §9 checks

- **Operation accounting 100%** — leaf ops = sum of dispositions on
  all four targets (table above).
- **No fabricated facts** — FALSE_FACT / FALSE_SUBJECT_ATTRIBUTION /
  FALSE_BINDING = 0 under the strict evaluator; the 2 FLD findings are
  locator-identity disagreements on renumbering clauses, adjudicated
  above.
- **No silent pass** — every target emits ≥1 evaluator-confirmed claim
  (28725: the `norma:11` rewrite, RESOLVED + CONFIRMED_POSITIVE).
- **BdE regression** — `import regdelta.profiles` registers exactly
  `bde-circular` (implicitly active); `pytest tests` = 347 passed.

## Abstention register (cause → span)

Binding/lifecycle abstentions, all journaled in `audit.jsonl`:

- `BINDING_NOT_FOUND` `no_structural_candidate` (43): before-side
  content absent from the target XML — image-only annex models and
  unnumbered sub-structure.
- `BINDING_NOT_PROVABLE` `no operation-owned content link` (32),
  `clause scopes below the recorded subject locator` (15),
  `following content is governed by a different sub-clause` (9),
  `bound span does not restate the subject locator` (1),
  `subject state UNKNOWN/DELETED` (10): ownership, scope and
  chain-lifecycle discipline.
- `CHAIN_DISCONTINUITY` deleted/unknown (10).
- `AMBIGUOUS_BINDING` `candidate_count>1` (2).
- `UNBOUND_SUBJECT` (51): relations whose required bindings all
  abstained (ADD 11, DELETE 11, MODIFY 16, SUBSTITUTE 13).

Construct-level abstentions (the PROFILE_LIMIT register):

1. **`seccion:` subjects not materialized** — `"seccion"` already
   exists in the frozen `LOCATOR_KINDS` registry and is recognized by
   `ownership.py`; the gap is that `_compose_keys()` has no path to
   emit `seccion:` subjects, so "La Sección Quinta … queda redactada"
   (28725, modifier 2008-7880 item Dos) stays in the mention record
   without a composed subject. A core *composition/capability* gap,
   not a taxonomy-extension gap.
2. **Unnumbered disposiciones** — "una disposición transitoria con la
   siguiente redacción" carries no ordinal; `disp:` keys are
   `tipo.ordinal` pairs, so no key is composed (journal #12).
3. **Two-level nesting** — "número N del apartado X) de la norma M"
   nests under a lettered apartado; the flat key space cannot express
   the intermediate level, so the composed key abstains.
4. **Image-only annex content** — `boe_diario` `<img href>` carries no
   fetchable source and the 162-page legacy PDF of 20895 has zero
   image-annex pages (`n_images=0` → PREANNEX), so `estado:*` subjects
   on that target abstain rather than fabricate.
5. **Unnumbered continuation items** — apartados 6–8 of norma 29
   (20895) exist as unnumbered continuations, not item starts;
   `norma:29.apartado:8` correctly abstains `NOT_PROVABLE`.

## Frozen positive-evidence rule for PORT-CNMV-2

```text
Per HOLDOUT target:
  - operation accounting = 100% (leaf ops = sum of dispositions)
  - >= 1 CONFIRMED_POSITIVE relation, OR every emitted relation a
    classified abstention with a named cause
  - FALSE_FACT = FALSE_SUBJECT_ATTRIBUTION = FALSE_LOCATOR_DECLARATION
    = FALSE_BINDING = 0
  - no fetch outside the HOLDOUT manifest; no semantic HOLDOUT access
    before this gate's adjudication
Expected DEV-observed volume: ~1-70 relations/target depending on
modifier density; confirmed-positive fraction ~15-30%.
```

## Journal summary (16 entries)

Harness/ordering (#1–#4), canonical `anejo` keying + `bis|ter|quáter`
(#5–#6), ordinal-word operative openers + `seccion` visibility (#7),
legacy stylesheet boundary adapter (#8), marked numeric ordinals (#9),
letter-spaced/legacy PDF state codes (#10–#11 with families A/CA/GA/P),
bogus `disp:transitoria.con` ordinal capture (#12), stale persist-dir
contamination (#13), evaluator finding adjudication (#14), provisional
adjudication `PROFILE_LIMIT` + reviewer checks (#15), evaluator
remediation PORT-CNMV-1R: NOT_PROVABLE default, full-locator O2,
bound-rep fidelity verification, per-relation verdict persistence,
`seccion` report correction, `.gitignore` revert (#16).
