# COV-0 — coverage debt baseline

## sealed

journal entries: 604

| symptom kind | count |
|---|---|
| BINDING_NOT_PROVABLE | 321 |
| UNBOUND_SUBJECT | 148 |
| BINDING_NOT_FOUND | 95 |
| CHAIN_DISCONTINUITY | 34 |
| ACQUISITION_FAILURE | 2 |
| AMBIGUOUS_BINDING | 2 |
| disposicion sections present but 0 clauses | 1 |
| FETCH_ERROR | 1 |

debt by oss-recon problem:

| problem | journal entries |
|---|---|
| representation-binding-evidence | 566 |
| version-chains | 34 |
| evidence-capture (out of oss-recon scope) | 3 |
| amendment-actions | 1 |

O1 unattributed leaf ops by target:

| target | NOT_PROVABLE+AMBIGUOUS |
|---|---|
| BOE-A-2004-21845 | 104 |
| BOE-A-2008-9915 | 2 |

top unattributed modifiers:

| target \| modifier | unattributed |
|---|---|
| BOE-A-2004-21845|BOE-A-2017-14334 | 44 |
| BOE-A-2004-21845|BOE-A-2013-5720 | 25 |
| BOE-A-2004-21845|BOE-A-2013-11729 | 19 |
| BOE-A-2004-21845|BOE-A-2016-11483 | 9 |
| BOE-A-2004-21845|BOE-A-2016-4356 | 6 |
| BOE-A-2004-21845|BOE-A-2016-1238 | 1 |
| BOE-A-2008-9915|BOE-A-2016-1238 | 1 |
| BOE-A-2008-9915|BOE-A-2012-14977 | 1 |

emission: 286 relations, resolution {'UNRESOLVED': 148, 'PARTIAL': 114, 'RESOLVED': 24}
zero-relation TP ops: {'NO_SUBJECT_CANDIDATES': 88, 'O2_FAILED': 5}
binding verdicts: {'before:NO_BINDING_CLAIM': 272, 'after:NO_BINDING_CLAIM': 228, 'after:BINDING_CORRECT': 58, 'before:BINDING_CORRECT': 14}
lifecycle: {'UNKNOWN': 178, 'NOT_APPLICABLE': 57, 'PRESENT': 43, 'DELETED': 8}
audit rows: 286 verdicts {'PASS': 286}

## dev

journal entries: 807

| symptom kind | count |
|---|---|
| BINDING_NOT_PROVABLE | 465 |
| UNBOUND_SUBJECT | 231 |
| BINDING_NOT_FOUND | 75 |
| CHAIN_DISCONTINUITY | 33 |
| AMBIGUOUS_BINDING | 2 |
| ACQUISITION_FAILURE | 1 |

debt by oss-recon problem:

| problem | journal entries |
|---|---|
| representation-binding-evidence | 773 |
| version-chains | 33 |
| evidence-capture (out of oss-recon scope) | 1 |

O1 unattributed leaf ops by target:

| target | NOT_PROVABLE+AMBIGUOUS |
|---|---|
| BOE-A-2013-5720 | 34 |
| BOE-A-2011-2378 | 10 |
| BOE-A-2005-4749 | 9 |
| BOE-A-2010-12488 | 1 |
| BOE-A-2013-7467 | 1 |
| BOE-A-2014-1183 | 1 |

top unattributed modifiers:

| target \| modifier | unattributed |
|---|---|
| BOE-A-2013-5720|BOE-A-2013-11729 | 19 |
| BOE-A-2013-5720|BOE-A-2016-11483 | 9 |
| BOE-A-2005-4749|BOE-A-2012-4804 | 7 |
| BOE-A-2011-2378|BOE-A-2012-4804 | 7 |
| BOE-A-2013-5720|BOE-A-2016-4356 | 6 |
| BOE-A-2005-4749|BOE-A-2014-8654 | 1 |
| BOE-A-2005-4749|BOE-A-2013-7467 | 1 |
| BOE-A-2010-12488|BOE-A-2016-1238 | 1 |
| BOE-A-2011-2378|BOE-A-2015-13429 | 1 |
| BOE-A-2011-2378|BOE-A-2014-8654 | 1 |

emission: 520 relations, resolution {'RESOLVED': 172, 'UNRESOLVED': 231, 'PARTIAL': 117}
zero-relation TP ops: {'NO_SUBJECT_CANDIDATES': 33, 'O2_FAILED': 3}
binding verdicts: {'before:BINDING_CORRECT': 182, 'after:NO_BINDING_CLAIM': 348, 'after:BINDING_CORRECT': 172, 'before:NO_BINDING_CLAIM': 338}
lifecycle: {'PRESENT': 371, 'NOT_APPLICABLE': 75, 'UNKNOWN': 65, 'DELETED': 9}
audit rows: 520 verdicts {'PASS': 520}

