# First-run D-14a design evidence

Status: proposed policy tested with a synthetic in-memory model; **no production
setup/control implementation or new collection authorization**. See the
[concrete owner review](../implementation/first-run-control-review.md).

## What was completed

- Reconciled accepted root/sudo/D-12c history authority with the still-open D-14
  first-run gate, M3 root controls, source-research limits and product requirements.
- Prepared the remembered-choice/fresh-activation/root-CLI-control recommendation,
  including bounded setup draft scope, safe persistence, stale/replay handling,
  empty/subset behavior, uncertain cleanup and initial stop-before-edit policy.
- Added `tests/unit/test_first_run_design.py`: a test-only model, not imported by
  production. Thirty cases pass on macOS and Ubuntu using synthetic callbacks.
  It performs no source, socket, database or application-state file operations.
- Collected recognized VM source/service/config metadata and independently checked
  the authorized production preservation baseline. No source was initialized,
  subscribed, sampled, repaired or granted extra permissions. No normal-browser,
  TLS, OS logging, package or Mac system change was made.

## Executed synthetic scope

Verified source snapshot `hids-src-20261113T104619Z-1ff331297705`, manifest
`399ddbc86ea426ae462417800f53fdce2b44077fbfc5920679232308c2d97c45`.
The ordinary-user Ubuntu workflow passed one named `first_run_design` phase:
30 tests, exit zero, no skips, source verified before/after.

Private report:
`/home/ivy/hids-browser-compare.9z_gnv_e/first-run-design-checks/run-20261113T044747Z-b61a16a229d3/report.json`.

The model tests root-role simulations; choice vs activation separation; empty and
recognized subsets; unknown/duplicate/path/command rejection; stale configuration/
assessment revisions; single-use/expiry/forgery/restart invalidation; partial clean
and uncertain initialization failure; initialization vs scoped delivery; confirmed
stop and uncertain stop; active-edit refusal; no automatic retry or consent expansion;
and clock failure. Its JSON-shaped in-memory state is not an approved production
storage/wire schema. Simulated roles and callbacks do not prove SO_PEERCRED, real
cleanup, filesystem durability, HTTP scope enforcement or source operation.

Production API/backend/native/frontend/packaging behavior was not changed. The
previous [history acceptance](m4-history-view-acceptance.md) remains its earlier
executed scope; a fresh full M3/M4/browser run is not claimed or needed for this
model/documentation-only change. Before production setup work, the owner must decide
D-14a; implementation then needs the real boundary/fault/namespace/browser gates
listed in that packet.

## Current lab metadata and preservation

Linux 2's pinned UUID was checked. Current kernel is `7.0.0-43-generic`, AArch64.
Audit is active; all four M3 service/socket/health/timer units are inactive. M2
service units are not installed. Relevant service accounts exist without observed
supplementary groups; this does not establish actual file ACL access. Journal
paths, connector headers and both kernel build options exist; these are metadata,
not live delivery/field or production-identity evidence.

Private inventory:
`/var/tmp/hids-first-run-preflight.qwfhwl2o/report.json`,
`installed-metadata.json`, and `scope-notes.json`.
All 29 installed artifacts match the original hashes. The installed reader binary
is `hids-audit-plugin`; an absent guessed `hids-audit-reader` pathname is not lost
software. Current plugin config basenames are `af_unix.conf`, `filter.conf`,
`syslog.conf`; no configuration was changed. Do not infer source usability from a
filename or auto-repair logging as part of first-run discovery.

The metadata inventory does not sample event values. **Separate lab preservation**
reads/hashes previously authorized Audit source-prefix bytes and HIDS state/artifacts.
The initial private report's phrase “no event log read” was too broad for that
combined lab operation; `scope-notes.json` preserves the correction. Product
preflight must never call that preservation helper or read logs to discover fields.
No raw payload examples were retained or exposed. Original DB/WAL/backups, artifacts,
source prefixes, Audit policy and unit state match the established baseline; all
357 M3 databases remain. No state recreation, deletion, commit or push occurred.


## Final preservation guard result

The final call to the historical lab `preserved()` helper refused at its assertion
that each original source **pathname** still has its old inode. A separate read-only
diagnostic found all four original inodes at the next rotated names (`audit.log`
through `.3` became `.1` through `.4`); every original authorized prefix hash
matches. Every protected baseline file, Audit rule set, Audit active state and M3
unit state also matches. Private report:
`/var/tmp/hids-first-run-preflight.qwfhwl2o/preservation-diagnostic.json`.

Thus the old helper did **not** pass this final invocation, and no new all-green
acceptance report is claimed. The diagnostic establishes the narrower content/
inode-preservation result across changed filenames. No explicit rotation command,
log copying, source deletion, baseline rewrite or guard change was performed.
The original-path guard remains unchanged and will block a later privileged lab
run; any adaptation must preserve the exact original inode and prefix-hash checks
and be reviewed/tested separately. This is independent of the still-unapproved
D-14a production consent/control policy. No further source or control work followed.


## Subsequent owner approval and implementation

The owner accepted the recommended consent/control policy in the next continuation.
[Bounded implementation/acceptance](first-run-acceptance.md) now records working
setup/draft/root-terminal behavior. The historical design-only results above remain
their original scope. The rotation-aware lab guard was subsequently reviewed,
implemented and tested: renamed originals still require their exact original inode
and recorded prefix hash. All protected production checks passed under that guard;
no logs were copied/deleted and the baseline was not rewritten.
