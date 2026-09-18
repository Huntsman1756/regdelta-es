# CORE-GAP — consolidated terminal adjudication

Umbrella program: remove as many of the six PROFILE_LIMIT families as
can be solved safely in the core, without sacrificing
proof-or-abstain, provenance, determinism, or prior proven behavior.

## Workstream terminals

```text
CORE-GAP
  WS-A redesignation continuity      PROVEN
  WS-B hierarchical composition      PROVEN
  WS-C anonymous structural identity ANCHORED_SUBJECT_PROVEN /
                                     HONEST_ABSTENTION_IS_CORRECT
  WS-D representation evidence       REPRESENTATION_ASSOCIATION_ONLY
```

| WS | commit(s) | terminal doc |
|---|---|---|
| A | `5cd1988` | `wsa/TERMINAL.md` |
| B | `d0919fa`, `d45dda0` | `wsb/TERMINAL.md` |
| C | `4977ad7` | `wsc/TERMINAL.md` |
| D | this commit | `wsd/TERMINAL.md`, `wsd/exp-d1/` |

## WS-D summary

EXP-D1 (pypdf 6.14.2, raw object access, no decode-for-evidence, no
rasterization, no OCR) falsified byte equality: the signed diario PDF
embeds annex figures as **vector content** — 2 shared logo XObjects
(`/CCITTFaxDecode`), 0 inline images, 0 image XObjects on annex pages,
0 byte-equal matches against 204 captured official PNGs. The
deterministic association signed-PDF-page ↔ boe-page ↔ img_alt ↔
PNG-url+sha256 is provable and is now persisted as `pdf_anchor`
binding evidence (identity unchanged, zero ledger deltas). pypdf NOT
adopted — the preregistered positive-gain condition did not hold.
ePUB avenue: `OFFICIAL_BYTES_UNAVAILABLE` (not in the frozen corpus).

## Historical replay (frozen baseline → WS-D)

```text
historical (baseline/bde-dev -> runs/wsd1/bde-dev):
  IDENTICAL        4974
  EXPECTED_DELTA    114   (all registered WS-A/WS-C cases)
  UNEXPECTED_DELTA    0
  NEW_ROWS            0
  LOST_ROWS           0

incremental (wsc2 -> wsd1):
  IDENTICAL        5016   (WS-D is evidence-only; zero churn)
  UNEXPECTED_DELTA    0

determinism:
  BdE   wsd1 == wsd2   5016 IDENTICAL
  CNMV  wsd1 == wsc2   envelope + all tables identical except
                     representations.binding_evidence += pdf_anchor
                     (the intended WS-D addition)
```

## Cross-workstream interaction coverage

`tests/coregap/test_cross_workstream.py` — 13 tests, all green:

- redesignation over deep hierarchical locators (3-level path
  preserved on both sides);
- redesignation of unnumbered class identity (no pair — destination
  cannot be anchored) and numbered class identity (edge emitted);
- positional leaf never redesignates;
- context-scoped redesignation under inherited anejo;
- declared anejo binds image pages; nested leaf and positionally
  filled anejo never image-bind;
- edge migrates IMAGE representation verbatim; unproven
  representation migrates as UNKNOWN (never resurrected);
- positional leaf cannot head a locator; resolves only inside a
  proven parent.

## Mutation/adversarial coverage

`tests/coregap/test_mutation_adversarial.py` — 24 tests, all green,
including one real boundary fix: `guion:0` no longer resolves
(`n_val >= 1` in `ownership._sub_present`, matching the guard already
present in `binding.py`). Edge refusals (cycle/self/collision/
destination-exists/unanchored), image failure modes, annex-map
tampering, scope-word adversarial values, provenance fail-closed,
emission determinism.

## Harness integrity

`tests/coregap/test_diff_runs_matcher.py` — 7 tests pinning the
vacuous-truth matcher bug found during WS-C: a `match_key_prefix` or
`match_contains` entry without `match` is not a catch-all.

## Test evidence

```text
full suite    449 passed   (402 baseline + 7 matcher + 13 cross +
                            3 WS-D + 24 mutation/adversarial)
```

## Safety ledger

```text
safety:
  FALSE_FACT                  0
  FALSE_SUBJECT_ATTRIBUTION   0
  FALSE_LOCATOR_DECLARATION   0
  FALSE_BINDING               0
  FALSE_CONTINUITY            0

holdout                     sealed (never read semantically)
OCR                         never used
LLM/vision fallback         never used
rasterization-as-identity   never used
synthetic page/image ids    none minted
```

## Result

```text
CORE-GAP = PARTIAL_PASS

A redesignation continuity       PROVEN
B hierarchical composition        PROVEN
C anonymous identity              ANCHORED_SUBJECT_PROVEN /
                                  HONEST_ABSTENTION
D image representation            REPRESENTATION_ASSOCIATION_ONLY
                                  (source limit on byte equality)

false facts                      0
false locator declarations       0
false bindings                   0
false continuity                 0
unexpected historical deltas     0
```

Three of four workstreams extended core capability within
proof-or-abstain; the fourth reached its honest source-limit terminal
and hardened provenance (explicit PDF association evidence) without
identity churn.
