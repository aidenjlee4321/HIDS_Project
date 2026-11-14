# M4 synthetic one-event pilot acceptance

Historical scoped checkpoint. The owner later approved production storage/budgets
and a bounded real-data trial; [subsequent acceptance](m4-real-data-trial.md) records
that pass. Original pending-at-that-time and synthetic-only limits below remain
preserved; none establishes unattended monitoring or supported security rules.

## Authorization and implemented scope

After reviewing the pilot walkthrough, the owner said “understood, please
continue.” This accepts the bounded M3 integration transition and the fixture-only
[M4 contract](../implementation/m4-pilot-contract.md). It does not approve live
integration, a final production schema, real security-rule coverage, a release,
commits/pushes or broader privileges. D-07 production review and subsequent D-08
security-rule/severity decisions remain open beyond this exact pilot.

Implemented: independently validate one synthetic M3-shaped event, persist it and
pending work, evaluate an immutable bounded JSON rule on only that event, then
atomically save the result and a linked demo alert when matched. Python owns all
writes. No new dependency, source read, OS collector, deployment, API or UI is added.

Files:

- `engine/detection/m4_pilot.py`: validation, pure evaluator, private prototype store.
- `rules/pilot/configured-executable.json`: opt-in informational demo definition.
- `tests/fixtures/m4/execution.json`: explicitly synthetic normalized event.
- `scripts/m4_pilot.py`: fixed-fixture demonstration in a new exclusive store.
- `scripts/m4_workflow.py`: named scope reusing the existing source verification,
  private reports, bounded subprocesses, failure summaries and timing machinery.
- `tests/unit/test_m4_pilot.py`: finite acceptance and actual SIGKILL recovery.

The first synthetic executable is `/opt/hids-fixture/probe`. Its finding says
“Configured executable matched (demo).” It asserts the configured condition only;
there is no attack label, confidence score, ATT&CK claim or remediation.

## Persistence and safety properties exercised

The envelope pins its fixture version, synthetic marker and M3 profile; canonical
source/activation/generation UUIDs and native identity scope event keys. The
existing closed M3 execution validator runs independently at receipt. Missing
required envelope/payload fields reject; explicit null auid/session preserve unknowns.
No activity timestamp is invented from processing clocks.

Rules allow one to four equality predicates on executable, uid, auid or success.
Required-field values are checked before any comparison: unknown required auid
produces `unable` even if another predicate would fail. Boolean UID values, unknown
fields/operators, rule code and revision drift reject. Evaluation is a pure function
of one event and one rule; it receives no database/history interface.

Transaction 1 stores the immutable event, immutable rule snapshot and pending
work. Transaction 2 stores the final evaluation and any alert together. Failure
leaves the committed event/pending work intact; retry uses the stored normalized
snapshot. Duplicate delivery/evaluation preserves a single event/alert. Different
scopes do not collide; same identity with different content rejects. Evaluation
errors remain explicit errors with fixed reason codes. Stored payload/rule hashes
and identifiers are checked before pending evaluation.

The prototype uses a dedicated new owner-private 0700 directory, regular single-link
0600 files, exclusive writer flock, SQLite WAL, FULL synchronous and foreign keys.
Create refuses existing directories; open checks the marked application/version
and table inventory before a writable connection. Unknown versions/foreign stores,
unsafe permissions, symlinks/hardlinks and concurrent writers reject. No automatic
migration, retention, permission repair or evidence deletion is implemented.
Same-UID/root compromise is outside this prototype's protection. These are synthetic
ordinary-user development stores; this does not broaden human access to real
security data or establish a production authentication model.

## Executed evidence

The final local run passed:

`/private/tmp/hids-m4-workflow/run-20261112T051242Z-7b22af1935c4/report.json`

- 23 pilot tests, all 87 M3 Python regressions and the demonstration passed.
- Three real child-process SIGKILL cases: after event commit, during alert insertion
  before transaction completion, and after alert commit. Reopen/integrity/retry
  preserves one committed event and exactly one final alert.
- Trigger-injected event/evaluation failures verify transaction atomicity; these
  are deliberate logical fault tests, not new physical filesystem-failure claims.
- Matching, nonmatching, unknown-required, malformed/unsupported input, exact
  duplicate, identity conflict, separate scopes, revision drift, evaluator error,
  snapshot hash conflict, private permissions and incompatible-store cases passed.

The same corrected code passed on the existing Ubuntu 26.04 AArch64 VM, Python
3.14.4, SQLite 3.46.1, as ordinary user UID 1000 with no sudo/deployment:

- Verified snapshot: `hids-src-20261112T051245Z-0ab12000c231`.
- Manifest SHA-256:
  `ef264c514d54ca6ce0bbf08decd3bc118387d3c341ae7aac4cf438a6497e1aed`.
- Workflow source-content SHA-256:
  `e1c33c9af3f5337f76a63c8d2a05bd58717dfcbfa6c099ac6a3313fceeb18985`.
- VM source:
  `/home/ivy/hids-m4-fixture.etjurv8x/hids-src-20261112T051245Z-0ab12000c231`.
- VM report:
  `/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T012019Z-b336985d9f6a/report.json`.
- All three phases passed, no skips: 23 pilot tests, 87 M3 regressions and demo;
  1.672 summed phase seconds. Snapshot inventory/hashes verified before and after.
- Independent inspection of the saved demo confirmed one event, one evaluation,
  one alert, integrity_check `ok`, empty foreign_key_check and owner-private files.
  The alert references the expected event and informational demo definition.

The first Ubuntu attempt is retained at
`/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T011847Z-6dba628dc08f/report.json`.
It exposed that Python 3.14 accepts nesting that hit an implicit recursion limit
locally. The fix adds explicit 32 KiB / depth 16 / 2048-node JSON input bounds,
instead of relying on interpreter recursion behavior. Both final runs include this
fix. No dependency or interpreter setting changed. Later documentation updates
record these results; the tested snapshot remains immutable historical evidence.

Independent privileged post-pilot inspection also matched the original Audit
configuration/plugins/rules and four original source inode/byte prefixes, all 29
installed artifacts, original configuration/512 lab budget and state permissions.
All 355 original SQLite files remain; all four M3/checker units are inactive and
Audit is active. The tested pilot code/scripts/rule/fixture were compared byte for
byte with the canonical repository after documentation edits; they are unchanged.

## Repeat the scope

From the canonical repository, as an ordinary user:

```sh
python3 -B scripts/m4_workflow.py --output /private/tmp/hids-m4-workflow
```

On Ubuntu use a canonical private output path under the invoking user's home or
`/tmp`. For a transferred source snapshot also pass `--expected-manifest DIGEST`;
use the existing `scripts/dev.py` snapshot generator and pinned transfer workflow.
This scope performs no native compile, installed deployment, live collection or
Audit configuration change. Its report does not substitute for M3 native/live
acceptance. Full logs/stores remain private outside Git.

For only the fixed demonstration, supply a new canonical directory whose parent
already exists:

```sh
python3 -B scripts/m4_pilot.py --store /private/tmp/hids-m4-demo-new
```

The demonstration refuses an existing store. The Store API's explicit open path
is exercised for recovery by the acceptance suite. A synthetic marker is a fixture
constraint, not authentication or proof of a real source event's committed origin.

## Limits and next integration review

This completes the approved fixture pilot checklist, not production M4 or v0.1.
No existing M3 database, ACK, service unit, writer ownership, installed artifact,
logging policy or collection authorization changed. No new live rule is enabled.
The next bounded step is to review a read-only handoff from actually committed M3
executions, preserving verified scope/profile/available observation metadata and
keeping failures independent of M3 ACKs. That review must settle scheduling,
provenance verification, durable progress/retry and production migration/rollback
before live hookup. Meaningful security rules need their own source evidence,
requirements, limitations and owner acceptance; the demo supplies no coverage claim.
