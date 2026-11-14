# Documentation consistency review — November 11, 2026

## Review scope and result

The quick audit inventoried and scanned all 54 first-party Markdown files then
present across repository guidance, architecture/ADRs, implementation plans,
research, schemas, validation, collector/test/workflow readmes and backlog. It
checked status/authority statements and local file/heading references, with targeted
review against the current implementation, owner approvals and recorded test results.
The new review packet and this record are included in the final link scan.

Current summaries now distinguish:

- Owner-reported M1/M2 acceptance and their preserved earlier preparation results.
- M3's accepted plugin/EOE integration closeout and scoped physical storage,
  quota, health, native/rotation/recovery evidence; broader release gates stay open.
- Implemented synthetic M4 rule/alert/handoff and actual backend sandbox evidence,
  with no enabled real-data entry, supported security-rule coverage or finished UI.
- Current accepted decisions versus dated/superseded RAW-file design history and
  still-proposed production schema/budgets/live activation.

## Corrections

Updated repository guidance, the documentation index, architecture status/Audit
section/roadmap, threat-model implementation context, release scope, readiness-plan
inventory and milestone context, current handoff and backlog. Removed stale current
claims that only M1 exists, journald work is wholly planned, M3 reads RAW files,
all detection work is unimplemented, or implementation remains documentation-only.
Recorded selected real quota evidence without declaring all quota/VFS cases proved.

Historical M1/M2 preparation/validation and ordering-design records now have clear
later-status pointers. Original results, pending-at-that-time claims, dated counts,
owner-report limitations and accepted ADR reasoning remain preserved. The process
collector readme now explicitly scopes its unvalidated cn_proc runtime separately
from implemented Audit code. The M1 integration readme links M2/M3/M4 scopes.
No broad release criterion was checked merely because a fixture test passed.

All local Markdown file and heading links resolved in the final scan. Source and
DDL references were compared with current files. The concrete proposed storage
settings pass the existing storage-policy validator; the Ubuntu free-space
observation is recorded as an observation and must be checked again before use.

This is a repository consistency review, not new execution evidence or a fresh
external-source research audit. Dated research/validation remains evidence for its
recorded scope; its explicit unknowns are not promoted to current verified facts.
No application source, tests, dependencies, host settings, Git history or production
state changed for this documentation pass. Existing uncommitted implementation
work remains; no commit/push was performed.

## Continued work

Prepared the concrete [production storage/trial review packet](../implementation/m4-production-review.md)
from the tested five-table DDL and existing storage-admission rules. It makes the
next D-07/D-09 decision reviewable: an additional protected local event copy,
separate live store/version, explicit source selection, conservative trial budgets,
no enabled rules, no automatic retention/deletion and bounded VM acceptance.
It remains proposed until the owner accepts it; earlier synthetic architecture
approval is preserved rather than broadened into real-data authorization.
