# CORE-GAP — hardening/public-release integration report

Branch: `release/core-gap-hardening`
Merge: `hardening/public-release` (6 commits, packaging/CI/docs +
runtime hardening) into CORE-GAP tip (`b60e628`).

## Merge resolution

One content conflict, resolved without rewriting frozen evidence:

| file | resolution |
|---|---|
| `tests/g0g/test_holdout_sealed.py` | adopted the hardening version (`_OTHER_GATE_SEALERS` refinement, `as_posix` normalization) and added `scripts/core-gap/census.py` to `_OTHER_GATE_SEALERS` — the census uses the generic word "holdout" only as a mechanical exclusion filter and never references `g0g/holdout` |

`src/regdelta/db.py` auto-merged cleanly: the hardened
`_rebuild_table` (transaction guard, post_sql inside the transaction,
foreign-key restore) coexists with the WS-C `subject_kind` CHECK
migration (`PARRAFO`, `GUION`).

No frozen evidence was modified: the merge touches code, docs,
packaging, and tests only.

## Post-integration verification

| check | result |
|---|---|
| `ruff check src tests scripts` | clean |
| `mypy` (typed surface) | clean, 3 files |
| full test suite | **686 passed** (449 CORE-GAP + 237 hardening) |
| `tests/g0g/test_holdout_sealed.py` | seal integrity + access rule pass |
| post-merge BdE replay vs `wsd1` | **5016 IDENTICAL**, 0 deltas — the merge is semantically transparent to reconstruction |
| `uv build` | `regdelta-0.3.0a0` wheel + sdist built |
| `scripts/check_distribution.py` | passed — wheel/sdist contain only `regdelta` + docs; evidence excluded |
| `uv lock --check` | resolved, consistent |
| license | Apache-2.0 (`LICENSE` + `pyproject.license`) |
| `SECURITY.md` | present (GitHub private reporting channel named) |
| secret scan on changed files | only benign hits (captured public BOE artifacts, prose) |
| hosted CI | `.github/workflows/checks.yml` configured (push/PR/dispatch; ubuntu+windows × py3.11/3.13); not executed — branch not pushed; every CI step verified locally (ruff, mypy, `scripts/check.py` → pytest, `uv build`, `check_distribution`) |

## Safety ledger (unchanged by integration)

```text
FALSE_FACT                  0
FALSE_SUBJECT_ATTRIBUTION   0
FALSE_LOCATOR_DECLARATION   0
FALSE_BINDING               0
FALSE_CONTINUITY            0
holdout                     sealed
unexpected deltas           0
```
