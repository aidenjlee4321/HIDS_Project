# M2 runtime acceptance readiness gate

This records preparation and offline validation only. No Ubuntu runtime acceptance,
service startup, live journal access or new snapshot transfer was performed.
The runtime exercise is **not yet cleared**: the Linux archival gate and owner
source-identity provisioning below remain outstanding. Both storage limits are
now owner-approved for the current runtime acceptance only.

## Changed-file inventory

Modified:

- `docs/validation/m2-runtime-acceptance/resources.py`
- `docs/validation/m2-runtime-acceptance/probe.py`
- `docs/validation/m2-runtime-acceptance/runbook.md`
- `tests/unit/test_m2_runtime_archival.py`

Created:

- `docs/validation/m2-runtime-acceptance/validate_archival_linux.py`
- `docs/validation/m2-runtime-acceptance/readiness-report.md`

No production implementation, contract, schema, existing fixture, historical
validation record or validated snapshot was changed. The original readiness check
verified all 109 manifest-listed canonical files against the immutable snapshot.
The subsequent owner-approved documentation-only configuration synchronization
updates `docs/implementation/m2-journald-spec.md`; the other 108 canonical files
remain identical. All 109 files in the snapshot remain unchanged under manifest pin:
`9c2d2df75cfd7989b5427ed578c96b1fe45ed90a18f70e6245e7d7f692234aea`.

## Corrections and archival behavior

The existing implementation archives **both** the database and runtime trees by
stream-copying into exclusive destination-side staging directories. It rejects
links, special files, nested devices, overlapping paths and extended Linux
metadata; ACLs/xattrs are refused rather than silently lost. Copies preserve UID,
GID, POSIX permissions and modification times, including mixed ownership when
executed as root. Exact structure, sizes and SHA-256 values are verified against
frozen source identities. Access times may change; copied inode/device/ctime
identities necessarily differ.

Files and directories are fsynced before publication. Publication uses a native
same-parent no-replace rename, followed by parent fsync; no replacement fallback
exists. Both archives and both originals must verify before durable receipts are
written and any original is removed. Removal uses only individually checked
inventory entries and descriptor-relative no-follow operations. Failure leaves
stages/final archives for inspection; nothing merges or retries automatically.
Partial removal can leave fewer originals, but only after both complete archives
were verified and their receipts persisted.

Added `finish_cleanup()` reserves and fsyncs an exclusive
`completion-unconfirmed` marker before final inventory replacement. A marker
supersedes any visible `cleanup_complete` flag, including on inventory reload.
Failure resets the in-memory completion state and returns unsuccessfully without
retrying an ambiguous write. Successful completion requires inventory persistence,
marker removal, parent fsync **and successful helper return**. If the very last
parent fsync fails after marker unlink, completion durability remains unknown;
neither marker absence nor a visible flag alone proves success. No multi-filesystem
transaction or power-loss guarantee is claimed.

One concrete probe defect justified changing `probe.py`: `MainPID=0` can occur
while `ExecStopPost` is still running. `wait_exit()` now waits for inactive state
before reading the exit marker and fails promptly on failed state. Its journal,
replay, storage and collection behavior is unchanged. The regression simulates
`deactivating → inactive` and verifies that exit evidence is checked only afterward.

## Requirement audit

PASS means the stated static/local check passed, not that Ubuntu runtime behavior
was observed. NOT TESTED requirements must pass before declaring acceptance.

| Requirement | Status | Evidence / remaining gate |
|---|---|---|
| Complete acceptance source and production-interface review | PASS | Reader/config/runtime, service/control/peer policy, storage, units and runbook compared |
| Standalone and embedded helpers, hashes | PASS | Exact byte equality; standalone Linux gate embeds exact current helper/test bytes |
| Genuine socket activation design | PASS | Unchanged socket unit; production requires PID match, one FD, actual listening Unix socket on FD 3; no fabricated environment |
| Actual FD 3 and LISTEN_PID on Ubuntu | NOT TESTED | Runbook Stage 6 verifies running process metadata |
| Unit ordering, shutdown readiness | PASS | Requires/After and reverse stop order; bounded readiness; stop-hook race corrected |
| Service identities/groups and filesystem policy assertions | PASS | Reader UID 997; independent NSS GIDs; service-only journal/IPC groups; ingestion excludes journal; fixed ownership/modes |
| Actual current Ubuntu credentials, journal permissions and peer authentication | NOT TESTED | Stages 2–7; no assumptions from interactive-user access |
| Protected three-key configuration | PASS | Root-owned protected copy; exact source_id/max_records/max_pages; no runtime config under /tmp |
| No collection before root activation / no historical backfill | PASS | Production start gate inspected; inactive probes avoid journal payload inspection; existing fixture tests passed |
| Actual inactive/active behavior and SSH event attribution | NOT TESTED | Exact source-port, boot-ID and monotonic-time match after one credential-free connection |
| Exact approved emitter filters | PASS | Paired COMM/EXE AND branches, OR between branches; 35 M2 vectors passed |
| Read-only retrieval / explicit transactions / bounded queries | PASS | Production read-only connection and fresh get_event; explicit snapshot BEGIN/ROLLBACK; bounded records/activations/gaps |
| Actual persisted event/checkpoint and immutable duplicate replay | NOT TESTED | Stages 8–9; all persisted event/progress/activation columns compared; interruption rows separately reported |
| Response/reconciliation and concurrent-reader assertions | PASS | Production validate_response; exact reconciliation checks; second peer must close, not merely time out |
| Actual concurrent reader, crash/restart, deactivation and shutdown | NOT TESTED | Stages 7, 10–11 within original authorization interval |
| Same-filesystem archival on macOS | PASS | Actual Darwin exclusive rename and exact metadata/content verification |
| Linux renameat2 no-replace behavior | NOT TESTED | Self-contained gate requires real Linux syscall; no mocked EXDEV substitute |
| Actual cross-device archival and interrupted cross-device copy/collision | NOT TESTED | Gate requires distinct /tmp and /dev/shm devices; no mounts created |
| Root cross-account UID/GID preservation | NOT TESTED | Explicit --ownership gate uses existing hids-journal/hids-ingest accounts, only new private fixture trees |
| Failure injection / source preservation | PASS | Local synthetic cases below; no destructive acceptance execution |
| Native Linux extended metadata handling | NOT TESTED | Linux gate creates one synthetic user xattr and requires fail-closed archival rejection |
| Cleanup inventory, receipt and completion failure handling | PASS | Local tests cover durable receipt gate, partial removal and final bookkeeping uncertainty |
| Linux-native archival execution environment | NOT TESTED | Docker client exists, daemon unavailable; no daemon/VM installed or started |
| Acceptance storage limits | PASS | Owner approved max_records=100 and max_pages=4096 for this runtime acceptance only; not production defaults or retention policy |
| Private source identity | OWNER DECISION REQUIRED | Persistent source UUIDv4 must be supplied in protected runtime configuration and private evidence, never tracked documentation |

The SSH test requires an already active IPv4 loopback/wildcard sshd listener on
port 22 and its existing Ed25519 public host key. It stops if unsuitable; it does
not start/configure SSH or broaden filters. A credential-free connection may emit
no suitable port-bearing record; that is an incomplete live test, not a pass.
Negative CLI/DAC checks do not claim a non-root peer bypassed DAC and reached the
backend's credential check. Absence of pre-activation records is not syscall
tracing. These limitations remain explicit in the runbook.

## Failure-injection coverage

Local tests cover source mutation; interrupted streaming writes and directory
traversal; hash/size/structure/ownership/mode/mtime mismatches; existing target,
existing staging reservation and racing empty target; publication EXDEV/EIO;
missing/unsupported no-replace primitive; file/directory fsync failures; receipt
persistence failure; first and partial original unlink failures; final completion
write and inventory-parent fsync failures; completion-marker removal and collision.
Symlinks, hardlinks, FIFO, nested device and Linux metadata rejection are covered.
The real cross-device and native xattr cases are Linux-gated, not counted as local
passes. Root ownership preservation is a separate explicit native test.

## Test results and exact commands

Host: macOS 14.5 ARM64, Apple Clang 15.0.0, Python 3.9.6, SQLite 3.43.2.

```bash
python3 -B -m unittest discover -s tests/unit -p 'test_m2_runtime_archival.py' -v
HIDS_DEV_STATE=/private/tmp/hids-dev-m2-readiness-final-unrestricted \
HIDS_NATIVE_UAPI=/private/tmp/hids-cnproc-validation-1wejko38/include/uapi \
HIDS_NATIVE_SHIM=/private/tmp/hids-cnproc-validation-1wejko38/mac-shim.h \
python3 -B scripts/dev.py test --sanitize
```

- Archival/probe suite: **39 run, 36 passed, 3 skipped**. Skips: actual Linux
  cross-device success; actual Linux cross-device interruption/collision; native
  Linux xattr handling. No failures.
- Full offline suite: **exit 0**, plus workflow suite **exit 0**. Both native
  regression suites and production link smoke passed. All **62 M1** and **35 M2**
  vectors, M1 contract/native fixture and M2 reader runtime checks passed with
  ASan/UBSan; no sanitizer finding was reported.
- Python: 13 launcher, 17 M1, 3 M1 policy, 17 M2, 1 M2 fixture integration,
  15 lifecycle/security, 5 runtime process integration and **21 automation** tests
  passed: **92 passed**. The **12 M1 Linux integration tests skipped** because
  this is macOS; none is counted as accepted by this run.
- Initial sandboxed full run failed at the M2 socket fixture with `EPERM` binding
  a temporary Unix socket. The authorized rerun outside that sandbox passed.
  No production check was weakened and no test was removed.
- Report: `/private/tmp/hids-dev-m2-readiness-final-unrestricted/runs/validation-20261108T042605Z-cfa142aa864a/validation.json`;
  stdout/stderr logs are alongside it. Initial failed run evidence remains under
  `/private/tmp/hids-dev-m2-readiness-final/runs/validation-20261108T042422Z-c80ef0cbea62`.
- Static checks: four Python files parsed; all **18 Bash fences** individually
  and combined passed `bash -n`; Python heredocs parsed; both embedded helpers
  matched standalone bytes; three embedded base units matched packaging exactly;
  Linux-gate embedded payloads/digests matched current files. Linux gate `--help`
  passed on host; Linux test execution was not performed.

## Eventual Ubuntu commands and owner gate

Use [runbook.md](runbook.md) as the complete executable package. Supply the
standalone gate separately, outside the immutable source snapshot; no transfer was
performed by this task. Stage 0 contains the exact outer SHA-256 verification and:

```bash
python3 -I -B "$ARCHIVAL_GATE"
sudo /usr/bin/python3 -I -B "$ARCHIVAL_GATE" --ownership
```

Both must exit 0 with zero skips. The first expects 39 tests; the second expects
one real cross-account preservation test. All root-owned test files are confined
to newly created temporary directories; no service or journal access occurs.
Stop on unavailable /dev/shm, unsupported syscall, missing identities or any other
failure. Do not install, mount or change memberships to force the gate through.

Then run numbered Stages 1–12 in the runbook, in one ordinary-user Bash session.
These contain the full compile command, genuine socket-activated unit setup,
explicit root activation, controlled SSH connection, production response-validated
replay, restart tests, deactivation and inventory-guarded cleanup. Do not execute
embedded Python helper bodies or unit text as separate shell commands.

Still required: privately supplied persistent source UUIDv4 in the protected runtime
configuration and private evidence; do not record its value in tracked documentation.
The owner has approved `max_records=100` and `max_pages=4096` for the current runtime
acceptance only. They are not permanent production defaults or a finalized retention
policy; see the [configuration specification](../../implementation/m2-journald-spec.md#8-runtime-acceptance-configuration).
The former caps cumulative stored dispositions, including rejections; duplicate checks precede the cap. The
latter caps main database pages (16 MiB only at a measured 4096-byte page size),
not WAL/SHM/logs or disk usage generally. Capacity errors stop acceptance; committed
records are not evicted. No source UUID has been generated or recorded here.
Storage approval does not pass the remaining Linux or runtime acceptance gates.

## Artifact SHA-256

| Artifact | SHA-256 |
|---|---|
| resources.py | `f7a241c6bdfe47ca50a556c01a642b47dd32129d2071ae8bf848d322983022bb` |
| probe.py | `2c7a22c6ea0c7d2143536c5af90c60b6bda3965f43f1a877181f2a54ad9a4a5e` |
| runbook.md | `cea62ad176d4fd8561df5ecc6cb6015d212372c76737b2eda63111e21d875a77` |
| validate_archival_linux.py | `3c5ae72a36ad3d4fd73e0354c15f9ba5af7fe837fb2cb7a4651252f0eb3f6f8b` |
| test_m2_runtime_archival.py | `6ac325c4b184d5c1dd9b7cd21e5eda42006b00b8f1c5e2b07b00c5d43a09d507` |

This report intentionally does not contain its own self-referential digest.
