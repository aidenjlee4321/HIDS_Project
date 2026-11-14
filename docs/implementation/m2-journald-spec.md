# M2 journald implementation specification

Original fixture authorization and proposals are preserved below. Later lifecycle
implementation and [owner-reported runtime acceptance](../validation/m2-runtime-acceptance/ubuntu-runtime-acceptance.md)
record subsequent scope. The original no-live-authorization header applies to its
checkpoint; it does not override later explicit owner approvals.

**Status:** Owner-approved for fixture-based M2 implementation; deployment/live acceptance not authorized
**Recorded:** November 7, 2026
**Scope:** One local SSH-journal source → C++ → Unix stream/JSON Lines → independent Python validation → Python-owned SQLite/retrieval

The owner has accepted separate M2/M1 contracts, cursor-based identity, atomic
event/checkpoint persistence, current-position start without historical backfill,
whitelisted bounded fields, least privilege, idempotent retries and explicit
activation. The owner subsequently approved the concrete choices for implementation. They do
not modify the [M1 contract](m1-pilot-contract.md), schemas, tests or evidence.

## 1. Prerequisites and integration

Owner-verified Ubuntu preparation (not rerun during this documentation task):

| Prerequisite | Supplied result |
|---|---|
| `libsystemd0` | 259.9 installed |
| `libsystemd-dev` | 259.9 installed; `sd-journal.h` available |
| `pkgconf` | 2.5.1 installed |
| Reader account | Dedicated system account `hids-journal`, UID 997 |
| Permanent journal membership | No permanent `systemd-journal` membership |

No further dependency is proposed. Link the native adapter with `libsystemd`;
use existing C++20, nlohmann/json 3.12.0 and Python standard-library SQLite.
Actual service group/GID, journal access, SSH executable paths, service execution,
reader-to-ingestion credentials and runtime reliability still require verification.
Do not infer a GID of 997 from the supplied UID.

Preserve `collector/src/{process_collector,process_connector_protocol,linux_process_connector}.cpp`
and their native interfaces. Add `collector/include/hids/journal_collector.hpp`,
`collector/src/journal_collector.cpp` and separate M2 normalization/transport modules.
Use injectable `JournalIo`, journal-native records, and serialized
`start(activation)`, bounded `poll_once()`, `stop()` operations. Never force a
journal record into `process::NativeEvent`.

Reuse patterns/utilities from `collector/src/pilot/contract.cpp` (`utc_now`,
`uuid_v4`, strict JSON handling), `pilot/transport.cpp` (`Channel`, bounded I/O),
and Python `m1_contract.py`, `m1_receiver.py`, `m1_store.py` without changing M1
semantics. `transmit()` directly invokes M1 validation; M2 needs its own entry
point. Add `engine/ingestion/m2_contract.py`, `m2_receiver.py` and
`engine/database/m2_store.py`. Use a separate M2 database; M1 schema validation and
its 100-row synthetic table remain untouched.

## 2. Service identity, IPC and authorization

Proposed future reader unit policy: `User=hids-journal`, primary
`Group=hids-journal` (verify it exists), `DynamicUser=no`,
`SupplementaryGroups=systemd-journal hids-ipc`, `NoNewPrivileges=yes`, empty
`CapabilityBoundingSet=` and `AmbientCapabilities=`, `UMask=0077`.
Journal membership is supplied only to service processes; do not add it permanently
to the account or grant `adm`, root or DAC-bypass capabilities. A service process
can read more than the selected dataset if compromised: filtering is minimization,
not an access-control boundary.

Propose a separate non-login `hids-ingest` account with primary group
`hids-ingest` and only `hids-ipc` as an additional service group. No journal groups,
OS collector permissions or capabilities. This account/group and `hids-ipc` have
**not** been reported created and require explicit setup approval.

`SupplementaryGroups` extends NSS account groups; it does not remove unwanted
permanent memberships. Audit actual memberships at setup and fail startup if the
approved credential policy is not satisfied. See
[systemd execution policy](https://raw.githubusercontent.com/systemd/systemd/v259/man/systemd.exec.xml).
Units and executable lifecycle/activation entry points now exist as source
artifacts; none are deployed or started. See the
[lifecycle record](../validation/m2-lifecycle-validation.md); the earlier
[component checkpoint](../validation/m2-component-validation.md) remains historical evidence.

| Resource | Proposed owner/group and mode | Access boundary |
|---|---|---|
| `/run/hids` | root:root, 0755 | Protected parent; no ordinary-user writes |
| `/run/hids/ingest` | hids-ingest:hids-ipc, 0750 | Reader can traverse, cannot replace socket |
| `/run/hids/ingest/journal.sock` | hids-ingest:hids-ipc, 0660 | Unix stream; backend creates/listens |
| `/var/lib/hids/m2` | hids-ingest:hids-ingest, 0700 | Reader cannot access database |
| `journal.sqlite`, WAL/SHM and private reports | hids-ingest:hids-ingest, 0600 | Backend and root only |

Socket initialization must explicitly set owner/group to hids-ingest:hids-ipc,
set mode 0660, and verify type, ownership and mode before listening. Failure is
fatal; no fallback to a permissive socket. Tests must cover both valid SSH
command/executable pairs, crossed pairs, unrelated processes and missing/mismatched
executables, including the exact libsystemd AND/OR call sequence.

Future privileged HIDS setup establishes these resources; it does not alter journal
files, ACLs or Ubuntu logging. Reject symlinks, unsafe owners/modes and unexpected
existing socket objects; remove only an endpoint whose identity the process owns.
No security data goes in the shared transfer folder or application stdout logs.

Both endpoints verify Linux `SO_PEERCRED` before reading event/control frames.
Receiver requires reader UID 997 and its configured primary GID; reader requires
the configured `hids-ingest` UID/primary GID. Resolve/pin account IDs at trusted
startup; no peer-supplied UID, PID or registration is accepted. The receiver binds
one reader PID to an activation lease. A replacement PID must reacquire that lease
through its authenticated connection; refuse concurrent readers. PID is session
identity, not durable authorization. M1's exact-PID, same-UID harness is unchanged.

Only a separate root-authenticated local control path may create/revoke source
activation, bound to the fixed source profile. No HTTP interface or event message
can activate a source. Prototype tests use inherited trusted control pipes; actual
root control/setup requires separate approved deployment work. Journal handles,
tail inspection and payload reads are forbidden until activation is authorized.

## 3. Exact source and event contract

Source profile `local-default-system-ssh-v1`: local machine, default namespace,
`SD_JOURNAL_LOCAL_ONLY | SD_JOURNAL_SYSTEM`, with explicit OR branches:

1. `_COMM=sshd-session` AND `_EXE=/usr/lib/openssh/sshd-session`.
2. `_COMM=sshd` AND `_EXE=/usr/sbin/sshd`.

Verify paths on Ubuntu before activation. No automatic alternative paths, broader
unit filters, other namespaces/hosts, sudo records or full-journal ingestion.
Use libsystemd matches; keep native service fields separate from message accounts.
No authentication correlation or attempt counting: distinct PAM/SSH entries remain
distinct records. Detection, Audit/cn_proc integration and dashboard are not M2.

Contract `m2.journal-ssh/0.1.0`, protocol 2. All listed keys are required; no other
keys are accepted. Optional native information is represented by explicit nulls.

| Envelope key | Exact type/constraint |
|---|---|
| `protocol_version` | Integer 2, never Boolean |
| `message_type` | String `journal_event` |
| `contract_version` | String `m2.journal-ssh/0.1.0` |
| `source_id` | Persisted lowercase UUIDv4 bound to this local profile/database |
| `activation_id` | Persisted lowercase UUIDv4 for the authorized interval |
| `event_id` | Cursor-derived string defined in section 4 |
| `cursor` | Opaque printable ASCII, 1–512 bytes; no NUL |
| `expected_revision` | Integer 0 through 2^63−1; no Boolean |
| `journal` | Exact object: `boot_id`, `realtime_us`, `monotonic_us` |
| `fields` | Exact whitelist object below |
| `observation` | Exact object: `producer_instance_id`, `observed_at` |
| `activity_wall_time` | Null |
| `activity_wall_time_reason` | String `not_established` |

`boot_id` is 32 lowercase hexadecimal characters. Journal clock values are uint64
canonical decimal **strings**, in microseconds, without leading zeroes except `0`.
Monotonic time is boot-scoped; realtime is journal receipt time, not asserted
activity time. `producer_instance_id` is UUIDv4; `observed_at` is collector UTC
`YYYY-MM-DDTHH:MM:SS.ffffffZ`, calendar-validated. Backend receipt/storage times are
stored separately. Clock failure stops submission; never fabricate activity time.
No new ECS mapping is finalized by this limited contract.

| Exact `fields` key | Value and decoded byte limit |
|---|---|
| `_COMM` | Required UTF-8 string, 1–64; must match selected branch |
| `_EXE` | Required UTF-8 string, 1–1024; must match selected branch |
| `MESSAGE` | Required UTF-8 string, 0–4096 |
| `_PID` | Canonical decimal string for 1–2147483647, or null |
| `_UID`, `_GID` | Canonical uint32 decimal string, or null |
| `_SYSTEMD_UNIT` | UTF-8 string, 0–256, or null |
| `PRIORITY` | String `0` through `7`, or null |
| `_TRANSPORT` | ASCII string, 1–32, or null |
| `MESSAGE_ID` | 32 lowercase hexadecimal characters, or null |

No `_CMDLINE`, hostname, raw syslog payload, environment or arbitrary field copy.
Reject binary/invalid UTF-8, embedded NUL, repeated whitelisted native fields and
malformed present values. Missing optional values are null; malformed is not null.
Missing required metadata/content produces a durable rejection, not a fake event.
Inspect length-delimited fields without copying unselected values. Bound inspected
field count to 256 per entry; exceeding it is an explicit rejection. Duplicate
checking must not silently use only the first whitelisted occurrence.

Set a low library data threshold, inspect explicit returned lengths and reject
ambiguous threshold-sized/truncated data instead of claiming completeness. The
threshold is a hint, not a hard library allocation bound; application copies and
queues are bounded, while library overhead must be measured. See
[field API](https://www.freedesktop.org/software/systemd/man/259/sd_journal_get_data.html).

UTF-8 JSON Lines, maximum 65536 payload bytes excluding LF; responses max 2048;
depth eight; reads max 4096 bytes. Reject duplicate JSON keys, extra keys, invalid
types, malformed encoding and oversized frames before unbounded buffering. Use
the JSON library for escaping, including embedded message newlines. No truncation.

## 4. Identity, storage and responses

`event_id = "j1." + source_id + "." + lowercase_hex(cursor_bytes)`.
This is reversible, delimiter-unambiguous and requires no hash dependency. Do not
parse cursor internals, sort cursors or derive identity from PID/time/message.
The source UUID persists across reader restarts; source profile changes require
separate activation/profile review, not silent reuse with different filters.

Cursors may have equivalent textual representations. Use `sd_journal_get_cursor`
for newly encountered entries; freeze that token before sending. On restart or
requested replay of the saved entry, position and use `sd_journal_test_cursor` to
verify equivalence, then reuse the **saved token**, not a freshly spelled alias.
Only sequential continuation/recovery of this stream is allowed; arbitrary older
cursor submissions or aliases are not a backfill API. If equivalence cannot be
established, stop and report a gap. No blanket guarantee of canonical spelling is
assumed. See [cursor semantics](https://www.freedesktop.org/software/systemd/man/259/sd_journal_get_cursor.html).

Compare canonical source content: contract/source/cursor, journal metadata, fields
and activity-time representation. Exclude activation/revision and observation
metadata; preserve first stored observation. Sort JSON object keys with compact
ASCII-escaped serialization and no floats/NaN; validate independently in C++ and
Python. Within retries resend the exact immutable envelope, not just equal content.

Python alone owns separate M2 event, rejected-disposition, activation and progress
tables. Events have unique source/cursor identity and event ID. Progress contains
activation, revision and last committed cursor or explicit initial-boundary state.
Use explicit SQL transactions, WAL, FULL synchronous, busy timeout 1000 ms and
independent reader/writer settings as in M1; M2 schema initialization is separate.
Read-only retrieval uses URI-encoded `mode=ro`; protect sidecars too.

For each event/rejection: `BEGIN IMMEDIATE`; verify activation/lease; look for an
existing identity; compare content; for a new record compare-and-swap the expected
revision; insert event/disposition and update cursor/revision; `COMMIT`; then ACK.
Duplicate lookup precedes stale-revision rejection: a committed identical replay
returns its original receipt without moving progress backward. Unknown identity
with stale revision is rejected. Conflict changes neither original nor progress.
At revision exhaustion stop; never wrap. Database capacity failure stops progress;
M2 storage budgets are explicit and independent of M1's synthetic row limit.
Section 8 records the separately approved current acceptance budgets; production
budgets remain a gate before unattended use, not permission for unbounded runs.

Protocol-2 ACK has exactly `protocol_version`, `message_type="ack"`, `event_id`,
`result` (`stored`, `duplicate`, `rejected_record`), `checkpoint_revision` (the
record's committed revision), `code` (null, or rejection reason). A duplicate
rejected disposition returns `rejected_record`. Reject has exactly protocol,
`message_type="reject"`, nullable/matching `event_id`, and `code` from
`invalid_json`, `invalid_event`, `unsupported_version`, `frame_too_large`,
`id_conflict`, `stale_revision`, `inactive_source`, `reader_busy`.
Error has exactly protocol, `message_type="error"`, matching `event_id`,
`code="storage_error"`. All response keys/types/IDs/codes are validated; malformed
responses mean unconfirmed, never rejection or success.

A valid identity with unrepresentable native content is sent as
`message_type="journal_rejection"` with exactly protocol/contract, source,
activation, event ID, cursor, expected revision, observation and `reason`.
Allowed reasons: `missing_required`, `malformed_field`, `duplicate_field`,
`binary_field`, `field_too_large`, `too_many_fields`, `event_too_large`.
No offending values are retained. Commit disposition and progress atomically;
ACK only afterward. Unusable cursor/identity cannot advance progress: store a
source failure through the trusted control path and stop. Wire-invalid requests
never become trusted checkpoint-advancing rejection records.

Lost ACK: frozen retry or authenticated progress reconciliation. Reconciliation
returns backend-owned activation/revision/cursor and any requested committed
receipt; it never permits a reader to set progress. One ordered stream, one pending
record, one active reader lease. Connection loss releases the lease; authenticated
replacement obtains a new lease and persisted state before continuing. Use three
automatic connection attempts, 100/500 ms delays, 30-second total operation and
5-second I/O stages. Exhaustion stops collection; an explicit retry gets a fresh
budget, with at most one explicit retry per pending operation in M2 acceptance.
No background recovery loop or durable producer outbox is introduced.

Storage exceptions after attempted commit are unconfirmed. Terminal protocol/
storage failures close ingestion for this source and report failure; explicit
restart/reconciliation only. Startup failure has no event-specific response.
Post-commit retrieval failure never revokes an ACK or committed progress.

## 5. Activation, boundaries and gaps

Root-authorized control persists source/profile/activation before permitting open.
After opening and installing exact matches: seek tail, position on the latest
matching entry with `sd_journal_previous`, capture only its cursor as baseline,
and persist that boundary before reporting `active`. Do not emit/read its message.
Keep the reader positioned there while awaiting persistence; the next forward
entry is eligible. Do not seek tail again after boundary acknowledgement.

The start boundary is the selected cursor, not the earlier authorization click or
a guessed wall time. Record boundary-establishment start/end observations; show
`initializing` until durable. Concurrent appends after the chosen baseline remain
eligible; entries included in the selected baseline are outside the declared
interval. Boundary setup failure stops without silently choosing a newer boundary.
Tests must verify actual libsystemd tail/previous/next behavior and append races.

If no matching entries exist, persist explicit `empty_unanchored` boundary and
retain the reader position. First new selected entry is committed normally. A
restart before a cursor is durably anchored stops with `unanchored_restart_gap`;
never silently re-tail. Explicit new activation may establish a new boundary,
while retaining the gap record. No historical scan/backfill is implied.

Restart with an anchored, still-authorized activation obtains progress from
Python, seeks the saved cursor, advances and tests exact equivalence. Skip only
the verified already-disposed entry, then continue. Catch-up after that checkpoint
within the same authorized interval is permitted recovery, not pre-activation
backfill. Revoked activations cannot resume; reenabling establishes a new interval.

On `SD_JOURNAL_INVALIDATE`, verify continuity; rotation alone is not proof of loss.
Missing/vacuumed cursor, access loss or unprovable position produces a durable
gap and stops the source. No nearest-entry acceptance, automatic tail reset or
timestamp-based recovery. Monotonic clocks drive waits; realtime changes do not
alter identity/progress. Persist gap code, source/activation, last confirmed
revision/cursor and observation times, not invented lost counts or activity times.
If SQLite itself is unavailable, report through bounded local control diagnostics
and explicitly label durable gap persistence unavailable until reconciliation.

## 6. Tests, scope and approval gates

Keep every M1/native regression, link smoke, strict warnings and supported sanitizer
check. Add shared C++/Python contract vectors, fake JournalIo cursor/field/rotation
sequences, SQLite faults around both inserts/progress/commit, and two-process
lost-ACK/restart/credential tests. Test stale duplicate receipt without checkpoint
rewind, conflicting replay, equivalent cursor reuse, durable rejection and empty
restart gaps. Test no pre-activation opens, append races, clock changes, unsafe
paths, wrong UID/GID/PID lease, denied reads, slow/full DB and queue bounds.

Ubuntu acceptance must establish selected real records through persistence and
fresh read-only retrieval under actual approved identities; confirm runtime
SupplementaryGroups and IPC/DB boundaries without changing journal configuration.
No tests or real-record reads were performed by this documentation pass.

Approval package:

1. Approve protocol/contract/limits, SSH scope, identity and replay comparison.
2. Approve service-only broad journal-read exposure, proposed ingestion account/
   IPC group, ownership/modes and authenticated activation/lease/control policy.
3. Approve tail/empty/gap behavior and recovery limited to an active interval.
4. Approve atomic rejected dispositions/progress and conservative failure handling.
5. Separately authorize implementation and then any account/group/resource/unit
   setup or actual service/live acceptance execution. Nothing here installs or
   starts services. Quantitative retention/storage budgets require measurement
   and approval before unattended production operation.

No Audit/cn_proc live integration, rules/alerts, HTTP/dashboard, correlation,
remediation, automatic logging changes or additional dependencies are included.

## 7. Implemented lifecycle/control binding

The owner authorized completing lifecycle orchestration. Event contract/limits in
section 3 are unchanged. The production backend uses the fixed root-owned
`/run/hids/control.sock` (0600), inherited as systemd FD 3 with checked LISTEN_PID
and exactly one listening FD. Only SO_PEERCRED UID 0 control clients can activate,
revoke or request status. The root client authenticates the systemd-created root
listener, while data IPC authenticates the backend-created hids-ingest listener.
No PID/UID from a JSON request establishes authority.

Root requests have exactly protocol_version=2 and command=status, or those keys
plus source_id/activation_id for activate/deactivate. Source must match protected
configuration; activation is UUIDv4, and revocation names the exact current interval.
Status distinguishes persisted checkpoint state from connected reader PID/failure.
Ready control requests take priority over ready event writes in one SQLite-owning
loop. New source activation never starts services or grants permissions.

An authenticated reader uses exact protocol_version/message_type=reconcile to
obtain backend-owned source_id, activation_id, state, revision, cursor,
boundary_start/end. Boundary requests contain exactly protocol_version,
message_type=boundary, cursor, started_at, ended_at. Identical persisted boundary
replay returns boundary_ack without re-tailing or changing progress. Gap requests
contain exactly protocol_version, message_type=gap, code; they cannot advance a
cursor or activate a source. Root control and reader requests use separate endpoints.

The lease is bound to one credential-verified connection/PID. Five-second request/
output inactivity expires it; replacement authenticates again. Interrupted anchored
collection is recorded without invalidating valid progress. An interrupted initial
boundary becomes a gap, not permission to choose a newer tail. Shutdown/revocation
closes leases; no new poll is issued after the reader observes revocation/cancellation.
One poll already issued may complete; revoked data cannot commit. There is no
automatic journal/service restart or historical backfill.

Configuration is a checked root-owned non-writable-by-others file at
`/etc/hids/m2.json` with exactly source_id, max_records and max_pages; missing/null
budgets are startup errors. The null example is not executable configuration.
Separate deployment/live approval remains required. See the lifecycle record for
source entry points, fixture tests, platform limits and subsequent Ubuntu gates.


## 8. Runtime acceptance configuration

The owner has approved `max_records=100` and `max_pages=4096` for the **current
M2 runtime acceptance only**. These are not permanent production defaults, a
finalized retention policy, or authorization for unattended collection. Future
production budgets require measurement and separate approval.

The protected runtime configuration has exactly three keys: `source_id`,
`max_records` and `max_pages`. Both components validate explicit integer budgets;
missing, null or invalid values fail startup. The persistent machine-specific
source UUIDv4 must be supplied privately and retained in the protected runtime
configuration and private evidence, never in tracked documentation. Neither
budget approval nor configuration creation activates collection.

| Parameter | Approved acceptance value | Meaning and enforcement |
|---|---|---|
| `max_records` | `100` | Python `Store.put()` caps total persisted dispositions: accepted journal events **and** durable native-rejection records, cumulative across activations in this database. Identical replay lookup precedes this check. It does not cap journal reads, runtime, bytes, activation rows or gap rows. |
| `max_pages` | `4096` | Python's SQLite writer sets and verifies `PRAGMA max_page_count` at every startup. It limits main-database pages across all tables and indexes, not just event payloads. It does not establish a retrieval limit or a filesystem quota. |

At a measured page size of 4096 bytes, 4096 pages permit 16 MiB of main-database
pages; verify the actual page size rather than assuming it. WAL and SHM sidecars,
diagnostic logs, exports, backups and acceptance archives consume additional
storage. These settings do not bound total disk growth, and read-only retrieval
connections do not establish the writer's configured page cap.

At the disposition cap, a new disposition raises `configured_storage_capacity`;
existing identical replay can still be recognized without inserting another row.
Page exhaustion can fail any database write, including activation, checkpoint or
gap bookkeeping. A cap below the existing database size fails writer startup
verification; WAL/schema initialization failures likewise prevent readiness.
Per-event storage failures retain the existing unconfirmed-outcome semantics and
stop source acceptance; a database error alone is not proof that no commit occurred.
Previously committed records are not evicted, and limits do not silently advance
checkpoints, discard events, trigger automatic retention or increase themselves.
Later journal rotation/retention may prevent recovery; there is no durable producer
outbox or new backfill guarantee.

The [runtime runbook](../validation/m2-runtime-acceptance/runbook.md) records the
approved acceptance values and exact protected setup procedure. The
[readiness report](../validation/m2-runtime-acceptance/readiness-report.md) keeps
unexecuted Linux/runtime gates distinct from this configuration approval.
