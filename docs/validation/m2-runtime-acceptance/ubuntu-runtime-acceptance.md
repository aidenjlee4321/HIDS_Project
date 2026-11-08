# Ubuntu M2 runtime acceptance

**Exercise date:** November 8, 2026

**Evidence basis:** Project-owner report from manual execution through the UTM console

**Status:** Runtime exercise completed; archival and cleanup verified by the owner; live backend-level negative control authorization remains unverified.

This records the owner's supplied observations, not an independently repeated
exercise or inspection of private evidence. The [readiness report](readiness-report.md)
remains the historical preparation record. The [runbook](runbook.md) describes the
staged procedure; the [M2 specification](../../implementation/m2-journald-spec.md)
defines the implementation. No acceptance procedure was rerun to write this report.

## Environment and configuration

| Component | Owner-reported environment |
|---|---|
| Operating system | Ubuntu 26.04.1 LTS |
| Architecture | ARM64 / aarch64 |
| Kernel | 7.0.0-42-generic |
| GCC/G++ | 15.2.0 |
| systemd | 259 |
| Python | System Python 3.14 |
| Storage | Python-owned SQLite |

The validated source snapshot was `hids-src-20261108T012355Z-e520e3a020ed`, with
manifest SHA-256 `9c2d2df75cfd7989b5427ed578c96b1fe45ed90a18f70e6245e7d7f692234aea`.
The owner previously reported offline Ubuntu validation passed: three phases,
zero skips. That offline result is distinct from this runtime exercise.

The current acceptance used owner-approved `max_records=100` and `max_pages=4096`.
The former caps cumulative stored dispositions, including native rejections;
duplicate lookup precedes the cap. The latter limits main SQLite database pages,
including tables and indexes: 16 MiB only at a measured 4096-byte page size.
WAL/SHM files, diagnostic logs and archives require additional storage. These
values are acceptance-only budgets, not production defaults or a retention policy.
Capacity failures stop acceptance rather than silently evicting committed records.

An owner-generated persistent source UUIDv4 was validated and retained in protected
runtime configuration and private evidence. Its value is intentionally omitted.
Collection required explicit authorization; service start alone did not authorize it.

The existing SSH listener used systemd socket activation. The owner verified that
the port-22 listener belonged to systemd (PID 1), and no SSH service/socket
configuration changes were needed. This differs from the written runbook's
precondition requiring an already active `ssh.service` and an IPv4 listener owned
by an executing `sshd`. The reported run therefore must not be described as a
byte-for-byte execution of that precondition; the exact console adaptation was
not supplied. No change to the runbook or collection filters is asserted here.

## Native Linux archival gate

| Test | Owner-reported result |
|---|---|
| Linux archival suite | 39 passed; zero failures, errors or skips |
| Separate explicit-root cross-account ownership test | Passed |

These results cover native exclusive publication, real cross-device archival,
interrupted copying, source preservation, destination collisions, metadata and
content verification, and cleanup bookkeeping. The separate ownership test used
existing HIDS identities and disposable temporary trees to verify cross-account
UID/GID preservation. These are Linux-native observations, distinct from earlier
macOS tests that skipped Linux cases.

## Runtime Stages 1–12

The following results are owner-reported. Architecture statements describe the
intended production path: journald → non-root C++ reader → authenticated Unix
stream/JSON Lines → independent Python validation → Python-owned SQLite.

| Stage | Reported result |
|---|---|
| 1 — Preflight | Ubuntu platform and development/runtime dependencies checked. |
| 2 — Identities and existing resources | Service identities and group policies verified; existing systemd-activated SSH listener assessed as described above. |
| 3 — Permission assessment | Journal permission assessments completed without opening the journal; reader and ingestion access boundaries assessed. |
| 4 — Build and configuration | Actual reader built; approved budgets and privately supplied source identity validated. |
| 5 — Protected preparation | Protected configuration/storage and temporary service definitions prepared; service isolation assessments passed. |
| 6 — Inactive behavior and denial | Initial database contained no pre-activation records; inactive reader did not start collection. Client-side control refusal and ordinary-user socket DAC denial verified, with the qualification below. |
| 7 — Explicit activation | Collection authorized explicitly; active reader credentials and ingestion journal denial checked; concurrent reader rejected while original lease retained; initial boundary verified. |
| 8 — Controlled SSH event | Controlled localhost connection completed; connection/event artifacts, persistence status and database summary retained. Owner reports selected SSH event collection and persistence. |
| 9 — Immutable replay | Replay completed and before/after fingerprints compared; replay receipt and reader status retained. Owner reports duplicate replay with unchanged event/checkpoint state. |
| 10 — Recovery | Reader crash/replacement and reader/ingestion restart exercises completed; recovery evidence retained; temporary owned units stopped. |
| 11 — Revocation and shutdown | Authorization revoked; reader cancellation verified; restart did not resume collection without renewed authorization; final database summary and ingestion shutdown verified. |
| 12 — Archival and cleanup | Unit definitions and resource inventory checked; database/runtime archives verified before original removal; temporary runtime resources removed and private evidence retained. |

The collection scope remained the approved SSH emitter pairs:
`_COMM=sshd` AND `_EXE=/usr/sbin/sshd`, OR
`_COMM=sshd-session` AND `_EXE=/usr/lib/openssh/sshd-session`.
The report does not authorize broader collection or historical backfill.

The acceptance procedure checks connection attribution using the captured source
port, boot ID and journal monotonic receipt timestamp; it retrieves data through
read-only SQLite connections and checks cursor/checkpoint alignment. Replay uses
production response validation and compares persisted state. The owner reports
these workflows completed, but raw event values, fingerprints, receipts and
cross-account credential details were not supplied for independent examination.
No such values are invented or reproduced here. Monotonic time is not wall-clock
activity time, and journal receipt time is not an established activity timestamp.

## Stage 6 diagnostic qualification

The live ordinary-user control invocation printed
`m2_control_failure_or_unconfirmed_outcome`. In
[`m2_control.main()`](../../../engine/ingestion/m2_control.py), a non-root caller
raises `PermissionError('root_control_required')` before loading configuration or
connecting to the control socket. The generic exception handler prints that
message and returns 1. The runbook wraps the expected failure in an `if` statement,
so a nonzero return permits the stage to continue; a successful non-root invocation
would instead fail the stage. The invoked command is `status`, not an attempted
backend activation request.

| Security assertion | Live exercise conclusion |
|---|---|
| Client-side refusal | Verified according to the owner; consistent with the inspected early root check and diagnostic. |
| Filesystem permission denial | Verified according to the owner for both protected Unix sockets. |
| Backend peer-credential rejection of an unauthorized caller | **Unverified in this live exercise.** |

[`RootPolicy.check()`](../../../engine/ingestion/m2_service.py) independently
validates Linux `SO_PEERCRED` and requires UID 0. Its implementation exists, but
the client refusal and DAC denials do not establish that an unauthorized live
connection reached that check. The generic diagnostic alone is not proof of a
backend rejection. Do not mark this backend-level negative case passed or loosen
permissions to force it through.

## Final state and evidence preservation

| Resource | Owner-reported final state |
|---|---|
| `/var/lib/hids` | Removed |
| `/run/hids` | Removed |
| Temporary HIDS systemd units | Removed |
| Database and runtime archives | Verified and preserved |
| Original runtime/database resources | Removed after archival verification |
| Private acceptance evidence | Preserved, root-owned directory with mode 0700 |
| Cleanup completion flag / phase | True / complete |
| Completion uncertainty marker | Absent |

The owner reports successful cleanup completion, not merely observation of a flag.
Archived database ownership and restrictive permissions were preserved. Runtime
artifacts and replay evidence were retained separately. The validated snapshot
was not modified by this documentation task.

Private evidence, databases, event records, credentials, source UUIDs and root-owned
acceptance artifacts must remain outside tracked documentation. This report
contains only the supplied sanitized results and implementation references.

## Limits and interpretation

The exercise provides a concrete owner-reported Linux runtime baseline for service
isolation, explicit authorization, selected SSH collection, persistence/replay,
recovery, revocation and archival. It does not establish production readiness,
comprehensive/lossless monitoring or long-running reliability.

Forced journal rotation/vacuum, empty-journal restart, live disk-full and lost-ACK
scenarios were not established by this live exercise. Offline coverage is distinct
from live observations. No power-loss guarantee or transaction spanning filesystems
is claimed. Backend-level unauthorized-peer denial remains unverified, and the
socket-activated SSH preflight adaptation is recorded rather than silently treated
as the original runbook condition.
