# COV-2 — DEV Representation-Binding Coverage Hardening

Base:

```text
7066fa0aa1fc60a0ac45999d354fce0c098f7318
```

Historical states remain immutable:

```text
G0-G.2 = FAIL
G1.2   = FAIL
G2.0   = STOP
G2.0b  = PASS
G2.2   = PASS

COV-0  = DONE
COV-1  = DONE
  EXP-B1 = PORT
  EXP-L1 = PATTERN_CONFIRMED
```

COV-2 is a DEV-only coverage gate.

Fresh COV-3 normative content remains semantically unopened.

---

## 1. Question

> Can RegDelta increase proven representation-binding assertions on the
> frozen CURRENT_OPERATIONAL DEV corpus from 354 to at least 443,
> using stronger official-evidence binding methods while preserving all
> G1/G2 factual-integrity invariants and without reducing the factual
> surface?

Priority:

```text
FALSE_* = 0
>
factual surface preserved
>
positive binding growth
>
chain/lifecycle coverage
```

This is not a parser-generalization gate.

This is not an ownership gate.

This is not a locator-recall gate.

---

## 2. Fixed target

Primary target stratum:

```text
CURRENT_OPERATIONAL / DEV equivalence
```

Frozen baseline:

```text
leaf operations             1266
TARGET_PROVEN                481
locator-proven ops           445
relations emitted            519

positive binding assertions  354
  before                     182
  after                      172

binding slots               1038
unclaimed slots              684
```

Required:

```text
positive_binding_assertions >= 443
```

Minimum gain:

```text
+89
+25.14% vs baseline
```

---

## 3. Anti-silence floors

COV-2 may not obtain binding growth by shrinking the factual surface.

CURRENT_OPERATIONAL DEV must finish with:

```text
relations_emitted        >= 519
locator_proven_ops       >= 445
leaf_operation_accounting = 100%
```

And:

```text
FALSE_FACT                  = 0
FALSE_BINDING               = 0
FALSE_SUBJECT_ATTRIBUTION   = 0
FALSE_LOCATOR_DECLARATION   = 0
```

per target.

Historical stratum also obeys the non-regression rules already frozen
in COV-1.

---

## 4. Exact-comparison surface

COV-2 uses exactly the same DEV corpus, raw evidence and evaluation
semantics used by the G2.2 DEV-equivalence run.

No new official raw evidence may be downloaded to improve DEV coverage.

```text
network = forbidden
evidence acquisition = frozen
```

This isolates:

```text
better use of existing evidence
```

from:

```text
more evidence acquired
```

Evidence-capture work is a separate problem class.

---

## 5. COV-2 phases

```text
COV-2A  prereg + COV-3 metadata selection/seal
COV-2B  evaluator extension + exact baseline
COV-2C  representation-binding hardening
COV-2D  final DEV audit + runtime/evaluator freeze
```

COV-3 normative content is not semantically opened in any COV-2 phase.

---

## 6. COV-3 holdout materialization before runtime changes

The COV-3 selection rule was frozen in COV-1.

Execute it before modifying `src/regdelta`.

Metadata-only discovery.

Selection:

```text
CURRENT_OPERATIONAL eligible < 3
    -> STOP

select top 3 CURRENT_OPERATIONAL

if HISTORICAL_PREDECESSOR eligible >= 1:
    select top 1 HISTORICAL_PREDECESSOR
else:
    select top 4th CURRENT_OPERATIONAL
```

Ranking within stratum remains exactly COV-1:

```text
declared_modifier_count DESC
same_date_modifier_cluster_count DESC
sha256("regdelta-cov-v1|" + boe_id) ASC
```

No semantic operation parsing for selection.

---

## 7. COV-3 capture and seal

After deterministic selection, capture content-agnostic official
artifacts using the already frozen capture policy.

Create:

```text
evidence/cov/cov3/
  selection.json
  gold/instrument_relations.json
  holdout/manifest.json
  holdout/raw/**
  holdout/SEAL
```

Gold contains only mechanically demonstrable instrument-level facts.

No per-operation labels.

No binding adjudication.

No locator adjudication.

No semantic target audit.

Commit and seal before COV-2 runtime work.

---

## 8. Semantic seen-set

Extend the semantic seen-set with every instrument semantically opened
through G2.2/COV-1.

COV-3 targets must not occur in it.

Metadata-only capture does not make them semantically seen.

```text
CAPTURED_STRUCTURALLY != SEMANTICALLY_SEEN
```

---

## 9. Baseline evaluator before runtime changes

Extend the frozen G2 evaluator only as necessary to independently
verify the new COV binding methods.

Do this before changing runtime.

Create:

```text
evidence/cov/cov2/EVALUATOR.md
scripts/cov/evaluate_cov2.py
```

Evaluator remains independent from runtime proof fields.

It rederives binding truth from official frozen evidence.

---

## 10. Baseline run

Execute the unchanged runtime from COV-1 over DEV.

Store:

```text
evidence/cov/cov2/runs/000-baseline/
```

Minimum artifacts:

```text
run.json
metrics.json
per-target.json
relations.jsonl
binding-sides.jsonl
subject-outcomes.jsonl
continuity.jsonl
ordering.jsonl
audit.jsonl
failures.jsonl
report.md
```

---

## 11. Binding-side ledger

`binding-sides.jsonl` is canonical for COV-2 coverage accounting.

One row per:

```text
modification_relation × {before, after}
```

Fields:

```text
target
stratum
modifier
semantic_relation_signature
runtime_relation_id
locator_key
side

runtime_binding_status
runtime_binding_method
runtime_candidate_count

evaluator_verdict

representation_kind
evidence_scope
abstention_reason
```

---

## 12. Semantic relation signature

Do not use `relation_id` as the sole baseline join key.

Binding improvements may change representation IDs and therefore may
change runtime relation IDs.

Use a stable comparison signature derived from legal-operation
identity, e.g.:

```text
target
modifier
operation source node/span
operation kind
locator key
normalized operative clause identity
```

The exact serialization must be frozen before runtime changes.

COV-2 does not redesign production `relation_id`.

Relation-identity redesign is out of scope.

---

## 13. Baseline equivalence

Before runtime work, reproduce COV-1/G2 baseline exactly:

CURRENT_OPERATIONAL DEV:

```text
relations                  519
locator-proven ops          445
positive binding assertions 354
```

and all frozen `FALSE_* = 0`.

If baseline cannot be reproduced:

```text
STOP COV-2
```

---

## 14. Debt census before fixes

Build:

```text
evidence/cov/cov2/debt-census.json
```

over every unclaimed CURRENT_OPERATIONAL binding side.

Taxonomy is evidence-mechanism-oriented, not target-specific.

Minimum classes:

```text
NO_STRUCTURAL_CANDIDATE
SUBJECT_SCOPE_NOT_PROVABLE
NO_OPERATION_OWNED_CONTENT
ANNEX_CODE_NOT_LOCATED
TABLE_CONTENT_NOT_ENUMERATED
ONLY_BROADER_PARENT_PROVABLE
CHAIN_STATE_UNKNOWN
CHAIN_STATE_DELETED
CHAIN_SCOPE_COLLISION
SAME_DATE_ORDER_UNPROVEN
MISSING_CAPTURED_ARTIFACT
AMBIGUOUS_MULTIPLE_CANDIDATES
OTHER
```

Every currently unclaimed relation-side must have exactly one primary
class.

No runtime change before census completion.

---

## 15. Scope boundary

COV-2 may modify mechanisms that prove:

```text
representation identity
representation structural scope
representation continuity
binding predecessor
binding ordering
```

It may not broaden O1 or O2 merely to reach the target.

Forbidden coverage strategy:

```text
parse more operations
accept weaker target attribution
accept weaker locator declarations
first-match binding
fuzzy legal-subject matching
semantic similarity
LLM extraction
OCR-generated legal identity
```

---

## 16. Allowed workstream A — table-aware structural evidence

Current BOE parsing already preserves table nodes.

COV-2 may add deterministic candidate enumeration inside tables.

Purpose:

```text
subject already identified by O1/O2
→ locate its representation in official table structure
```

Not:

```text
discover new legal subjects from arbitrary table text
```

---

## 17. Table candidate rules

A table candidate is admissible only when:

```text
1. parent structural scope is independently proven;
2. exact locator/code occurs in a structural cell;
3. candidate row/region boundaries are deterministic;
4. all candidates are enumerated;
5. candidate count == 1.
```

Outcomes:

```text
0   -> NOT_FOUND
1   -> BOUND
>1  -> AMBIGUOUS
```

Never first-match.

---

## 18. Table scope

A code occurring in:

```text
another norma
another anejo
another table
quoted replacement prose
reference/example content
```

must not satisfy the request unless that enclosing scope is proven to
belong to the requested subject.

B2 remains mandatory.

---

## 19. Representation serialization

When a table binding is proven, representation material must preserve
the exact official evidence region.

Allowed:

```text
TABLE representation
row range
table node index
cell coordinates if available
canonical serialized row/block
source snapshot
```

Do not normalize away source structure solely for easier diffing.

---

## 20. Allowed workstream B — operation-owned table after-content

An `after` binding may use a table only when the amendment operation
itself proves ownership of that replacement table/content.

G1 B3 remains unchanged:

```text
modifier-global matching is forbidden
```

Require:

```text
explicit following content
explicit annex reference
or other already-frozen operation-owned link
```

before table candidate enumeration.

---

## 21. Allowed workstream C — redesignation continuity

EXP-B1 licenses only the pairing mechanism.

No Words-to-Data code, USLM model or LLM pipeline enters RegDelta.

A redesignation edge must be source-declared and independently parsed.

Examples conceptually:

```text
X pasa a ser Y
X pasa a denominarse Y
renumbering explicitly declared by operative clause
```

---

## 22. Redesignation guards

A continuity edge is admissible only if:

```text
O1 == TARGET_PROVEN

old locator == PROVEN
new locator == PROVEN

edge is declared by the same proven operative scope

old != new
```

Additionally refuse if:

```text
both identities have independently proven simultaneous existence
```

unless official source explicitly establishes the transition.

---

## 23. Redesignation is not representation invention

Critical invariant:

```text
subject continuity != representation binding
```

A redesignation may prove:

```text
old subject identity → new subject identity
```

but must not manufacture:

```text
before representation
after representation
```

where no structural representation is proven.

It only contributes a positive binding assertion when an actual
representation can be carried through a provenance-preserving,
evaluator-verifiable predecessor relationship.

---

## 24. Redesignation ambiguity

If more than one admissible predecessor or successor exists:

```text
AMBIGUOUS
```

No pairing.

Journal it.

---

## 25. Allowed workstream D — same-date deterministic ordering

EXP-L1 licenses the ordering prior:

```text
publication/effect date
→ amending work date
→ subtype
→ natural-sorted official number
→ document position inside same work
```

Only official frozen metadata may participate.

---

## 26. No relation-id ordering

Remove `relation_id` hash as a semantic lifecycle tiebreak.

Hash ordering may remain for serialization/output determinism only.

It may never establish legal predecessor identity.

---

## 27. Same-date unresolved ties

If official metadata cannot establish order:

```text
ORDER_AMBIGUOUS
```

and no chain predecessor claim is produced from ordering alone.

Fail closed.

---

## 28. Scope compatibility before chain

EXP-L1 demonstrated same-key collisions.

Before chaining two hops sharing a `locator_key`, require compatible
subject scope.

Define deterministic:

```text
ScopeSignature
```

from already-proven structural context.

Possible components:

```text
root family
norma/disposición/anejo parent
módulo
cuadro
índice
encabezamiento
other explicitly parsed structural ancestor
```

---

## 29. ScopeSignature purpose

ScopeSignature is a chain/evidence discriminator.

It does not automatically redefine public `locator_key`.

COV-2 should not rewrite all subject IDs merely to solve chain
collisions.

Full subject-identity schema redesign is out of scope unless the
existing representation is demonstrated incapable of preserving a
correct binding.

---

## 30. Scope collision rule

Same locator string + incompatible proven scope:

```text
must NOT chain
```

Outcome:

```text
CHAIN_SCOPE_COLLISION
```

not:

```text
CHAIN_PREDECESSOR
```

---

## 31. Compatible inherited scope

Do not overcorrect.

A child locator that inherits a proven lexical parent may chain when
the same scope signature is re-established.

Fail closed only when scope cannot be proven.

---

## 32. Existing B1–B6

All G1 binding invariants remain normative.

Especially:

```text
B1 unique-or-abstain
B2 exact parent scope
B3 operation-owned after content
B4 predecessor continuity
B5 ambiguity degrades
B6 resolution follows verified binding
```

COV-2 extends candidate evidence; it does not weaken these rules.

---

## 33. O1/O2/O3 remain frozen

G2 semantics remain intact.

No coverage credit from:

```text
newly permissive ownership
newly permissive locator declaration
newly permissive lifecycle inference
```

Changes required only to qualify chain scope may refine evidence, but
must not reduce the G2 factual thresholds.

---

## 34. Positive binding definition

Unchanged:

```text
one relation × side
whose independent evaluator verdict is BINDING_CORRECT
```

Runtime `BOUND` alone does not earn coverage credit.

---

## 35. No partial credit

These do not count toward the 443 target:

```text
NOT_FOUND
NOT_PROVABLE
AMBIGUOUS
NOT_APPLICABLE
runtime BOUND but evaluator NOT_CHECKABLE
runtime BOUND contradicted by evaluator
continuity edge without representation
```

---

## 36. TDD — table binding

Minimum RED tests before implementation:

```text
exact unique code in proven table scope
  -> BOUND

same code in two admissible rows
  -> AMBIGUOUS

same code outside proven parent
  -> ignored

code only in unrelated table
  -> NOT_FOUND

table content under explicit operation-owned after span
  -> eligible

table elsewhere in modifier
  -> forbidden for after

serialized TABLE representation
  -> exact source provenance preserved
```

---

## 37. TDD — redesignation

```text
source-declared old→new + O1/O2 proven
  -> continuity candidate

O1 FOREIGN
  -> refused

old or new locator unproven
  -> refused

independent simultaneous existence
  -> refused

multiple successors
  -> AMBIGUOUS

continuity with no representation evidence
  -> no BOUND fabricated

proven predecessor representation + valid edge
  -> predecessor may propagate with explicit proof
```

---

## 38. TDD — same-date ordering

```text
official numbers resolve same-date modifier order
  -> deterministic order

same modifier work
  -> source document order

official metadata tie unresolved
  -> ORDER_AMBIGUOUS

relation_id changes
  -> semantic ordering unchanged

hash order contradicts official order
  -> official order wins
```

---

## 39. TDD — scope collision

```text
same key / same proven scope
  -> eligible chain

same key / different norma
  -> no chain

same estado code / different módulo
  -> no chain

same apartado / different cuadro
  -> no chain

scope unavailable
  -> abstain
```

---

## 40. Independent evaluator

Every new runtime binding method requires independent evaluator support
before being counted.

Evaluator may reuse frozen source parsers but may not accept:

```text
binding_proof.method == X
```

as evidence that X is correct.

It must independently enumerate/reconstruct the evidence.

---

## 41. New proof methods

Use closed method names declared before implementation.

Suggested minimum:

```text
UNIQUE_STRUCTURAL_TABLE_TARGET
OPERATION_OWNED_TABLE_CONTENT
REDESIGNATION_PREDECESSOR
SCOPE_QUALIFIED_CHAIN_PREDECESSOR
OFFICIAL_SAME_DATE_PREDECESSOR
```

Names may be adjusted during preregistration, but once COV-2 coding
starts the vocabulary is frozen.

No ad-hoc per-case method strings.

---

## 42. Binding proof completeness

Every positive runtime binding must continue to prove:

```text
requested locator
instrument
snapshot
binding method
structural scope
candidate count
all candidate summaries
chosen candidate
representation kind
node/table span
predecessor relation/representation if applicable
```

Additional continuity/order evidence where relevant.

---

## 43. Subject proof compatibility

`subject_proof` remains independent.

New binding evidence cannot alter:

```text
TARGET_PROVEN
locator PROVEN
existence_before
```

without separately satisfying G2 evaluator truth.

---

## 44. Coverage-credit ledger

Create:

```text
evidence/cov/cov2/coverage-delta.jsonl
```

One row per binding side that changes baseline outcome.

Fields:

```text
target
modifier
semantic relation signature
side

baseline status
final status

baseline method
final method

debt class
generic fix id

representation kind
proof source

evaluator verdict

coverage_credit: true|false
```

---

## 45. Fix log

Append-only:

```text
evidence/cov/cov2/fixes.jsonl
```

Each generic fix records:

```text
root cause
debt classes affected
RED tests
files changed
binding method introduced/changed

positive assertions before/after
relations before/after
locator-proven ops before/after

FALSE_* delta
B1-B6 delta

CURRENT delta
HISTORICAL delta

commit
```

---

## 46. No target-specific runtime logic

Hard:

```text
new BOE IDs in src/regdelta = 0
new specific Circular numbers = 0
new specific locator literals for corpus cases = 0
```

Fixtures/tests/evidence may contain them.

Existing anti-hardcoding guard remains active.

---

## 47. Parser/runtime versions

Only changed semantic components receive version bumps.

Expected examples:

```text
structural_binding  g1-v1 -> cov-v1
history             v4    -> v5
```

If a dedicated continuity/order module is introduced:

```text
continuity / ordering = cov-v1
```

Do not bump unrelated parsers.

---

## 48. No schema expansion by default

COV-2 should first express new proof through existing:

```text
binding_proof
subject_proof
artifact_locator
```

A DB schema change is allowed only if a specific auditability failure is
demonstrated and documented before implementation.

No convenience schema expansion.

---

## 49. Fix loop

For every runtime fix:

```text
frozen debt case
→ root cause
→ RED generic test
→ generic implementation
→ GREEN

→ targeted debt replay
→ all 16 DEV targets
→ full binding-side audit
→ G0/G1/G2 regressions
→ anti-hardcoding
→ COV-3 seal integrity
→ full suite
→ commit
```

---

## 50. Historical track

HISTORICAL_PREDECESSOR is not the COV-2 optimization target.

Report all effects.

Do not tune specifically for:

```text
BOE-A-2004-21845
```

unless the same generic mechanism is justified by the preregistered
binding evidence model.

No bespoke M/T/S-era target adapter in COV-2.

Grammar-profile portability comes later.

---

## 51. EXP-B1 limitation carried forward

EXP-B1's PORT verdict licenses the mechanism, not an expected coverage
gain.

COV-2 must report separately:

```text
redesignation edges discovered
actionable
used for subject continuity
used for positive representation binding
ambiguous/refused
```

If its representation-binding yield is zero:

```text
still valid PORT
```

No pressure to force usage.

---

## 52. EXP-L1 limitation carried forward

PATTERN_CONFIRMED licenses official ordering as a prior.

Report:

```text
same-date groups
scope-compatible
scope-collision
order-resolved
order-ambiguous
chain predecessor created
chain predecessor refused
```

COV-2 may legitimately reduce `chain_proof_coverage` if previous
hash-based chains are shown to be ungrounded.

Such removals are:

```text
COV_CORRECTION_NOT_REGRESSION
```

provided no factual positive assertion is contradicted.

---

## 53. Chain is not a PASS volume target

COV-2 does not require chain growth.

It requires:

```text
no false chain claims
official/source-grounded order
scope-compatible continuity
```

Report:

```text
CHAIN_PROVEN / declared chain hops
```

with Wilson interval where meaningful.

Do not market low-n chain results as validated precision.

---

## 54. CURRENT_OPERATIONAL final gates

Exact same-corpus DEV comparison:

```text
positive_binding_assertions >= 443

relations_emitted           >= 519
locator_proven_ops           >= 445
leaf_operation_accounting   = 100%
```

And:

```text
FALSE_FACT                  = 0
FALSE_BINDING               = 0
FALSE_SUBJECT_ATTRIBUTION   = 0
FALSE_LOCATOR_DECLARATION   = 0
```

on every CURRENT target.

---

## 55. HISTORICAL final gates

Historical stratum cannot regress on the frozen COV-1 floors:

```text
relations_emitted            >= baseline
positive_binding_assertions  >= baseline
locator-proven ops           >= baseline
leaf operation accounting    = 100%
```

unless an existing positive claim is independently demonstrated false.

Any such factual correction must be separately documented and cannot
be hidden as coverage optimization.

---

## 56. Global integrity gates

```text
B1-B6 failures                       = 0
binding_proof consistency violations = 0
subject_proof consistency violations = 0
operation inventory mismatches       = 0
subject outcome mismatches            = 0
FK failures                           = 0
query execution failures              = 0
```

---

## 57. G0/G1/G2 regressions

Hard:

```text
G0_OLD_FALSE_FACT_REPRODUCTION = 0
G1_FALSE_FACT_REPRODUCTION     = 0
G2 factual gates               = 0 failures
```

No regression of the G2.2 integrity claim.

---

## 58. Audit coverage

Final COV-2 must audit:

```text
100% emitted relations
100% runtime BOUND sides
100% newly positive binding sides
100% continuity edges used
100% same-date predecessor claims
```

---

## 59. Statistical report

For each stratum and binding side report:

```text
n positive assertions
n distinct relations
observed false bindings
Wilson 95% interval
```

Also report:

```text
before vs after
representation kind
binding method
debt class converted
```

---

## 60. Coverage attribution

The final +89 or greater must be decomposed by mechanism:

```text
table structural evidence
operation-owned table evidence
existing textual candidate improvement
redesignation predecessor
scope-qualified chain
same-date predecessor
other preregistered generic method
```

No unexplained coverage gain.

---

## 61. Baseline-to-final debt matrix

Produce:

```text
debt class
baseline count
converted to BINDING_CORRECT
still abstained
became ambiguous
became NOT_FOUND
```

per:

```text
CURRENT_OPERATIONAL
HISTORICAL_PREDECESSOR
```

This is the primary diagnostic output of COV-2.

---

## 62. Required final artifacts

```text
evidence/cov/cov2/
  PREREG.md
  protocol.md
  EVALUATOR.md

  debt-census.json

  runs/
    000-baseline/
    00N-final/

  coverage-delta.jsonl
  fixes.jsonl

  FINAL.md
  final-metrics.json
  VERDICT.json
```

---

## 63. Final report headline

Must show:

```text
CURRENT_OPERATIONAL

baseline positive bindings   354
final positive bindings      N
required                     443

delta                        N - 354

relations baseline/final
locator-proven baseline/final

FALSE_FACT
FALSE_BINDING
FALSE_SUBJECT_ATTRIBUTION
FALSE_LOCATOR_DECLARATION

before binding coverage
after binding coverage

distinct relations contributing
Wilson interval
```

Then historical results separately.

Never pool the two strata in the headline.

---

## 64. COV-2 PASS

COV-2 passes only if all are true:

```text
CURRENT positive bindings >= 443

CURRENT relations >= 519
CURRENT locator-proven ops >= 445

all leaf operations accounted

all four FALSE_* = 0 per target

historical floors satisfied

B1-B6 = 0 failures

proof consistency = 0 violations

all new positive bindings independently audited

anti-hardcoding PASS

COV-3 holdout still sealed/unopened

full suite PASS
```

---

## 65. COV-2 FAIL

If the 443 target is not achieved:

```text
COV-2 = FAIL_COVERAGE_TARGET
```

even if factual integrity remains perfect.

Do not lower 443.

Do not reinterpret the gate as “useful improvement”.

Do not tune on COV-3.

---

## 66. Integrity failure

If any `FALSE_* > 0`:

```text
COV-2 = FAIL_FACTUAL_INTEGRITY
```

even if coverage exceeds 443.

Precision remains lexicographically prior to coverage.

---

## 67. Runtime freeze

On COV-2 PASS:

freeze:

```text
COV_RUNTIME_HEAD
src_tree_sha256
parser versions
runtime-literals hash
```

No further runtime modification before COV-3 opening.

---

## 68. Evaluator freeze

Freeze separately:

```text
COV_EVALUATION_HEAD
evaluator sha256
runner sha256
metric-contract sha256
```

As in G2:

```text
runtime_head != evaluation_head
```

when appropriate.

Never conflate them.

---

## 69. COV-3 pre-open equivalence

Before opening fresh holdout, the sealed evaluator must reproduce the
final COV-2 DEV run exactly aside from declared volatile fields.

No holdout opening if equivalence fails.

---

## 70. Claim ceiling after COV-2

COV-2 alone makes no new fresh-corpus claim.

Allowed statement:

> On the frozen DEV CURRENT_OPERATIONAL corpus, RegDelta increased
> independently verified positive representation-binding assertions
> from 354 to N while preserving the preregistered factual surface and
> zero-false-claim gates.

Do not call coverage improvement generalized until COV-3.

---

## 71. Commit discipline

Recommended sequence:

```text
docs: preregister COV-2 binding coverage hardening

chore: seal COV-3 holdout
test: freeze COV-2 evaluator and baseline

fix/feat: generic binding evidence commits
  one root cause / mechanism per commit where practical

test: freeze COV-2 DEV coverage result
```

No squash.

No amend across the baseline/final evidence boundary.

---

## 72. Terminal state

Return only one:

```text
READY_FOR_COV_3_PREOPEN
```

or:

```text
NOT_READY_FOR_COV_3
```

Do not open COV-3 in the same execution.

---

## 73. Deliverable

Return:

1. base HEAD;
2. COV-3 selected targets and strata;
3. COV-3 SEAL hashes;
4. semantic seen-set hash;
5. baseline HEAD;
6. baseline src tree;
7. evaluator HEAD/hash;
8. debt census;
9. baseline CURRENT metrics;
10. baseline HIST metrics;
11. generic fixes;
12. RED→GREEN evidence;
13. table-binding methods added;
14. redesignation edges discovered/used/refused;
15. same-date groups resolved/refused;
16. scope collisions identified;
17. scope collisions prevented from chaining;
18. final positive bindings CURRENT;
19. required 443 target;
20. positive binding delta;
21. before/after binding distribution;
22. distinct contributing relations;
23. Wilson interval;
24. relations baseline→final;
25. locator-proven ops baseline→final;
26. leaf-operation accounting;
27. historical metrics baseline→final;
28. debt matrix;
29. mechanism attribution of coverage gain;
30. FALSE_FACT;
31. FALSE_BINDING;
32. FALSE_SUBJECT_ATTRIBUTION;
33. FALSE_LOCATOR_DECLARATION;
34. B1–B6;
35. binding_proof consistency;
36. subject_proof consistency;
37. G0/G1/G2 regressions;
38. applicability;
39. query execution;
40. anti-hardcoding;
41. COV-3 holdout integrity;
42. runtime HEAD;
43. evaluation HEAD;
44. src_tree_sha256;
45. full suite;
46. git status;
47. READY / NOT_READY.

No COV-3 semantic opening.
