# metalex-cwa-15710

## 1. Source freeze

- spec: CWA 15710:2010 "MetaLex — Open XML Interchange Format for
  Legal and Legislative Resources" (CEN Workshop Agreement)
- review date: 2026-09-19 (CORE-GAP recon)
- license: CEN workshop agreement text, freely distributed spec
- companion: "MetaLex naming conventions and the semantic web"
  (dare.uva.nl)

## 2. Problem fit

- `problems/stable-node-identity.md` — primary

Component: `metalex:LocalNamingConventionMethod` enumerated choice —
`individual` (assigned identifier/name), `ordinal` (declared ordinal
number), `positional` (position within a LocalNamingConventionScope).
Identity significance attaches only to what the naming convention
declares; the method is part of the identifier's metadata.

## 3. Evidence-rule compatibility

| question | answer |
|---|---|
| official source bytes | NO (markup standard) |
| exact structural span | YES |
| deterministic | YES |
| ambiguity unresolved | YES (method enum is honest about it) |
| fail closed | YES (a convention may simply not declare an element) |
| synthetic consolidation | NO |
| normalized content | YES (as pattern, no) |
| original preserved | YES |
| temporal provenance | YES (W/E/M versioning) |

## 4. Verdict

**PATTERN** — the decisive prior art for anonymous structural
identity: `positional` is a *declared method*, distinct from
`individual`/`ordinal`. A positional locator can never masquerade as a
source-declared one because the method travels with the identifier.
Maps onto RegDelta as a provenance class on the locator (e.g. a
`POSITIONAL_DERIVED` component provenance or a distinct kind token),
not a new canonical spelling.

## 5. Falsification experiment (if ever adopted as mechanism)

Annotate frozen `anejo:N`/`disp:*` emissions and annexmap positional
fills with a method field; replay G2.2 ledger — PASS iff zero
adjudicated binding changes and every positional key traces to a
journaled derivation; FAIL if any positional-method key was consumed
where a declared identity was required.
