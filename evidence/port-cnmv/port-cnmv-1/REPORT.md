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

**Redesignation abstention (PORT-CNMV-1R2):** the strict evaluator
surfaced 2 `FALSE_LOCATOR_DECLARATION` — `pasa a ser el número N`
renumbering clauses emitted the *post-change* locator as a `MODIFY`
subject. Redesignation requires old→new locator continuity the frozen
core cannot express (paths locate, they do not identify), so the
claim is a false identity, not a coverage gap. The profile now
narrows `pasa(n) a ser/denominarse` so a structural-designator
destination no longer counts as an operative `MODIFY` verb — a
generic grammar rule with no BOE-ID/target special-casing;
non-designator complements ("pasa a ser el siguiente", "pasa a
denominarse «X»") stay operative. Excluded clause spans are journaled
to `audit.jsonl` as `PROFILE_LIMIT_REDESIGNATION` with an
`operative_candidate` flag, and `metrics.json` demonstrates
`operative_candidates = leaf_operations + excluded candidates` —
nothing drops silently. The two false relations were removed, not
reclassified; the whole observed redesignation family (8 relations)
is now abstained.

## Freeze record

| artifact | sha256 / ref |
|---|---|
| profile `src/regdelta/profiles/cnmv.py` | `6be19dcde3a7de83290822124b9943874fb23f396e0ef7725af355fa278991ab` (R2: redesignation abstention) |
| runtime `src/regdelta` tree | `0278ff59e4168a59e39f7a0845e4b570b9f63ef9` (git tree @ `711f5f9`; delta vs `b67755f` is `profiles/cnmv.py` only) |
| boundary adapter `scripts/port-cnmv/cnmv_boundary.py` | `d5af7efcd52f3753baddd61e507cd40b6cd17675e4a70d550738ad174e3f5ff1` |
| runner `scripts/port-cnmv/run_dev_probe.py` | `ce6224ac4d6e2f92c3e70334fc84ae715309e1abb5d78d3035cd61dfeb44bf23` (R2: redesignation accounting) |
| evaluator `scripts/port-cnmv/evaluate_dev.py` | `ac40e78c31aa96d8da1a78e9f71232bfaa10dc5d98df97a51ec382c8da5a960d` (unchanged since remediation) |
| materializer `scripts/port-cnmv/materialize_run.py` | `4055bafc901ac0b629c6a19fa498bf2b09f5d8706e6a94c6402d9c894f3b9c8c` (R2: redesignation audit lines + candidate accounting) |
| journal `journal.jsonl` | `c8501be2ce52130523719c338eea8b1de6ee4cad89b734a00d8175393ea9a3ea` |
| DEV run envelope | `dev-run-014.json` (materialized: `runs/014-r2-redesignation/`; prior: `dev-run-013.json` → `runs/013-dev-final/`) |
| evaluator output | `eval-dev-007.json` |

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
| BOE-A-2008-20895 | 9 | 113 (+3 redesignation) | 51+57+4+1=113 ✓ | 62 | 19 | 19 | 24 |
| BOE-A-2010-13162 | 6 | 54 (+1 redesignation) | 14+38+2=54 ✓ | 30 | 9 | 6 | 15 |
| BOE-A-1994-28725 | 6 | 12 | 3+3+6=12 ✓ | 1 | 1 | 0 | 0 |

Candidate accounting (run-013 → run-014): 113+3=116 and 54+1=55 —
every leaf op the abstention removed is a journaled
`PROFILE_LIMIT_REDESIGNATION` span.

## Evaluator verdicts (remediated evaluator, post-R2 — eval-dev-007)

| target | relations | CONFIRMED_POSITIVE | ABSTENTION_CONFIRMED | ABSTENTION_DISPUTED | EVALUATOR_NOT_PROVABLE | FALSE_* |
|---|---|---|---|---|---|---|
| BOE-A-2008-16091 | 18 | 3 | 1 | 12 | 2 | 0 |
| BOE-A-2008-20895 | 62 | 16 | 18 | 17 | 11 | 0 |
| BOE-A-2010-13162 | 30 | 3 | 15 | 6 | 6 | 0 |
| BOE-A-1994-28725 | 1 | 1 | 0 | 0 | 0 | 0 |
| **total** | **111** | **23** | **34** | **35** | **19** | **0** |

- `CONFIRMED_POSITIVE` 23 — every required dimension independently
  re-derived: clause found in the modifier, O1 TARGET via clause /
  section / title evidence, exact locator equality, all bound sides'
  representations verified against raw evidence, subject resolved in
  the target.
- `ABSTENTION_CONFIRMED` 34 — runtime abstention reproduced by the
  evaluator (subject genuinely absent / no after-content declared).
- `ABSTENTION_DISPUTED` 35 — runtime abstained where the evaluator sees
  the evidence (subject resolves, or after-content present in the
  modifier). Reported as coverage gaps, not false claims.
- `EVALUATOR_NOT_PROVABLE` 19 — exact reasons in `failures.jsonl`
  (`CNMV_EVALUATOR_MODEL_ERROR`).
- `FALSE_FACT` 0, `FALSE_SUBJECT_ATTRIBUTION` 0,
  `FALSE_LOCATOR_DECLARATION` 0, `FALSE_BINDING` 0 — the 2 renumbering
  FLDs of eval-dev-006 are gone because the redesignation clauses no
  longer emit relations at all (see R2 note above and register #6).

Independent clause census: 2002.

## §9 checks

- **Operation accounting 100%** — leaf ops = sum of dispositions on
  all four targets, and `operative_candidates = leaf_operations +
  excluded redesignation candidates` reconciles exactly with the
  pre-abstention run (68, 116, 55, 12).
- **No fabricated facts** — FALSE_FACT / FALSE_SUBJECT_ATTRIBUTION /
  FALSE_LOCATOR_DECLARATION / FALSE_BINDING = 0 under the strict
  evaluator.
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
6. **Locator redesignation / renumbering continuity** — `pasa(n) a
   ser/denominarse` + structural-designator destination is a
   redesignation construct the frozen locator model cannot express
   (no old→new identity transition). The profile abstains at the
   grammar level; 6 spans journaled as `PROFILE_LIMIT_REDESIGNATION`
   in `audit.jsonl` (4 operative candidates: bulk renumbering
   "Cuatro" + clauses 21/22 in BOE-A-2011-19550, "Once. Se renumera
   la norma 11.ª" in BOE-A-2025-8206; 2 non-candidate constructs in
   sumario/bullet positions). First family with concrete
   falsifications of the current behavior (eval-dev-006 FLD ×2);
   OSS prior-art candidate `redesignated_as`/TreeDiff already
   falsified favorable in EXP-B1 — feeds the future core-gap gate.

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

## Journal summary (18 entries)

Harness/ordering (#1–#4), canonical `anejo` keying + `bis|ter|quáter`
(#5–#6), ordinal-word operative openers + `seccion` visibility (#7),
legacy stylesheet boundary adapter (#8), marked numeric ordinals (#9),
letter-spaced/legacy PDF state codes (#10–#11 with families A/CA/GA/P),
bogus `disp:transitoria.con` ordinal capture (#12), stale persist-dir
contamination (#13), evaluator finding adjudication (#14), provisional
adjudication `PROFILE_LIMIT` + reviewer checks (#15), evaluator
remediation PORT-CNMV-1R: NOT_PROVABLE default, full-locator O2,
bound-rep fidelity verification, per-relation verdict persistence,
`seccion` report correction, `.gitignore` revert (#16);
UNSUPPORTED_REDESIGNATION finding on the 2 FLD renumbering clauses
(#17); R2 redesignation abstention + probe accounting, FLD→0 on clean
rerun (#18).
