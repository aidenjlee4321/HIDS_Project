# M3 — Linux Audit execution monitoring proposal

**Status:** Accepted decisions and unresolved proposals; not an implementation authorization

**Prepared:** November 8, 2026\
**Decision reconciliation:** November 9, 2026 (owner-directed documentation only)

**Target:** One Ubuntu 26.04 LTS host; initially native AArch64 execution records

## 1. Goals, non-goals and decision boundaries

Collect already-existing Linux Audit execution records, reconstruct each native
Audit event, normalize a privacy-minimized representation in C++20, independently
validate it in Python, and persist it with replay/checkpoint and source-health
information through protected local IPC. Deliver a testable vertical slice before
extending monitoring coverage.

Native reconstruction of records from **one Audit event** is parsing, not v0.2
security-event correlation. No detection rules, alerts, behavioral sequences,
cross-source deduplication, dashboard, HTTP, remediation, automatic hardening,
Audit rule changes, auditd/plugin configuration changes, package installation or
service deployment belong to this proposal's implementation authorization.
This task authorizes documentation only. Accepted design decisions below do not
authorize semantic-parser implementation, pipeline integration or deployment.
Historical experiments and validation reports retain their original results.

Preserve C++20 native processing, Python-only SQLite writes, Unix stream sockets
and JSON Lines, independent validation, root-only human security-data access,
least privilege and local storage. M1/M2 contracts, source filters, databases and
runtime behavior remain compatibility boundaries. Do not turn an Audit event into
an M2 SSH event or replace the existing cn_proc adapter.

[ADR-006](../decisions/006-provisional-process-collection.md) remains the provisional
cn_proc lifecycle decision. This milestone adds Audit execution context where
existing auditing supplies it; Audit does not thereby become an approved replacement
for all FORK/EXEC/EXIT collection. The narrower M3 request takes precedence over
older roadmap references to simultaneous authentication and /proc implementation.
CIS assessment, ATT&CK rule mapping, SSDF release practices and future hardening
remain roadmap context, not new M3 features or claims of coverage/compliance.

## 2. Confirmed repository facts and reusable components

The following inventory records the November 8 source inspection, distinct from
recommendations below; this documentation reconciliation does not revalidate source
behavior or rerun tests. The subsequent structural increment is scoped in section 4.1:

| Existing component | Exact integration boundary |
|---|---|
| `collector/include/hids/journal_collector.hpp` | `Entry`, `JournalIo`, `JournalCollector::start/poll_once/committed/stop` are journal-specific; use their injectable-I/O pattern, not their record type. |
| `collector/src/journal_collector.cpp` | `normalize(const Entry&, ...)` produces journal-native provenance and fields; add a separate Audit normalization function. |
| `collector/src/journal/contract.cpp` | `parse`, `validate`, `canonical`, `identity`, `validate_response` implement the closed M2 contract; SSH pairs and cursor identity cannot represent Audit execution. |
| `collector/include/hids/journal/transport.hpp`, `collector/src/journal/transport.cpp` | `Channel`, `UnixChannel`, `exchange_line`, `request` provide bounded I/O/peer-check patterns. Existing event transport validation is M2-specific; do not call it with an M3 envelope. |
| `collector/src/journal/runtime.cpp` | `ReaderRuntime::start/step/exchange/stop`: authorization before source open, immutable pending bytes, bounded retries and reconciliation. Journal cursor semantics are not file checkpoints. |
| `engine/ingestion/m2_contract.py` | `decode`, `validate_event`, `canonical`, `validate_response`: closed protocol 2, `m2.journal-ssh/0.1.0`, 65536-byte payload/2048-byte responses. Add independent M3 validators. |
| `engine/ingestion/m2_receiver.py` | `PeerPolicy.check`, `Listener`, `Framer`, `service_policy`: Linux peer credentials, verified socket owner/mode, bounded framing; current reader identity is specifically UID 997. An Audit reader must not impersonate it. |
| `engine/ingestion/m2_service.py` | `RootPolicy.check`, `systemd_control_listener`, `Service.control/dispatch/drop`, `load_config`: one configured source, reader lease and global failure state. It is not an implemented multi-source router. |
| `engine/database/m2_store.py` | `Store.transaction/put/boundary/progress`, `get_event`: atomic disposition/progress, duplicate/conflict checks and read-only retrieval. Schema and cursor assumptions are M2-only. |
| `packaging/systemd/hids-{journal,ingest}.service`, `hids-ingest.socket` | Separate non-root reader/ingest identities, service-only journal/IPC groups, root-created control FD 3. Do not give ingestion Audit-log read permissions. |
| Native process collector/parser | `collector/src/{process_collector,process_connector_protocol,linux_process_connector}.cpp` remain separate; Audit is neither cn_proc input nor a `process::NativeEvent`. |

The [Ubuntu runtime report](../validation/m2-runtime-acceptance/ubuntu-runtime-acceptance.md)
is owner-reported: Stages 1–12, native archival tests and cleanup succeeded. Its
Stage 6 establishes client refusal and socket DAC denial, **not** a demonstrated
live backend negative peer-credential test. The historical
[readiness record](../validation/m2-runtime-acceptance/readiness-report.md),
[runbook](../validation/m2-runtime-acceptance/runbook.md), and
[lifecycle record](../validation/m2-lifecycle-validation.md) remain unchanged.

Older architecture/AGENTS/status passages still predate implemented M2. They are
not evidence that its source code is absent. The November 9 reconciliation updates current decision documentation only; it
does not rewrite historical experiments or validation evidence. Existing [Audit authentication research](../research/authentication.md)
establishes some authentication records, not EXECVE coverage on the present VM.

## 3. Integration alternatives and recommendation

### Confirmed upstream properties

Auditd can dispatch records to configured plugins; its configuration directory,
plugin lifecycle, inherited root environment and queues require care. A blocked
plugin can contribute backpressure to auditd and the kernel. Configuring a new
plugin is a change to the Audit logging infrastructure, even if rules are unchanged.
See [upstream plugin documentation](https://raw.githubusercontent.com/linux-audit/audit-userspace/master/docs/auditd-plugins.5).

Auditd's configured log path, raw/enriched format, write enablement, permissions,
rotation and flushing affect what a file reader sees. Do not assume the default
path is the active configuration or that every event was durably logged. See
[upstream auditd configuration](https://raw.githubusercontent.com/linux-audit/audit-userspace/master/docs/auditd.conf.5).

The kernel's multicast Audit bind checks `CAP_AUDIT_READ`; this is distinct from
becoming the controlling audit daemon. Do not register HIDS as the audit daemon,
request `CAP_AUDIT_CONTROL`, change filters or displace auditd. Multicast reception
is live, not a replay source. See
[kernel Audit implementation](https://raw.githubusercontent.com/torvalds/linux/master/kernel/audit.c).

| Approach | Privileges and compatibility | Loss, recovery and operational complexity | M3 assessment |
|---|---|---|---|
| Auditd dispatcher/plugin | Auditd remains stream owner; plugin starts privileged and should drop privilege. Requires an existing approved dispatcher path or new Audit plugin configuration. Target plugin ABI/version must be checked. | Low-latency records; finite dispatcher/plugin queues; slow consumer can affect Audit infrastructure. No inherent durable replay/consumer ACK checkpoint; log/spool recovery is extra design. | Not initial M3: conflicts with existing-logging constraint if a plugin must be added. Future separately approved option. |
| Existing audit log files | Non-root reader with already-authorized directory traversal and file read access; zero Audit control capabilities. Works with auditd's existing file output if enabled; cannot assume ordinary-user access. | Existing logs provide bounded recovery while retained; rotation, partial writes, renames, compression and truncation require explicit handling. Reader lag does not stall auditd, but rotation can overtake it. Disk persistence adds latency and does not prove upstream losslessness. | **Recommended**, conditional on actual read permissions and existing execution records. Best fit for current architecture and no-configuration-change policy. |
| Audit netlink | Unicast daemon/control registration conflicts with auditd and is excluded. Read-only multicast can coexist but needs `CAP_AUDIT_READ`; target kernel, namespaces and group behavior need validation. | Fast live delivery; socket overflow/ENOBUFS and disconnect gaps; no durable cursor or offline recovery. Requires hardened netlink parser, loss diagnostics and a capability-bearing service. Kernel and consumer losses are different. | Not initial M3. Multicast is a technically distinct future option, not proof that all netlink competes with auditd. |

**Recommendation:** read one explicitly configured, root-approved local auditd log
stream and its verified rename-rotation chain. Do not shell out to repeated
`ausearch --recent` or copy whole logs into SQLite. Start only after explicit source
activation; initial activation starts at the current file boundary, without
historical backfill. Catch-up after restart is restricted to the same still-active
interval and retained files. Disabling the source must close file descriptors.

**Coverage blocker:** auditd and general authentication events do not imply
execution syscall rules exist. If existing policy does not emit execve/execveat,
report `execution_coverage_not_observed`/`not_configured` only where evidence warrants
that distinction. HIDS must not install rules to make acceptance pass. Complete
execution coverage cannot be promised under this constraint. Audit syscall rules
would require separate owner design/authorization outside this proposal.

## 4. Native event reconstruction

Audit records with the same `msg=audit(seconds.fraction:serial)` belong to one
source-native event; record types can be interleaved with other events. Node/origin,
source stream and epoch must scope grouping; PID, command name or adjacency are
not grouping keys. A serial alone is not globally unique. See
[upstream ausearch event/checkpoint semantics](https://raw.githubusercontent.com/linux-audit/audit-userspace/master/docs/ausearch.8)
and [auparse timestamp representation](https://raw.githubusercontent.com/linux-audit/audit-userspace/master/docs/auparse_get_timestamp.3).

The EXECVE/PATH/CWD/PROCTITLE/EOE handling below is owner-accepted. Additional
SYSCALL classification/cardinality details remain proposed pending grammar and
scope review, apart from the explicitly required identity fields in section 5.

| Record | Initial semantic policy | Privacy and interpretation |
|---|---|---|
| `SYSCALL` | Exactly one for an execution semantic result; verify architecture/syscall and strict field values. | `exit` is the syscall return, not eventual process exit. Numeric UID roles remain distinct; do not retain raw a0–a3 register values. |
| `EXECVE` | Accept only complete information when supplied; validate argc, argument indices, split fragments, duplicate/conflicting fragments and missing information across all occurrences. | Validate but do not persist argument values. Do not fabricate missing arguments or substitute PROCTITLE. |
| `PATH` | Optional; multiple occurrences allowed, each validated in original order. | Discard contents from normalized/persistent output. Never assume the first PATH identifies the executable. |
| `CWD` | Optional; maximum one, validated when present. | Discard contents from normalized/persistent output. |
| `PROCTITLE` | Optional; maximum one, validated when present. | Discard contents; never a replacement for EXECVE. |
| `EOE` | Structurally validated terminator. | Exclude from libauparse input; structural closure is separate from semantic validity. |

**Accepted completeness policy:** reject incomplete EXECVE sequences rather than
returning partial execution semantics. Support for incomplete sequences is a
future stretch goal. Absence of any EXECVE record is a different condition from
an incomplete supplied sequence. **Unresolved:** classification/eligibility of a
failed SYSCALL with no EXECVE record. Do not silently reject or classify such an
event under a rule that the owner has not approved. This does not relax the
complete-EXECVE requirement for sequences that are supplied.

The supported EXECVE grammar must be established before implementation: argc,
indexed arguments, split/length fragments, cross-record continuity, legitimate
repetition, conflicting or duplicate fragments, and missing information need
explicit rules and representative sanitized fixtures. A repeated record type is
not automatically a duplicate field or a complete argument sequence.

Use architecture-specific syscall tables: candidate AArch64 execve/execveat are
221/281 with Audit arch `0xC00000B7`; verify the target UAPI headers and fixtures
before claiming support. Unsupported/compat architectures must not be guessed.
See [Linux syscall definitions](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/asm-generic/unistd.h).
A successful exec changes the process image, not its PID, and does not prove later
program success. Interpreter scripts/fexecve and failed attempts need specific
fixtures before equivalent coverage is claimed.

### 4.1 Structural authority and semantic eligibility

The local working tree contains a fixture-driven structural increment described
in `tests/integration/M3-README.md`. That separate untracked implementation/test
work is not included in this documentation commit and requires its own review.
The structural boundary owns native identity, original timestamp strings, source
generation/byte positions, ordering, closure, replay checks and volatile contiguous
acknowledgment. This reconciliation changes none of that work or its fixtures.

Closure is not semantic completeness. Timeout, shutdown, capacity exhaustion or
unresolved discontinuity cannot establish complete execution context. Initial
EOE-based semantic eligibility remains a recommendation; additional closure
mechanisms require explicit approval and evidence. PROCTITLE-terminal opt-in in
structural fixtures is not approval to use it as semantic completeness. The
current Event interface must be checked for sufficient closure/completeness
metadata before semantic integration; do not infer unavailable metadata or change
reconstruction implicitly. The proposed exactly-one-SYSCALL check belongs to semantic validation, not a
new requirement for structural reconstruction.
Late/conflicting records remain structural failures, not new executions or
permission to amend immutable results. Durable finalization and restart behavior
remain unresolved in section 6.

### 4.2 Accepted temporary timestamp policy

Only the temporary libauparse input uses three fractional digits:

| Original fraction | Temporary fraction |
|---|---|
| `.1` | `.100` |
| `.123` | `.123` |
| `.123456` | `.123` |
| `.123456789` | `.123` |

Right-pad short fractions and truncate longer fractions; **do not round**. The
validated initial widths are 1, 3, 6 and 9; other widths remain unsupported by this
semantic projection until separately validated/approved, without changing the
structural parser's timestamp acceptance. Reject malformed syntax instead of
repairing it. Original seconds, complete fraction, serial, record bytes, source
byte offsets and identity stay unchanged. Never use temporary millisecond values
for deduplication, durable identity, ordering or checkpointing. Colliding temporary
timestamps cannot merge structural events; each gets its own parser state.
Round-half-up remains historical experimental comparison, not the selected policy.

### 4.3 Accepted fresh BUFFER lifecycle and record accounting

1. Check structural eligibility and approved bounds before allocation. Enumerate
   original records, including EOE for original-size accounting; reject embedded
   NUL and malformed timestamps. Calculate projected non-EOE input length from
   validated source spans with checked addition/subtraction, without constructing
   an unbounded intermediate buffer.
2. Build the complete temporary representation in structural order, excluding EOE.
   Overflow-check `input_bytes + 1`, allocate the bounded input plus a mandatory
   NUL terminator, and populate it directly where practical. Bound any intermediate
   copies and decoding buffers independently. The terminator is allocation overhead,
   not a logical parser-input byte.
3. Call `auparse_init(AUSOURCE_BUFFER, buffer)` once for this event. BUFFER requires
   NUL termination and copies its input; it has no explicit-length initialization
   argument. A NULL result is an explicit parser-initialization failure, potentially
   including library allocation failure, not proof of application `std::bad_alloc`.
4. Drain every library event with `auparse_next_event()` (positive: event, zero:
   exhaustion, negative: error), and traverse every record and field. Independently
   validate semantics using numeric/raw field representations, not interpreted
   account names or host-dependent identifier/path lookups.
5. Compare returned records positionally with expected types and complete temporary
   record representations. Every supplied non-EOE occurrence must appear exactly
   once in order; omissions, unexpected records, extra duplicates, reordering or
   unexplained representation changes reject the complete semantic result.
6. Return one fully validated result or one typed failure, never partial output.
   Use RAII for destruction on all paths and discard temporary sensitive values.

No `AUSOURCE_FEED`, feed/flush calls, callbacks, persistent BUFFER reuse or fallback
parser architecture is part of this accepted approach. libauparse event boundaries
never become structural boundaries. Successful library parsing is not successful
semantic validation. The exact allocation-free internal result/failure API remains
unapproved; no libauparse types should escape the adapter boundary.

### 4.4 Accepted strict validation policy

Reject unknown fields in the initial semantic profile. Unfamiliar record types
must not be silently accepted; the supported native type allowlist and exact
failure classifications still require the grammar review.
Use explicit record-specific allowlists and encoding/numeric validation, including
recognized fields whose values are discarded. Reject duplicate singleton fields,
even when equal; never use first/last-value-wins. Preserve legitimate repeated
EXECVE/PATH occurrences and distinguish fragmented argument syntax from duplicate
singleton fields. Required, missing, malformed and explicitly unset states are
not interchangeable.

The exact Audit lexical and field-specific encoding grammar remains a blocker:
verify quoting, escapes, hexadecimal byte pairs where applicable, numeric ranges,
field names and complete token consumption rather than inventing a full ad hoc
Audit grammar or relying on library acceptance. Native GID fields can be explicitly
recognized and validated for discard without including them in normalized output;
omission from output does not itself make a known source field unknown.

Validated check-and-discard handling of future unknown fields is a **stretch goal**,
not the current compatibility policy. Do not accept unfamiliar fields to improve
coverage. All supplied records must validate, including excluded arguments, PATH,
CWD and PROCTITLE values. Malformed data invalidates the whole semantic result;
no raw values may enter errors, diagnostics, spools or persisted output. Bounded
transient processing does not imply secure erasure of every library allocation.

## 5. Proposed separate M3 event contract

Candidate identifier: `m3.audit-exec/0.1.0`; candidate protocol **3** on an M3-only
endpoint. The external envelope/protocol/encoding remain provisional. The accepted semantic
requirements below constrain the eventual contract but do not finalize it or change
any existing M1/M2 contract/schema.
Keep protocol-2 decoding and M2 schema unchanged. No new mandatory ECS fields or
custom namespace are finalized; these are source-specific transport fields.

The following older wire sketch is provisional, not an approved validator.
Identity value/unset encoding and rejection/health messages still need approval.
Other sketched keys are required unless explicitly nullable. Objects reject extra and
duplicate keys; integers reject Boolean values. Decimal source numbers are canonical
strings to preserve ranges across languages. No NaN/floats or implicit defaults.

| Object/key | Proposed type and semantics |
|---|---|
| `protocol_version`, `contract_version`, `message_type` | Integer 3; exact contract string above; `audit_execution`. Rejections/health/control need separate closed message types before implementation. |
| `source_id`, `activation_id` | Private configured source UUIDv4; current authorization UUIDv4. Never commit machine-specific values. |
| `event_id` | Stable source-position identity described in section 6; not PID, serial or content hash alone. |
| `expected_revision` | Integer 0..2^63−1 for compare-and-swap source progress, not Audit serial order. |
| `provenance` | `{adapter:"audit-log", file_generation:UUIDv4, first_record_offset:decimal, record_locations:[{generation:UUIDv4,start:decimal,end:decimal}]}`; byte intervals, not path-derived trust. |
| `audit` | `{seconds:decimal, fraction:string, serial:decimal, node:null, boot_id:null, record_types:[string], record_count:integer}`. Preserve timestamp precision; first profile rejects remote/non-local node streams rather than merging hosts. Audit log records do not supply a universal boot ID. |
| `execution` | `{arch:string|null, syscall_number:decimal|null, syscall_name:"execve"|"execveat"|null, success:boolean|null, return_value:signed_decimal|null, pid:decimal|null, ppid:decimal|null, executable:string|null, comm:string|null}`. Missing versus malformed states remain explicit. No invented TGID: Audit PID semantics need namespace/thread fixtures. |
| `identities` | Required semantic fields: `uid,euid,suid,fsuid,auid,session_id` (native `ses` maps to the last). Each must be present and valid, with explicit unset supported where defined by the source. No GID fields in the initial normalized contract. Exact numeric/unset wire representation remains pending; missing or malformed required fields reject semantic output rather than becoming null/zero/root. |
| `reconstruction` | Candidate provenance includes basis/issues, EOE presence and record counts. This draft must distinguish structural closure from semantic completeness and lossless source delivery; any incomplete disposition/health representation is separate from a successful execution result and remains unapproved. Incomplete EXECVE is rejected, not emitted as partial execution output; rejected dispositions need their own design. Failed SYSCALL with absent EXECVE remains unresolved. |
| `privacy` | `{arguments:"not_collected_policy",cwd:"not_collected_policy",path_values:"not_collected_policy",proctitle:"not_collected_policy"}`; does not claim those values were absent from native records. |
| `observation` | `{producer_instance_id:UUIDv4, observed_at:UTC_microsecond_string}` captured by C++; Python adds receipt/storage times separately. |

Audit seconds/fraction are the native kernel Audit wall-clock timestamp with source
precision, **not** observation or commit time. Preserve clock reversals and serial
resets without sorting activity by wall time. No native monotonic timestamp is
invented; a local monotonic observation, if later justified, belongs to observation
metadata and its own boot scope. Missing native activity time remains missing and
makes native grouping untrustworthy; create a bounded source rejection/health
record rather than synthesizing activity time. Exact external timestamp encoding/ranges and reason enums remain open; the
accepted temporary library projection in section 4.2 does not change native time.

**Accepted identity requirements:** `uid`, `euid`, `suid`, `fsuid`, `auid` and
`session_id` are mandatory. GIDs are deliberately excluded. Preserve the distinct
real/effective/saved/filesystem/login/session roles. Missing is a validation failure,
malformed is a separate failure, and a recognized emitted unset sentinel remains
explicitly unset. Never turn unset AUID into root or use euid in its place. Verify
field-specific native sentinel forms before choosing an external encoding; do not
invent a universal unset mapping for every UID field.

**Accepted executable-identity direction:** preserve useful `exe` (executable path)
and `comm` (task name), distinct from argv. Their exact normalized names, encoding,
requiredness and text bounds still need contract approval. Paths/names may be
sensitive or attacker-controlled; validate them without granting access or inferring
intent. Argument count is not newly approved for retention.
Arguments, environment, full raw lines, CWD/PATH values and PROCTITLE are excluded
from persistence and diagnostics. Existing raw argument bytes necessarily pass
through bounded reader/parser memory; this is authorized payload processing only
after activation, not a promise that excluded values never enter the process.
Do not put them in crash reports, debug logs or temporary spools. Read access nevertheless exposes the broader log
to the collector; filtering is minimization, not an OS access boundary. Invalid
UTF-8/hex/NUL cannot be replaced silently; either reject the chosen text field or
adopt an explicitly versioned bounded byte encoding after owner review.

Existing structural/pipeline resource candidates (engineering proposals, **not
accepted defaults**):
64 KiB per native record; 256 KiB/256 records per assembled event; 128 open groups;
8 MiB aggregate assembly accounting; 64 KiB normalized JSON payload excluding LF;
2048-byte responses; one pending delivery; 4096-byte read chunks. Enforce the
aggregate cap before appending, so per-group limits cannot multiply into an
unbounded allocation. Propose executable 4096 bytes, comm 256 bytes and closed
bounded diagnostic arrays. Oversized arguments can make an otherwise legitimate
event exceed the native budget: report a bounded rejection/incomplete event, do
not claim truncation yields completeness. Parser/library overhead must be measured
in addition to these application budgets. Retention/page/row budgets are separate
owner decisions; M2's 100/4096 acceptance values do not become M3 defaults.

### Future independently configurable retention

The owner accepts a future design goal of independently configurable retention
for selected security-information categories: executable path, process name,
arguments, working directory, filesystem paths and process title. This is not an
M3 implementation requirement and does not expand current retention.

Defer exact toggleable fields, defaults, global versus per-source scope,
configuration format/interface, access controls, disabled-retention behavior,
and whether validation/transient processing remain enabled. Do not infer that
turning retention off will stop processing, or that processing must continue; that
future behavior is deliberately undecided. For current M3, validate excluded data
and retain no arguments, environment, PATH values, CWD values, PROCTITLE or raw lines.
Retention duration, database/disk budgets and migrations remain separate decisions.

## 6. Identity, checkpoints and restart

### Recommended identity model

Persist an ingestion-assigned file-generation UUID with verified source device,
inode, creation observations and bounded prefix anchors; device/inode alone can be
reused. Keep generation identity through rename rotation. Do not treat a new reader
instance or pathname as a new source generation. The C++ reader reconciles this
registry through authenticated IPC; Python alone writes its durable state.

Candidate `event_id = "a1." + source_id + "." + first_record_generation + "." + first_record_byte_offset`.
This identifies one physical reconstructed event in one configured log lineage.
Preserve native timestamp/serial/node grouping separately. It is not a universal
identity across copied logs or different Audit sources; such imports/backfill are
excluded. Record spans can cross files; the first-record location remains the
identity anchor. An orphan EXECVE group is incomplete execution evidence, not
proof of a successful syscall; missing SYSCALL outcome must remain unknown. Never infer chronological ordering from serials or event IDs.

Identical replay compares independently validated, canonical source content and
privacy/reconstruction profile. Exclude observation, activation and transport
revision; preserve first stored observations. Same ID with different valid canonical
content is `id_conflict`; do not overwrite. Retry exact immutable pending bytes.
Unsupported versions are rejected before collision checks. Lost ACK means
unconfirmed delivery: reconcile, then replay the same ID/content. ACK only after
commit; no exactly-once delivery claim or C++ database writes.

### Checkpoint model and unresolved completion durability

Use a **contiguous consumed-byte frontier**, not the most recently completed
Audit serial: interleaved event A may still be open when later event B commits.
An atomic Python transaction inserts an event/rejection disposition and updates
only a proven contiguous frontier under expected revision and current activation.
Never advance beyond an unresolved earlier group. Record handling of unrelated
(non-execution) records as bounded scan progress, so a quiet execution stream does
not require rereading an entire log forever. Scan-progress requests must prove no
unresolved group was skipped; they are not arbitrary collector checkpoint writes.

**Blocking design choice:** timeout-finalized incomplete groups and pending groups
must reconstruct identically after a crash. Keeping only a byte offset is
insufficient: timeouts, late records and interleaving can change the canonical
result. Recommend durable bounded finalization decisions (group key, span,
completeness/profile and deadline decision, without raw arguments) in the same
Python-owned transaction, plus conservative replay from the earliest unresolved
record. An alternative is durable sanitized pending assembly state. Exact tables,
state transitions and scan/frontier proof require a focused contract addendum and
failure-injection vectors before coding; do not claim M2 cursor semantics solve it.
This is source reconstruction bookkeeping, not a detection correlation graph or a
new general-purpose durable outbox.

For identifiable malformed/oversized execution groups, propose durable minimal
rejected dispositions with source spans/reason and atomic checkpoint handling.
If record framing/identity or rotation continuity cannot be trusted, stop at the
last safe frontier and report a gap; do not invent an identity or skip bytes to
make progress. No automatic retry of ambiguous database repair or archive import.

## 7. Activation, rotation, ordering and failure behavior

1. Before explicit root authorization, inspect only approved source metadata and
   permission evidence. No Audit payload reads or active netlink subscription.
2. After authorization, securely open the pinned local regular file, capture its
   identity/size as the initial tail boundary, and persist that boundary before
   emitting events. Recheck rename/truncation races. Boundary verification may
   require limited post-authorization framing reads; do not emit pre-boundary data.
3. A line or multi-record event already in flight at activation can straddle the
   boundary. Mark boundary-overlap groups incomplete/excluded with an explicit
   disposition; do not back-read old records or call them complete. Exact handling
   of headerless partial first lines belongs in the contract addendum.
4. Keep old descriptors through rename rotation and discover only an approved,
   verified successor. Resolve retained generations on restart using authenticated
   generation metadata and integrity anchors; never compare filenames as cursors.
   Stop if succession cannot be proved. Copytruncate, unexpected replacement,
   missing generations, inode reuse, compression or permission loss must not
   silently reset to the current tail. Initial M3 does not auto-decompress archives.
5. Reconstruct interleaved groups independently within bounds. Duplicate byte
   delivery at an identical location is not two native records; repeated distinct
   record locations are not automatically duplicates. Preserve type multiplicity;
   conflicting duplicates or late data after finalization produce diagnostics.
6. Resume only within the still-authorized interval. Reboot/daemon reset or uncertain
   historical boot attribution does not justify inventing a boot ID. If native
   grouping identity may collide across an unproven stream transition, block for
   review instead of combining records. No automatic reactivation or backfill.
7. Backpressure pauses file reading within fixed memory bounds. Auditd continues;
   retained files may disappear before catch-up. On capacity, slow receiver, lease
   expiry, access loss or uncertain commit, expose source-local failure, preserve
   committed data/checkpoints, and stop unsafe progress. No disk spool by default.
8. Cancellation is cooperative and bounded; no file/SQL/socket operations in signal
   handlers. Flush only justified bounded dispositions; preserve safe resume state
   if shutdown interrupts reconstruction. Database failure is not proof of noncommit.

Health must distinguish source missing, unsupported format/architecture, access
denied, execution coverage unobserved, Audit not configured where proven, idle,
active, interrupted, malformed/incomplete, storage failure, lag and possible gap.
A readable empty file or zero matching events is not healthy coverage evidence.
Expose assessment freshness and counters with provenance. Audit global lost/backlog
counts are not this reader's drop count; serial gaps are not a loss estimate.

For initial M3, ingest only already-available, authorized health evidence; do not
add `CAP_AUDIT_CONTROL` merely to query status, signal auditd, or change its reporting
configuration. Without an approved status source, kernel backlog/lost counters are
**unknown**, not zero. Separate file-reader drops, reconstruction rejections,
retention gaps and confirmed source counters. Report diagnostic persistence failure
out-of-band without claiming it was stored.

## 8. Security, privileges and ingestion integration

Recommend a dedicated non-login `hids-audit` reader, distinct from `hids-journal`
and `hids-ingest`; exact account/group IDs and creation require owner approval.
No permanent privileged journal/Audit-group membership is assumed. If the existing
Audit log already grants an appropriate non-root read group, propose service-only
membership after approval and actual target checks. Reject shared groups that
allow unintended ordinary-human security-data access. No new log ACLs, permissions,
`log_group` setting or auditd configuration are authorized.

If existing logs are root-only, the non-root file-reader proposal is **blocked**
on a separately approved narrow access design. Do not quietly run the full parser
as root or grant `CAP_DAC_READ_SEARCH`/`CAP_DAC_OVERRIDE` to bypass this blocker.
A minimal privileged file-descriptor broker is an alternative requiring its own
review of fixed paths, rotation, lifetime, and compromise impact, not an implied
M3 component. Ordinary-user feasibility in cn_proc research says nothing about
Audit log readability.

| Component/resource | Proposed permission boundary |
|---|---|
| C++ Audit reader | Read only approved source files; no Audit control, journal group or SQLite access. New log opens only during an active interval. |
| Python ingestion | Existing unprivileged `hids-ingest` responsibility; receives normalized M3 frames, independently validates and alone writes M3 SQLite. No Audit-log access. |
| M3 data endpoint | Separate proposed `/run/hids/ingest/audit.sock`, ingest:hids-ipc 0660, protected parent; reject stale/symlink sockets. Both sides authenticate exact approved UID/primary GID through SO_PEERCRED; bind lease to PID/activation. |
| Root control | Existing root-only authorization principle and genuine socket activation; add an explicitly versioned M3 control binding without changing protocol-2 control messages. No endpoint accepts arbitrary file paths or commands from peers. |
| Database/evidence | Proposed separate `/var/lib/hids/m3` ingest-owned 0700, files/sidecars 0600; service-only access differs from human authorization. Reader cannot traverse it. |

Do not just send protocol 3 into `Service.dispatch()`: M2 hardcodes one source,
protocol, lease and global failure. Recommend an additive, tested multi-source
routing layer in the existing ingestion service, with M2 and M3 independent
validators, stores, activation/lease and source-failure state. Keep M2 wire behavior
and three-key configuration unchanged; give M3 its own protected configuration.
Bound dispatch work/SQLite waits so a failing or busy Audit source cannot starve
M2 control/revocation or collection. One Python process owns all its SQLite writes.

This necessary future integration is **not implemented or approved here**. Shared
process crash/disk exhaustion remain common failure domains. If regression-safe
source isolation is impractical, propose a separate M3 ingestion worker using the
same protected architecture for owner review rather than silently redesigning M2.
The routing/control/configuration decision is a prerequisite to implementation.

Compromise tradeoffs: the reader can see broader raw Audit data than its retained
whitelist; ingestion compromise exposes normalized storage within its identity's
access. It must not gain log access or privileged control. Root compromise remains
outside confidentiality guarantees. Avoid logging raw rejected records, arguments
or private paths in error text; prevent core dumps in approved service policy.

### 8.1 libauparse filesystem behavior and non-root parsing

**Accepted:** never run semantic parsing as root or grant extra capabilities merely
for parsing. Initialization loads userspace configuration and may attempt to open
the configured log for validation, even with BUFFER input. Successful parsing
without log-read permission does not establish filesystem independence or absence
of attempted access. Verify actual opens, permissions and behavior under the eventual
production identity; synthetic ordinary-user tests do not prove its access policy.
Do not modify host Audit configuration to accommodate the library.

The latest owner decision does **not** require a separate parsing daemon, curated
RootDirectory/RootImage or elaborate filesystem isolation as an implementation
prerequisite. Earlier recommendations to mandate that design are superseded.
Introduce additional isolation only if actual-identity testing demonstrates a need,
then obtain approval for the specific boundary. Production filesystem isolation,
source acquisition and actual non-root Audit-log permissions remain unresolved;
no access grant or service configuration is approved here. Keep existing least-
privilege separation and root-only human access. No undocumented configuration
path override or claim that BUFFER avoids configuration/log access is permitted.

## 9. Dependencies and verification gates

Existing: C++20/GCC 15.2.0 target, vendored nlohmann/json 3.12.0, Python standard
library/SQLite, Unix sockets and existing test scripts. No C++ SQLite dependency,
message broker, new build framework or Python OS collector is proposed.

Recommend **libauparse** rather than a new full Audit grammar implementation.
Ubuntu's official Resolute source package lists `libauparse-dev`; published indexes
show audit userspace 4.1.2 packaging (base `1:4.1.2-1build1`, updates
`1:4.1.2-1ubuntu0.1`). These were initial repository listings, not a production pinned minimum;
the later owner-reported tested version is recorded below, and architecture/pocket candidates must be checked on the
actual machine. See [Ubuntu audit source package](https://packages.ubuntu.com/source/resolute/audit)
and [Ubuntu updates package index](https://packages.ubuntu.com/resolute-updates/allpackages).

Upstream v4.1.2 auparse source declares LGPL-2.1-or-later. Audit userspace as a
whole has other licensing; do not label every component LGPL. Review packaged
copyright/transitive library obligations and the exact public headers before
approving linking/distribution. See [versioned auparse source](https://raw.githubusercontent.com/linux-audit/audit-userspace/v4.1.2/auparse/auparse.c).

The accepted library path is the fresh BUFFER lifecycle in section 4.3, not the
earlier FEED/callback recommendation. Consult the pinned
[BUFFER initialization API](https://github.com/linux-audit/audit-userspace/blob/v4.1.2/docs/auparse_init.3)
and [v4.1.2 implementation](https://raw.githubusercontent.com/linux-audit/audit-userspace/v4.1.2/auparse/auparse.c).
Use raw numeric identity values and explicit application validation. Library
acceptance or record-ready behavior cannot establish semantic completeness.

The owner reports Ubuntu 26.04.1 ARM64 experiments with libauparse 4.1.2 and package
version `1:4.1.2-1ubuntu0.1`, ordinary-user initialization under five synthetic
permission configurations, and fresh BUFFER reordered-record coverage with EOE
excluded. Temporary three-digit truncation is the selected policy; persistent
BUFFER is rejected. These bounded reports are not complete grammar, production
service access, live Audit coverage or long-running reliability validation. No new
experiment is performed or historical report altered by this reconciliation.
Production dependency/version/distribution policy remains open despite that tested
version; preserve macOS validation without unconditional Linux linkage.

Read-only target preflight to request separately: package/candidate versions for
`auditd`, `libauparse-dev`, relevant runtime libraries and any required `libaudit-dev`;
compiler header/link availability and transitive dependencies; effective auditd
log path/format/write/rotation configuration; actual service identity access;
existing rules and kernel status only under already-authorized read permissions.
Do not dump raw logs/arguments, install packages, signal services or grant privileges.
Representative source-derived EXECVE grammar/coverage evidence still requires
separate authorization; synthetic fixtures alone do not establish live coverage. Headers were not found at standard host include paths in this
macOS inspection; that does not establish Ubuntu package availability or absence.

## 10. Tests, phases and acceptance criteria

Preserve unchanged native collector/backend suites, production link smoke, 62 M1
and 35 M2 shared vectors, M1 native/contract/Python/policy/launcher tests, existing
Linux M1 integrations, M2 storage/fixture/lifecycle/runtime-process integrations,
automation and archival tests. Reuse `tests/integration/validate_m2_offline.sh`
and existing sanitizer procedure; keep Linux-only skips distinct from passes.
No regression suite or live test was executed for this documentation-only proposal.

The local structural increment and fixture limits are described in the workspace
file `tests/integration/M3-README.md`, which is not part of this documentation
commit. Do not describe that separate work as a published semantic parser or
production durable file reader.
Before any new semantic implementation, review its Event metadata, accepted field
requirements, strict allowlists/fragment grammar, failure API, production bounds
and actual-identity filesystem plan. No structural source change is implied.

Required future semantic vectors: all mandatory UID/AUID/session roles, explicit
unset/missing/malformed distinctions, native GID validation without output, useful
exe/comm distinct from argv, complete/split EXECVE and missing/conflicting fragments,
unknown-field/type and duplicate-singleton rejection, optional/repeated PATH and
optional singleton CWD/PROCTITLE, positional coverage across every library event,
original identity/byte-position preservation under truncation, embedded-NUL rejection,
preallocation overflow/bounds, NULL initialization, allocation/traversal failures,
no partial output and no sensitive-value diagnostics. Absent EXECVE on failed
SYSCALL needs an approved classification before its acceptance expectation is set.

The phases below remain a proposed full-pipeline roadmap, not renewed authorization
or a requirement to build IPC/SQLite before the isolated semantic increment:

| Phase | Deliverable and gate |
|---|---|
| 0 — Evidence and owner decisions | Verify read path, existing exec coverage, dependency/license, service permissions and representative sanitized fixtures; approve contract and reconstruction/checkpoint rules before coding. If unavailable, report graceful unavailability rather than change Audit. |
| 1 — Fixture/native reconstruction | Proposed `collector/include/hids/audit_collector.hpp`, `collector/src/audit/{record_parser,event_assembler,contract}.cpp`, sanitized `tests/fixtures/audit/` and independent shared vectors. Positive/failed execve/execveat; AArch64/unsupported arch; raw/enriched formats; encoded strings, fragments, repeated keys/types, EOE/PROCTITLE/timeout, missing/malformed/oversized fields, unrelated/interleaved events. No live subscription. |
| 2 — Protected fixture pipeline | Proposed `engine/ingestion/m3_{contract,receiver}.py`, `engine/database/m3_store.py`, M3 endpoint/approved router, schema vectors and two-process tests. Valid and invalid frames; split/coalesced/LF-at-limit; wrong peer before payload; unauthorized/stale activation; canonical duplicate/conflict/version ordering; lost ACK; commit uncertainty; read-only retrieval; bounded slowdown and storage failure. |
| 3 — File source/recovery | Injectable `AuditFileIo` with descriptor-relative pinned paths; proposed `collector/src/audit/{linux_audit_file,runtime}.cpp`. Synthetic files only: partial writes, interleaving and contiguous frontier, event crossing rotation, rename/replacement, inode reuse, truncation, missing/compressed generations, changed ownership, restart before/after event/checkpoint/ACK, timeout decisions and late records. Prove immutable identities across each interruption. |
| 4 — Health/security and fairness | Separate source health/cancellation, source-local errors, denied metadata/status evidence, bounded memory/record/group/scan queues and fresh health. Verify M3 overload cannot alter M2 contract or starve its activation/revocation path. Proposed packaging artifacts only; no deployment without approval. |
| 5 — Separately authorized Ubuntu acceptance | Validate intended identities, existing output/rules, actual read access and encoding, controlled harmless execution without adding rules, exact native grouping through C++→IPC→Python→SQLite/retrieval, duplicate/restart behavior and safe shutdown. Record every missing/failed/skipped branch and preserve evidence privately. |

Acceptance requires identifiable execution records from **existing** configuration,
not merely a running auditd or a readable empty file. Every source byte/checkpoint
advance must have a reproducible disposition; no open group may be skipped.
Incomplete/unsupported records must stay distinguishable from complete successful
execs. Confirmed kernel loss, possible retention gaps and collector errors must
remain separately attributable. Demonstrate identity preservation, first observation
preservation, atomic persistence and healthy continued M2 operation when M3 is denied
or fails. Report measured idle/burst/lag/memory/disk costs before setting production
budgets; do not claim exhaustive monitoring or exactly-once delivery.

## 11. Owner decision register

**Accepted** means an owner-approved design requirement/direction, not permission
to implement. **Provisional** means a proposal requiring review; **Unresolved**
means evidence or a decision is still needed. Future goals are not initial scope.
Earlier A-01–A-10 identifiers are retained with their accepted subdecisions separated
below rather than marking each broad integration proposal accepted wholesale.

| ID | Subject | Status and boundary |
|---|---|---|
| A-01 | Existing Audit logs and actual execution coverage | **Provisional** initial source: existing log files only; **Unresolved** actual read path/output/coverage. No rule/configuration change. |
| A-02 | Actual non-root acquisition identity and permissions | **Unresolved**; no new accounts, access grants, privileged broker or automatic escalation. |
| A-03 | Architecture, success/failure and closure scope | **Provisional** native AArch64; target UAPI/fixtures and initial completeness allowlist need review. Failed SYSCALL without EXECVE remains **Unresolved**. Preserve ADR-006. |
| A-04 | External M3 envelope, encoding and schema | **Provisional** `m3.audit-exec/0.1.0`/protocol 3; accepted semantic requirements below do not finalize wire keys, ECS, IPC or database schema. |
| A-05 | Durable finalization, late records, generations, rotation and checkpoints | **Unresolved**; volatile structural acknowledgment is not durable persistence or restart proof. |
| A-06 | Multi-source ingestion routing, control and SQLite | **Provisional**, separate approval/authorization; unchanged M1/M2 boundaries and Python-owned writes. |
| A-07 | Dependency/version/license and distribution policy | **Unresolved** production policy; libauparse 4.1.2 is owner-reported tested, not a finalized version policy or installation authorization. |
| A-08 | Retention/storage, queue/retry/resource and restart budgets | **Unresolved**; no experimental limits or M2 acceptance values become M3 defaults. |
| A-09 | Audit lost/backlog health evidence | **Unresolved**; no CAP_AUDIT_CONTROL or invented zero counts. |
| A-10 | Implementation, live testing and deployment | Separate authorization required; this task permits documentation only and does not revoke or expand the existing structural increment. |
| A-11 | Required `uid,euid,suid,fsuid,auid,session_id` | **Accepted**; no partial normalized success when required information is missing/malformed. |
| A-12 | Omit GIDs from initial normalized contract | **Accepted**; recognized native GIDs can be validated and discarded. |
| A-13 | Identity/session states | **Accepted** distinction: explicit unset, missing and malformed. Never map unset AUID to root/euid. Exact field-specific sentinel encodings remain **Unresolved** pending source verification/contract review. |
| A-14 | Complete EXECVE information | **Accepted**; validate argc, indices, fragments, conflicts/duplicates and missing information; reject incomplete sequences. Exact verified grammar remains a prerequisite. Absence is not incompleteness. |
| A-15 | Incomplete EXECVE support | **Future stretch goal**; no fabricated arguments or PROCTITLE substitution. |
| A-16 | Optional PATH, multiple occurrences | **Accepted** validate-and-discard contents; never infer executable from first PATH. |
| A-17 | Optional CWD/PROCTITLE, maximum one each | **Accepted** validate-and-discard contents; no argument fallback. |
| A-18 | EOE | **Accepted** structural validation and exclusion from library input; structural closure remains separate from semantic validity. |
| A-19 | Unknown fields and duplicate singleton fields | **Accepted** reject using record-specific validation; no last-value-wins or compatibility bypass. Exact native type allowlist/failure classification remains subject to grammar review. |
| A-20 | Future validated-discard unknown fields | **Future stretch goal**, not current acceptance behavior. |
| A-21 | Temporary timestamp truncation | **Accepted** section 4.2; originals authoritative, no rounding or temporary-time identity/order/checkpoints. |
| A-22 | Fresh `AUSOURCE_BUFFER` per structural event | **Accepted** complete bounded NUL-terminated input, all returned events/records/fields, positional accounting, independent validation and RAII; no FEED or persistent state. |
| A-23 | Non-root parsing and filesystem access verification | **Accepted** no capabilities merely to parse; document/verify configuration and possible log access under actual identity, no host configuration changes. |
| A-24 | Additional production filesystem isolation | **Unresolved/conditional** on demonstrated need and approval. A separate parsing daemon or mandatory curated filesystem is not approved/required by default. |
| A-25 | Executable identity retention | **Accepted direction** preserve useful exe/comm separately from argv; exact encoding/requiredness/bounds remain **Unresolved**. No argv/environment/CWD/PATH/PROCTITLE retention. |
| A-26 | Independently configurable category retention | **Future design goal**, not an M3 implementation requirement. |
| A-27 | Exact retention-toggle specification | **Deferred** fields, defaults, scope, interface, access controls, disabled behavior and transient validation/processing policy. |
| A-28 | Internal result/failure API and production safety limits | **Provisional** allocation-free typed failures/no partial output; exact API, numeric bounds and library/process memory enforcement remain unapproved. |

**Next review:** verify structural interface prerequisites and Audit field/fragment
grammar, resolve absent-EXECVE failed-syscall classification, exact identity/unset
and executable text encoding, and finite production bounds. Actual source access,
coverage, filesystem behavior and durable recovery still require their own evidence.
Then obtain separate semantic implementation authorization; IPC/SQLite integration,
permissions/deployment and live testing need separate approval. No automatic source,
privilege, retention or contract expansion follows from this documentation update.
