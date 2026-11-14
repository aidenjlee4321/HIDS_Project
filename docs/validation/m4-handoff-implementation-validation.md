# M4 handoff implementation: synthetic acceptance

Historical scoped checkpoint. The owner later approved production storage/budgets
and a bounded real-data trial; [subsequent acceptance](m4-real-data-trial.md) records
that pass. Original pending-at-that-time and synthetic-only limits below remain
preserved; none establishes unattended monitoring or supported security rules.

## Approval and scope

After the concrete handoff proposal, the owner said “good work, let's continue.”
This accepts implementing/testing the independent read-only worker, separate
protected destination, explicit source binding and frontier-safe sweep with
synthetic data. It preserves the earlier pilot approvals. Exact production DDL,
operational budgets, live activation and meaningful security rules retain their
review gates. No real-data entry point or production unit is installed/enabled.

Implemented files:

- `engine/detection/m4_handoff.py`: selected-source reader, durable independent
  SQLite destination, immutable event/rule snapshots, evaluation and fair bounded scheduler.
- `engine/detection/m4_handoff_worker.py`: root-configured backend-identity lab
  entry point; refuses non-lab configuration and requires actual isolation probes.
- `tests/unit/test_m4_handoff.py`: 19 implementation acceptance tests.
- `tests/integration/m4_handoff_ubuntu.py`: explicit root-only transient systemd
  sandbox test, synthetic M3 producer and retained protected evidence.

M3 ingestion, native reader, ACKs, schema, installed code and original policies are
unchanged. The existing fixture-only API still requires its synthetic envelope;
the handoff has a separate envelope/store/application id and no fixture migration.

## Source and persistence behavior exercised

The reader verifies private canonical files, existing WAL/SHM, exact control v4
and pinned ledger schema, selected source/activation/generation, accepted/EOE/
position witnesses, immutable native identity, metadata and independently validated
execution. Missing sidecars fail without creating source files. Source connections
use mode=ro/query_only, short read transactions and an interruptible statement
budget; progress handlers are disabled before unconditional connection cleanup.
No immutable mode, source writer lock, source migration, lease token or raw Audit
read is used. The lab entry restricts inputs to explicitly created isolated lab
paths; the library refuses the production `/var/lib/hids/m3` path.

Import commits event snapshots, optional immutable lab-rule work and sweep state
atomically in the destination. A later A behind B's page marker is found on a new
sweep; only the frontier captured at sweep start can become settled. State survives
worker restarts. Event/content/revision conflicts refuse without overwriting
history. No enabled rule means explicit unevaluated events, not a clean result.
Unknown source profile produces unable, not no_match. Evaluation and a possible
alert commit together, independently of M3. The pure rule evaluator remains the
one-event predicate function from the approved pilot.

The destination has a distinct application id/version and exact DDL checks,
private 0700/0600 files, exclusive writer, WAL/FULL synchronous, foreign keys,
explicit page limits and the existing bounded storage-admission machinery. No
new dependency, automatic retention/deletion, source discovery or collection
activation is added. This is application admission plus a SQLite page cap, not a
hard filesystem quota or complete physical-resource isolation.

## Executed tests

All 49 M4 tests passed locally: 23 original pilot + 7 ordering design + 19 handoff
implementation. Only the focused M4 suite was run locally in this step; the Mac
remains low on space. Full M3 regression was deliberately verified on Ubuntu.

The new 19 cases cover source/metadata preservation, B-before-A across destination
reopen, disabled rules, unknown profile, missing metadata, rejected/interrupted
input, wrong source/generation/schema, missing sidecars, frontier regression,
immutable conflict, import/progress and alert rollback, per-binding failure,
exclusive/unknown-version/live refusal, actual destination SQLITE_FULL and four
actual child SIGKILL boundaries (during import, after import commit, during alert,
after alert commit). The page-cap test receives actual SQLite FULL (13 on Ubuntu),
preserves prior events/cursor and passes integrity_check. It is not a simulated
block-device/full-filesystem fault. Source main/WAL hashes remain unchanged during
an idle-writer handoff test. Existing M3 native tests are not rerun or claimed by
this Python-only scope.

Final unit/workflow Ubuntu evidence:

- Snapshot `hids-src-20261112T054135Z-74f9a0d44212`.
- Manifest SHA-256:
  `b3f6f050697f02fcc7a0acceb2362a2d9b0223d4d9db6ef56186b49bd1b6098d`.
- Report:
  `/home/ivy/hids-m4-fixture.etjurv8x/results/run-20261112T015147Z-13bc787a2415/report.json`.
- Passed all 49 M4 tests, all 87 M3 Python regressions and demo; no skips,
  1.922 summed phase seconds. Ordinary user `ivy`; verified snapshot before/after.

The actual backend-identity/read-only sandbox passed separately:

- Final harness snapshot `hids-src-20261112T054413Z-e2287d240472`.
- Manifest SHA-256:
  `00d17084c25e9dcfe292138c053ae69aff8c4e07c212a8ce484dab33e47f807b`.
- Protected report `/var/tmp/hids-m4-handoff.r1ddp_fm/report.json`.
- Four transient worker starts under NSS-resolved `hids-ingest` UID/GID 994,
  with no supplementary IPC group/capabilities; strict system filesystem protection,
  source read-only mount, writable private destination and hidden original M3 state/sockets.
- Source OS write-open returns EROFS; SQL write receives SQLITE_READONLY; access
  to original M3 state/socket directories is denied. Actual committed WAL data is
  readable in that sandbox. The synthetic producer runs separately as the same
  service identity and retains the real M3 writer role.
- The four starts preserve event counts `[1, 1, 2, 2]`: B is imported, late A is
  committed behind the cursor, the old sweep closes safely, and the next finds A.
  Both are explicitly unevaluated; all four alert counts are zero. Demo rules
  are disabled in the worker. No threat finding is claimed.
- Private producer/source/config/destination/logs remain outside Git. Transient
  units were collected and the synthetic producer exited. Final sandbox source
  inventory/hashes were independently reverified.

Two earlier sandbox-harness attempts were retained: directory/name verification
failed before producer startup (`/var/tmp/hids-m4-handoff.81koh100/report.json`),
then the launcher lacked its repository import path
(`/var/tmp/hids-m4-handoff.wfms6bei/report.json`). The first historical report remains
`running` because that harness had not yet finalized failure status; its command
exited 1 and it is not a passing/running acceptance job. The second is marked failed.
Both are harness defects corrected before the final pass. No installed HIDS state
or source policy was changed by either. The worker/core/test source was byte-compared
with the passing unit snapshot; only harness fixes changed the later snapshot.

Independent final privileged verification matched original Audit policy/plugins/
rules, all four original source inode/byte prefixes, all 29 installed hashes,
original configuration/512 lab budget and protected state modes. All 355 original
SQLite files remain. Audit is active; all four M3/checker units are inactive and
no transient handoff units remain. No original history was removed.

## Repeat safely

As an ordinary user in the repository or verified snapshot:

```sh
python3 -B scripts/m4_workflow.py --output /tmp/hids-m4-workflow
```

On the authorized Ubuntu VM, from a verified source snapshot, separately opt into
the sandbox experiment:

```sh
sudo python3 -B tests/integration/m4_handoff_ubuntu.py --expected-manifest DIGEST
```

It requires original M3 units already inactive and Audit already active, takes
the existing lab workflow lock, retains artifacts and uses only new synthetic
state. It creates transient lab services; it installs no production service and
changes no Audit rule/plugin/PAM/journal setting. Full logs remain private. On
Mac use `/private/tmp` and prefer focused M4 tests while the volume is below the
existing M3 admission guard; do not weaken that guard.

## Remaining gates

This proves the selected synthetic adapter/sandbox paths, not supported live M4.
Production configuration/entry point, exact real-data DDL/version/migration review,
root-approved live activation selection, operational budgets and supported security
rules remain gated. The tested DDL is now concrete in `m4_handoff.py`; lab budget
values are explicit test settings, not approved unattended/release thresholds.

Read-only sealed ledgers without existing usable sidecars report unavailable;
no fallback is implemented. Broader file-replacement races, busy/slow source
contention, destination read-only/real physical quota/device faults, sustained
fairness/resource measurements, status persistence across worker failure and
complete unattended supervision/retention remain unproven. Shared UID/root
compromise and shared CPU/disk interference are not prevented by this direct-path
sandbox proof. Preserve D-09/D-10/D-13/D-15 and source/API consent/auth boundaries.
