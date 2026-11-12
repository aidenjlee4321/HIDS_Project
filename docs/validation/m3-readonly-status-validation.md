# M3 root status on a read-only state filesystem

## Behavior and preserved boundaries

The published bounded-filesystem checkpoint `bfb4592` found that cold startup on
read-only state failed before root control became available. The continuation
keeps metadata status available while preventing collection and all database writes.

The existing statvfs inspection now detects its read-only mount flag and reports
admission exhausted with reason `filesystem_read_only`, retaining the actually
observed free-byte count. Numeric reserve defaults, WAL/page/state budgets and
retention are unchanged. The additional reason is accepted by the matched root
control client; it is not a new final event schema or source protocol.

For existing private state, Runtime opens the existing writer lock read-only and
still takes an exclusive nonblocking flock. It creates neither a missing lock nor
a database on a read-only filesystem. Readable history uses SQLite URI `mode=ro`,
with the SQLite connection itself read-only, no migration/reconciliation and no
checkpoint or recovery writes. Another writer cannot acquire ownership. Returning
the mount to writable does not clear the status-only latch; an explicit process
restart is required, followed by separate root activation before collection.

## WAL availability and honest metadata-only status

The first attempts established a further SQLite limitation: a cleanly closed
WAL-mode database on a read-only mount may lack the auxiliary files needed for
ordinary read-only SQLite access. SQLite documents these requirements in
[read-only WAL databases](https://www.sqlite.org/wal.html#read_only_databases).
The implementation does not add `immutable=1`, ignore committed WAL, select a new
VFS, copy security databases, change journal mode or fabricate an interval.

If existing private control history cannot be opened with SQLite CANTOPEN on a
known read-only filesystem, Runtime retains exclusive ownership but serves only
known storage/configuration metadata. Interval/event/health history remain
unavailable; diagnostics explicitly return unavailable rather than an empty
successful history. The source identifier is the configured identity, not proof
of an unreadable control database's contents. Other schema/source/corruption
errors retain strict rejection; corruption is not hidden by this fallback.

The service remains root-only through its existing endpoints and peer checks.
Failure remains `storage_pressure`; readiness is false, possible-gap true and
activation, reader leases and writes are denied. No previous activation is reused.

## Tests and intermediate evidence

Five new storage regressions cover read-only admission including recovery,
checkpoint refusal, exclusive ownership, SQLite-enforced read-only access,
restart latching, no fresh state creation, committed uncheckpointed WAL visibility,
metadata-only CANTOPEN status and rejection of corruption. The WAL test leaves a
committed interval only in WAL behind an older pinned snapshot, then verifies
read-only Runtime sees that new interval. It would fail if WAL were ignored.
Mac focused checks pass 87 M3 Python + 40 workflow tests.

Initial real read-only attempts retained failed jobs (not acceptance):

- `hids-m3-lab-71c0156642d2`, report
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-71c0156642d2/run-20261111T220936Z-8012103106c8/report.json`.
- `hids-m3-lab-45cf48585cae`, report
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-45cf48585cae/run-20261111T221354Z-3342f27ed0f5/report.json`.

The originating error was SQLite CANTOPEN at schema access on the real read-only
image. The test harness also now flushes child exceptions before closing its
coordination pipe, preventing parent cleanup from obscuring their cause. Cleanup
passed in both failed runs. These did not affect original HIDS/source state.

Metadata-only control then passed in job `hids-m3-lab-7952d201a177`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-7952d201a177/run-20261111T222138Z-3e237d4fc92e/report.json`,
protected `/root/hids-m3-filesystem.6o1mtx8v/report.json`, 20.580 guest seconds.
This earlier snapshot predates the last root-client and reporting regressions;
use the final evidence below for the completed scope.

## Final real root-control experiment

Passed job `hids-m3-lab-1165ec6fecac`:

- Workflow report:
  `/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-1165ec6fecac/run-20261111T222749Z-c48d4968ea5c/report.json`.
- Protected image/report: `/root/hids-m3-filesystem.7ccx60jg/report.json`.
- Source snapshot:
  `e66f58d0f0810a44e50f18c7edd80ac5b2abfc7078f37c74e13368ace4e51494`.
- Elapsed 21.003 guest seconds; verified native cache hit. Seven phases passed,
  including 87 M3 + 40 workflow tests, 26 native groups, 128 native contract cases,
  124 allocation cuts, 11 API faults and 58 actual SIGKILL boundaries.

The same private 64 MiB ext4 capacity/SQLITE_FULL/recovery sequence runs first.
Then root creates private 0600 Unix listeners inside a 0700 directory and passes
the descriptors to the actual unprivileged `Service`. The parent uses the actual
root control client's ownership, server/client peer credentials and framing
checks, redirecting only that test process's endpoint constant. No canonical
system endpoint or installed unit path changes.

On the read-only image, root status was available with 57,020,416 observed free
bytes, admission exhausted/`filesystem_read_only`, failure `storage_pressure`,
source readiness false and diagnostics/history unavailable. Activation and leases
were rejected. After a writable remount, storage was normal but the same process
still rejected activation/leases and left history unavailable. Explicit Runtime/
Service restart recovered readable diagnostics, removed the storage failure and
kept source readiness false and the old lease unavailable; B and interrupted A
passed integrity checks. No activation was attempted after that healthy restart.

An earlier private report encoded the unattempted healthy activation check as
`activation_rejected=false`; the test reporting was clarified to null for that
unattempted operation. This does not change the successful blocked-operation
assertions or product behavior. Final reporting verification is recorded below.

This is actual Service/control IPC on private endpoints with the actual service
identity and root client, not an installed systemd cold-start-under-all-VFS-errors
claim. The normal installed full live regression is a separate check. Read-only
history may remain unavailable until writable restart; no readable history is
invented. Hard project/user quotas, device faults, missing/corrupt sidecars outside
this scope, packaging/distribution/license and release thresholds remain open.

## Installed full checkpoint

All 17 phases passed in `hids-m3-lab-fed8a5af21b9`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-fed8a5af21b9/run-20261111T223150Z-887336cd9bb5/report.json`.
Elapsed 135.361 guest seconds, zero cached-artifact build commands; fresh native/
parser/crash regressions still ran. This includes 87 M3 + 40 workflow tests,
actual transport, installed event/storage, runtime/live Audit, 4096-event load,
resource/fault handling and health isolation/periodic/lifecycle. Exact policy,
configuration, installed-file and state-permission cleanup passed. No dispatch or
running result is treated as acceptance.

## Final constructor and reporting verification

Final review covered SQLite CANTOPEN at connection open as well as first schema
access, while corruption in either position retains strict failure and releases
ownership. The metadata fallback is now handled in one constructor exception path.
The same 87 tests include all four open/query and CANTOPEN/corruption combinations.

The final real filesystem/control run passed `hids-m3-lab-41e1824764fa`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-41e1824764fa/run-20261111T224229Z-49d87db868c7/report.json`,
protected `/root/hids-m3-filesystem.k9l8qz1j/report.json`, 21.979 guest seconds.
Source snapshot:
`74aad6f9a8479532e8460e5bc612ef43bd1fda12bf3142ea60b3a31ab046bfe0`.
All seven phases and cleanup passed, including the real root-client checks,
read-only metadata status, denied activation/leases, writable latch, explicit
restart, integrity and no resurrection. The healthy activation check is now
correctly recorded as unattempted/null. Earlier reporting clarification also
passed `hids-m3-lab-3c83c1954ff9`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-3c83c1954ff9/run-20261111T223719Z-78cefc4a58d9/report.json`,
21.710 guest seconds. These separate report identities preserve the exact tested
snapshots rather than attributing later tests to earlier code.

The final frozen constructor also passed all 17 full live phases in
`hids-m3-lab-905e404c024d`, report
`/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-905e404c024d/run-20261111T224552Z-4d5869ccdc35/report.json`.
Elapsed 142.627 guest seconds; 87 M3 + 40 workflow tests, cache hit and zero
cached-artifact build commands. Source snapshot:
`0a5f3263ee5c70d05c005015e7e84fed0413e0cbb66268a1ba277dabb48f6368`.
This repeats the full installed transport/runtime/live/load/resource/fault/health
regression after the final open/query constructor hardening. The earlier full
checkpoint above is retained as earlier evidence, not relabeled.

Final independent inspection matched the original protected Audit policy/rules
manifest, verified all four original source inode/byte prefixes, matched all 29
installed artifacts and restored exact HIDS configuration (512 lab activations).
All 355 SQLite files including control remain, state is ingest 0700/files 0600,
configuration root 0640, Audit active and all M3/checker units inactive. All nine
protected test images remain root 0600 within root 0700 directories. No loop,
mount, temporary control socket or fault/probe executable leaks remain. No Mac
settings, installations, credentials or cleanup changed. The owner approved committing/pushing this checkpoint to
`aidenjlee4321/HIDS_Project` on `main`; verify Git for publication status.
