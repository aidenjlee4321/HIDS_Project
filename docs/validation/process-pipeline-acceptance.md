# Approved process pipeline: installed Ubuntu evidence

November 13, 2026. The [C-01–04 contract](../implementation/process-live-pipeline-review.md)
is owner-approved. The bounded installed owned-child pipeline passed. This is a
functional source→normalization→IPC→private-storage slice, not a complete installable
HIDS, supported detection catalog, general reliability result or release sign-off.

## Implemented boundary

C++ copies native fork/exec/exit records and observation clock samples into 256
fixed slots. No callback allocation, JSON, socket write or DB access. Outside the
callback it generates opaque UUIDv4 IDs with OS randomness, normalizes the approved
ECS-based subset, validates outgoing representations and sends bounded JSON Lines
over one private Unix stream. Python independently validates scope, types, native/
normalized equality, IDs and clock roles, then owns all SQLite writes. Commit
precedes success ACK. This is a new closed `process.lifecycle/0.1.0` contract;
M1's fixture contract and M3/M4 schemas/history remain unchanged.

Files: `collector/include/hids/process/`, `collector/src/process/`,
`engine/ingestion/process_contract.py`, `process_receiver.py`, `process_backend.py`,
`process_control.py`, and `engine/database/process_store.py`. The fixed root setup
coordinator has the process adapter; preflight remains metadata-only and never
subscribes or samples payloads. Unknown or missing installed artifacts block the
source. Exact old saved catalog hashes remain readable; immutable old revisions
are not rewritten and no choices automatically activate after an upgrade/restart.

The new store is `/var/lib/hids/process/store.sqlite`, owned by `hids-ingest` with
0700 directory/0600 files, WAL, exact version/application ID/schema checks and
independent storage order. It retains validated native metadata and the normalized
subset, not raw datagrams, executable names, arguments/environment or user identity.
The monotonic timestamp stays a lossless decimal string; activity wall time is
null. Observation and receipt UTC are separate, with no clock-order assumption.

Engineering bounds: 16 KiB event/1 KiB response, 256 pending native slots, one frozen
outbound frame, 10,000 events, 64 MiB combined accounted store/WAL/SHM/temporary
outputs, a conservative complete-DB write reserve and 256 MiB filesystem free
reserve. A separate 4096-page/16 MiB DB cap can refuse earlier. No automatic
expiry/deletion. Admission or SQLite FULL/readonly/lock failures stop the affected
source with honest incomplete/failure state; prior history is preserved. These
are prototype containment choices, not measured release performance thresholds.

## Actual service identities and safer startup correction

The first installed attempt failed **before collector launch**: setpriv's setresuid
was refused under the target root unit's RestrictSUIDSGID setting. Backend exit was
127, collector exit absent and the new store still empty. Automatic approval review
rejected a proposed disabling of that control. It was never disabled.

The implemented alternative uses four manual units: root
`hids-process-runtime.service`, `hids-process-collector.service`,
`hids-process-backend.service` and `hids-process-backend.socket`.
PID 1 changes the fixed service identity before applying each service's filters.
All three services retain `RestrictSUIDSGID=yes` and `NoNewPrivileges=yes`. The root
coordinator is reduced to CAP_CHOWN and Unix sockets; it manages application files,
the root activation lease and child units, not source collection or SQLite writes.
Collector is `hids-process`; backend is `hids-ingest`. Both have all five capability
sets empty. There are no supplementary group grants. systemd/NSS repeats each
role's own primary GID in its group vector; both entry points allow that redundant
primary value only and refuse any other group. This grants no additional group
access. Actual non-collecting service probes verified the identities/capabilities.

The private data listener is created by PID 1. The collector checks its root peer;
the backend independently checks the collector UID. A second root-held Unix lease
checks the exact collector MainPID/UID and delivers the current source/activation.
The collector verifies its root peer and current scope before opening cn_proc.
Lease closure requests stop; no automatic reconnect/root fallback. A one-use
30-second root activation file is consumed before source setup. Manual unit start
alone cannot recreate that authority. Volatile metadata directories are recreated
by app-specific tmpfiles rules without grants, subscriptions or restored ownership.

The startup controller waits for a fresh matching status after an old terminal
status, and refuses an unrelated active scope. Stop is scoped to owned IDs and
checks the separate units. Native ACK, delivery and incompleteness are independent;
bounded typed diagnostic counters do not reinterpret CPU sequence gaps as lost
record counts. IGNORE-send/socket-close success still does not confirm unsubscribe
completion.

## Executed target evidence

Ubuntu 26.04 AArch64, kernel `7.0.0-43-generic`, GCC 15.2.0. No dependencies were
installed. The named `scripts/process_workflow.py` verifies immutable snapshots,
keeps full private logs and performs strict C++20 builds with
`-Wall -Wextra -Wpedantic -Werror`, native boundary/queue checks, actual synthetic
native packet→C++ parser/normalizer/runtime→Unix socket→Python→SQLite tests and
42 independent cross-language positive/negative cases. It needs the existing
approved test venv for the HTTP/setup regressions; system Python lacks FastAPI.

Settled separate-service snapshot: `hids-src-20261113T162158Z-5871e06102c8`,
manifest `2a000d583f8b70479aba646a20bc3e0617af772412a997f0c56999e5d1a9c398`.
Its 17 offline phases passed: 79 Python tests, native checks and 42 cross-language
cases, no skips. Private report:
`/home/ivy/hids-browser-compare.9z_gnv_e/process-pipeline-checks/run-20261113T103414Z-0fdd590ba2b9/report.json`.
A separately tested controller status-race correction was installed before live
acceptance; its SHA-256 was
`5dd4c08e38146d4434751b1f96e6c2ea1a35d02b577f44c14422fe33a7571bdc`.

Actual tested production collector SHA-256:
`e5afaa5b01e38fa9d3768f96996ad5ca5c6fcdffae3073d331677147c7c11639`.
The separate owned-child acceptance binary SHA-256:
`0bd5dd685eb616b8ce0d49e29e7f9b45563d82f7852d3ab43fdd6134cb50ec26`.
It shares production runtime/parser/normalizer/transport, but is compiled with an
owned-child filter/fixture entry. It does not prove unfiltered sustained runtime.
A private previous-package backup remains at `/opt/hids-process-upgrade.fgyqgn5u`.
The temporary collector-only drop-in was removed after acceptance. No restriction
was removed and the installed production executable was not substituted.

## Installed live acceptance

Private final report: `/opt/hids-process-integration.dhdn5j3o/report.json`.
Actual root setup manager confirmation saved the process choice, staged one fresh
grant and started the separately restricted services. Exactly one owned sleep
child supplied actual fork/exec/exit; C++ normalized them and Python validated and
persisted all three. The stored interval has ACK=false, delivery=true,
incomplete=false, stopped=true; activity wall time remains absent. Source IDs,
PID/TGID and payloads remain private on the VM. No native report was exported.

Root scoped stop passed. The manager returned preferences to empty at revision 6;
all six immutable revisions remain. Prior revisions were hash checked unchanged.
A production-unit start without a new grant was refused before collection and
its failed unit state was reset without erasing failed runtime evidence. No source
or listener remains running. Earlier incomplete test directory
`/opt/hids-process-integration.dhbl4uaa` is retained; that startup failed before a
collector existed. No successful source experiment was repeated as routine testing.

Real isolated fault report `/opt/hids-process-faults.u89nsl6z/report.json` records
SIGKILL before/after commit (zero/one retained event respectively), genuine SQLite
FULL and read-only mount refusal. The read-only WAL path may reject at open with
SQLITE_CANTOPEN, rather than reach a write returning SQLITE_READONLY. Private mount
namespaces and synthetic fixtures were used; production admission was bypassed
only inside the isolated VFS fault fixture. Admission itself has separate tests.
No host filesystem/logging policy changed.

## Interruption recovery and independent preservation

The connection was interrupted after the installed trial completed. The VM was
subsequently found stopped, unlocked and started using existing authorization;
collection was not rerun. The persisted successful report was recovered. A new
DB-owner read checked integrity and the same three rows after boot. Saved choices
remain empty at revision 6 and no volatile grant survived. All four process units
and M3 units were inactive; Audit was active.

The lab preservation guard again matched the original dashboard acceptance
baseline: all 357 M3 databases, prior M4 database/backup/configuration hashes,
installed artifacts, Audit rules/service state and original source inode prefixes.
This lab guard reads previously authorized historical Audit prefixes and is never
a product metadata preflight. No old history/log was recreated, copied or deleted.
Aggregate proof: `/opt/hids-process-integration.dhdn5j3o/post-restart-preservation.json`.

SSH was restored using a public key read directly in the trusted VM console:
Linux 2 UUID `46330e53-4a53-4a94-b9d4-0adefd192ab7`, ed25519 fingerprint
`SHA256:DDlsEthQ0vFC2U4AnH9Fp6lQQZTpHV0z4TeEgbidIyg`.
A temporary known-hosts file enforces strict matching; no Mac SSH settings or
persistent credentials changed. Do not accept a different key by disabling checks.

## Remaining boundary

Subsequent focused corrections add read-only resolution after a confirmed COMMIT,
explicit cleanup-deadline failure reporting and boot-time metadata directories.
They passed the final offline checkpoint and stopped component update below;
no repeat of live collection was needed for these failure/packaging paths.

No process data HTTP route, Activity UI, new rule, enrichment, journal access,
certificate lifecycle, distribution package or complete clean-install acceptance
is delivered by this trial. The next reserved decision is the protected presentation
surface and packaging/access lifecycle, now that real data can exercise it. The
first installable build remains the next product stopping point; reassess before
extras. Whole v0.1/release requirements are not silently closed.


## Final failure and stopped-update checkpoint

Verified source `hids-src-20261113T184930Z-524c72b33bb8`, 376 files,
manifest SHA-256 `4a5c0340eeb95e45a2c712d0dca8d75eb0b848a59c1fd77ca0ad74fc0ed2e5bd`.
All 17 workflow phases passed: 83 Python tests, native checks, complete production
linking and 42 cross-language cases. Private report:
`/home/ivy/hids-browser-compare.9z_gnv_e/process-pipeline-checks/run-20261113T185002Z-4810b1d8d3bd/report.json`.
The production and owned-child binary hashes above are unchanged.

Stopped component update backup and proof:
`/opt/hids-process-upgrade.m20yyepv/stopped-final-verification.json`.
All checks passed: boot metadata directories recreated without restoring authority,
actual backend readiness and zero capabilities, unrelated HIDS paths inaccessible
inside its mount namespace, unchanged database bytes, no-grant start refused, and
all source units inactive. The socket-only check used an unauthorized root client;
no event/status was inserted and no native source opened. Saved choices remain
empty, revision 6; three stored process events remain. Old-state preservation passed.

P-01–P-04 subsequently received owner continuation authorization; the dashboard
review records the exact scope. This core checkpoint does not claim that later
presentation or installation work has passed.
