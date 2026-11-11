# M3 Audit implementation and validation

The first M3 runtime build passed the Ubuntu acceptance round described below,
including systemd, root activation, privilege separation, current-tail exclusion,
revocation, backend restart and a native Audit execution. See
[runtime integration](#activation-and-restart-integration) and the
[installed-runtime acceptance result](#installed-runtime-ubuntu-acceptance).
The owner-approved [health checker](#installed-health-checker-acceptance) now supplies
scoped kernel and available dispatcher observations. Quiet-source probes distinguish
clean Audit startup from a dispatcher reload regression; see the evidence below.
The [latest increment](#per-event-timeouts-and-sustained-workloads) adds durable
per-event timeout rejection, late-record suppression, bounded native payload
retirement, 35 Python tests, 21 native groups and installed storage/load evidence.

## Initial structural increment

This increment implements an internal C++20 structural component only, under the
owner's parser/test authorization. It opens no source, socket, database or kernel
interface. It does not modify M1/M2, Audit policy, service identities or privileges.
The [M3 architecture proposal](../../docs/implementation/m3-linux-audit-spec.md)
remains proposed; its unresolved production contracts are not approved implicitly.

## Implemented boundary

- `collector/include/hids/audit/reconstruction.hpp`: internal `Record`, `Key`,
  immutable finalized `Event`, `Limits` and `Reconstructor` interfaces.
- `collector/src/audit/record_parser.cpp`: bounded structural header parser for a
  complete LF-terminated Audit record, with exact native seconds/fraction/serial,
  type and byte span. EOE is accepted only with an empty payload, so unexpected
  trailing bytes cannot trigger structural finalization. Local unprefixed headers
  only; no `node=` or enriched-format support claim. Fractions are preserved
  verbatim at 1–9 decimal digits; this is an internal framing profile, not an
  approved normalized timestamp contract.
- `collector/src/audit/event_assembler.cpp`: source-position-ordered reconstruction
  across interleaved native identities, all six requested record types, repeated
  records, immutable terminal/timeout/shutdown decisions, deterministic emission,
  capacity diagnostics and caller-acknowledged contiguous frontier.
- `collector/src/audit/execve_validation.cpp`: offline validation of argument
  completeness on EOE-closed groups. Returns only a static result code.
- `tests/fixtures/audit/structural-exec.log`: invented sanitized sample, not a raw
  Ubuntu capture or evidence of installed execution auditing.
- `tests/unit/m3_audit_reconstruction_test.cpp`: assertion-based offline tests.

**This is not a complete Audit payload parser or a normalized execution event.**
The provisional offline lexical profile requires one ASCII space before each
field and printable ASCII values. Quotes cannot contain spaces or embedded quotes.
Backslashes are literal and quoted empty values pass lexical validation.
The target Ubuntu spacing and representation still require verification.
A syntactically valid field such as `pid=not-an-integer` is accepted
structurally and explicitly tested as such; no successful execution is inferred.
Missing header identity/payload, invalid header numerics, NUL/CR/newline injection,
overflow and oversized records are rejected. Field semantics,
architecture/syscall classification and raw/enriched grammar
require the separately proposed libauparse integration and dependency verification.
No ad hoc full Audit grammar or M2 contract substitution has been introduced.

The offline EXECVE profile uses one leading `argc`, contiguous argument indexes,
and contiguous fragment indexes with a declared length. Following the upstream
Linux serializer, the length counts quoted content bytes or hex digits. Each
fragmented argument uses one encoding throughout. Synthetic fixtures exercise
this profile pending verification against the target Ubuntu kernel's RAW output.
Successful validation establishes EXECVE completeness under this profile. The structural assembler still emits
incomplete dispositions for its caller to handle.

The proposal's native whitelist/normalized privacy fields are not serialized here.
Native bytes, including potentially sensitive arguments, live in bounded memory
for reconstruction/replay checks. They must not be logged, persisted or exported
as normalized data. No routine prints native values. Only sanitized fixtures are
used. A downstream owner must respect payload lifetimes and disposal policy.

## Finalization, duplicates and byte frontier

The caller supplies complete lines, contiguous absolute byte offsets, and a
nondecreasing local monotonic millisecond tick. This component does not read a
clock or buffer split lines. The final LF is framing, not retained native payload.
Malformed/unsupported input or resource failure is sticky; unsafe progress stops.
There is no skip-to-next-line or automatic repair. Existing ready outcomes remain
inspectable, but further acknowledgments cannot move a failed component's frontier.

Records can arrive in any order within one still-open event; source byte order is
preserved. EOE seals a group. PROCTITLE-as-terminal requires explicit fixture/profile
opt-in, disabled by default until semantic/profile validation is available. A
terminal marker means **structural closure**, not semantic completeness or proof
that the kernel delivered every required record. An orphan EXECVE/EOE does not
become a valid execution event. Timeout and shutdown outcomes are explicitly
nonterminal/incomplete. Expiration is caller-driven; retries never renew deadlines.

Replay of identical bytes at the same known position is idempotent. Equal payload
bytes at a new position remain a distinct record, counted but not silently dropped.
New-position records for a finalized identity fail with `late_record`; the original
outcome is never amended. A conflicting same-position replay fails. No count of
lost events is inferred from serial gaps. Unknown types are retained structurally,
without a claim of normalized support or execution classification.

`acknowledge(token)` means a trusted caller accepted a finalized disposition. It
is **not** a SQLite commit or a durable checkpoint API. A finalized but unacknowledged
event blocks the byte frontier, even when later events have been acknowledged.
The frontier also never splits a known event across its first and last record:
interleaved acknowledged event A cannot be partially skipped around unresolved B,
which would leave orphan A records on replay. Overlapping ranges may therefore
hold an entire prefix back until all intersecting outcomes are acknowledged.

`volatile_frontier()` is internal, memory-only state for one caller-established
source epoch/generation. Restart tests replay supplied fixture bytes from a safe
boundary and demonstrate deterministic reconstruction and external duplicate
requirements. They do **not** establish file-generation continuity, durable IDs,
committed disposition replay, rotation or late-record detection across processes.
Constructor offsets alone cannot prove any of those properties. No snapshot or
persistent assembly-state format is implemented.

A regression deliberately demonstrates the unresolved timeout issue: the same
initial record may timeout before a crash, then gain EOE during replay. Persisting
only a byte offset cannot reproduce the earlier decision. Proposed next step:
review/approve Python-owned bounded finalization decisions and a generation/late-
record registry before any frontier becomes durable. No durable outbox or irreversible
storage/IPC architecture choice is made by this increment.

## Resource bounds

Default **internal fixture limits**, configurable by the trusted caller, follow
proposal candidates: 64 KiB record payload, 256 KiB/group including LF framing,
256 records/group, 128 open groups, 8 MiB charged retained bytes and 2000 ms first-
record timeout. Added replay-history bounds are 4096 records and 256 finalized
groups per instance. These are not approved production budgets or retention policy.

The aggregate bound is checked before creating a retained record. Charging includes
input bytes plus 1024 bytes structural allowance per record; explicit record/group
counts also bound metadata and containers. Actual allocator/RSS overhead is not a
performance guarantee and requires measurement. Records shared with caller-owned
outputs can outlive the reconstructor; caller retention must be bounded separately.

Finalized history is intentionally retained within these limits, including after
acknowledgment, so old positions and late identities remain checkable. Capacity
failure does not evict tombstones or silently start a new epoch. This bounded
fixture implementation is therefore **not a long-running production reader**.
Capacity finalization/persisted rejection policy remains a production decision;
this component fails closed without inventing a successful disposition.

## Build and tests

From the repository root, with an existing C++20 compiler:

```bash
bash tests/integration/validate_m3_reconstruction.sh
bash tests/integration/validate_m3_reconstruction.sh --sanitize
```

The runner uses `-Wall -Wextra -Wpedantic -Werror`; sanitizer mode adds ASan/UBSan.
It introduces no dependency or build framework. Binaries remain in newly created
private temporary directories outside the repository. No root execution is needed.

Fourteen test groups cover the six-record fixture, structural malformed/missing input,
interleaving, earlier incomplete events, frontier range closure, explicit incomplete
finalization, out-of-order record types, duplicate/conflicting/late records,
clock reversal, timeout ordering, PROCTITLE opt-in, empty-EOE-payload enforcement,
all capacity classes, fixture restart/replay, timeout ambiguity and deterministic
output, and EXECVE fragment length and encoding checks. Other field semantics and Ubuntu/libauparse behavior remain untested,
explicitly outside this structural increment's claims. Preserve existing M1/M2 suites
and contracts unchanged.


## Verification record

On November 9, 2026, all 14 M3 offline groups passed on macOS arm64 with
Apple Clang, both normally and with ASan/UBSan. The broader M1/M2 offline
regression runner passed once it had permission to bind temporary Unix sockets.
Linux-only cases skipped on macOS remain outside this result. No live Audit
source or Ubuntu libauparse integration was exercised.

The reconstruction and EXECVE build passed all 14 groups in the original Linux UTM guest, normally and
with ASan/UBSan. The archive SHA-256 was
`4d53300eea734273b3194bbe532c7ce1565f43a7ccf238d0ff5dfebb7333def2`
on both the Mac and guest. A one-shot transfer on the private VM network
worked around the 9p share read failure. The Linux run used synthetic fixtures
and did not exercise the installed Audit source or link libauparse.


## Offline semantic fixture

`validate_execution` composes EOE-closed EXECVE validation with a narrow,
synthetic AArch64 event profile. It requires a single supported SYSCALL, checks
execution outcome and required identity fields, rejects duplicate and unknown
fields, and checks PATH indexes and counts and optional singleton context.
The output retains native time and serial, numeric identities, Base64 executable
and command bytes, and context counts or presence. Argument values, GIDs, and
context payloads are excluded from the output.

The fixture profile uses UINT32_MAX as explicit unset for AUID and session.
Its PATH allowlist covers only the three synthetic fixture fields. Native field
coverage, markers, target encoding, and libauparse cross-checks remain open.
This internal result has no wire format or persistence.

On macOS, the expanded suite passed with sanitizers. The execution fixture checks
Base64 output, explicit unset AUID, failed execution with complete EXECVE,
missing EXECVE, duplicate and unknown SYSCALL fields, and PATH count mismatch.
The expanded suite also passed all 14 groups on the original Ubuntu AArch64
guest, both normally and with ASan/UBSan. The verified archive SHA-256 was
`8a28a34bf646adb00d9be59b91a6e6631cee7ae013a788d834818bb97c4be44c`.
This run exercised synthetic inputs only.

### Installed Audit library smoke test

The original Ubuntu AArch64 guest loaded its installed `libauparse.so.0`
through a temporary Python ctypes probe. Two fresh NUL-terminated BUFFER
states used synthetic events with EOE removed. The probe verified exact
record text, traversal of an EXECVE split across records, and exhaustion of
both the record and event iterators. No Audit log was opened. This result
covers the runtime calls exercised by the probe. The linked C++ check below extends this runtime probe. Native RAW compatibility
and live reader acceptance remain pending.

### Offline SQLite progress ledger

Run `python3 -B -m unittest discover -s tests/unit -p test_m3_progress.py -v`
from the repository root. Nine tests passed on macOS. The ledger fixture
covers one activation and generation in a private SQLite WAL database.
It commits sanitized record positions before admission, resolves only owned
positions on rejection, and suppresses interrupted identities after reopen.
Fault injection verifies that failed scan and frontier writes roll back their
transactions. A closed, independently validated execution payload is committed
with its first-record offset and frontier after durable EOE registration.
An identical retry after reopen returns duplicate. A conflicting retry fails,
and a complete event interrupted before commit cannot be accepted on recovery.

The fixture uses one row per record and assumes an external serialized owner.
Production bounds, leases, rotation, the C++/Python wire contract, and live
reader integration remain open.

### Linked Ubuntu adapter and process-boundary checks

Set `HIDS_M3_AUPARSE=1` for the reconstruction runner on Linux when the
headers and linker library are available. All 14 groups passed in the Ubuntu
AArch64 VM normally and with ASan/UBSan. This used pinned upstream 4.1.2
headers in a temporary directory and the installed libauparse runtime.
The guest package download stalled. No development package was installed.
The linked check uses a synthetic fixture and compares library record text
and type against the temporary BUFFER input before semantic validation.

The offline C++ fixture producer and Python receiver also passed on macOS.
The producer waits for each registration response before assembly. A separate
producer process was killed before final commit and after commit but before its
response. The first case recovered with no accepted event, and the second
preserved one row and deduplicated an identical retry. This uses private
process pipes and one activation/generation. Unix socket routing, peer checks,
backend crash coverage beyond the ledger tests, live activation, and rotation
remain separate acceptance work.

```bash
build_dir=$(mktemp -d)
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror \
  -I collector/include -I collector/third_party \
  collector/src/audit/{record_parser,event_assembler,execve_validation,execution,plugin_input,plugin_session,plugin_transport}.cpp \
  collector/src/{pilot,journal}/{contract,transport}.cpp \
  tests/integration/m3_fixture_producer.cpp -o "$build_dir/producer"
python3 -B -m tests.integration.test_m3_fixture_transport "$build_dir/producer"
```


### Ubuntu live acceptance prerequisite check

In the original Ubuntu VM, `systemctl is-active auditd` reported active,
`sudo auditctl -l` reported no rules, and `getent passwd hids-audit` found
no dedicated reader account. This was a metadata-only check. No Audit payload
was read and no rules, permissions or accounts were changed. Under the current
existing-source policy, this VM cannot supply configured execution-rule evidence
or exercise the required reader identity. Use an already provisioned test
guest or obtain explicit approval for an isolated acceptance setup.

The offline protocol now rejects oversized, duplicate-key and out-of-scope
requests and requires version 3 with activation, generation and lease values
from the receiver. The ledger enforces a provisional maximum of 65,536
positions per fixture database and fails closed at capacity. That count is
an offline guard, independent of the production storage budget. Ten Python
tests and the C++/Python before- and after-commit process tests passed.

### Native Ubuntu source finding

With owner-authorized VM changes, the probe temporarily switched auditd from
ENRICHED to RAW and installed an execution rule scoped to the probe parent.
From the current file tail, the probe observed one SYSCALL, three EXECVE
records with indexed fragments, one CWD, two PATH records, and one PROCTITLE
for its own test execution. There was no EOE in the file. Only record types
and field names were displayed. The original configuration was restored and
`auditctl -l` confirmed the temporary rule was removed.

The [upstream auditd 4.1.2 source](https://raw.githubusercontent.com/linux-audit/audit-userspace/v4.1.2/src/auditd.c)
explicitly skips local file logging for AUDIT_EOE while dispatching events to
plugins. The owner subsequently approved the auditd plugin source and retained EOE-only
completion. The file-source observations remain evidence for that decision. The native probe also observed `tty` and `subj` in
SYSCALL and inode, device, mode, owner and capability fields in PATH, beyond
the synthetic allowlists.

### Plugin input framing

The pinned auditd dispatcher writes `format=string` records to the plugin's
standard input as newline-delimited text over a Unix stream. The new decoder
reassembles split reads, separates coalesced records, and fails closed on
oversized, blank, CR or NUL-bearing frames. A partial frame at EOF leaves
the stream incomplete. Its offsets in the fixture test are stream-local.
The decoder does not supply durable event identity or certify continuity.

All 15 offline C++ groups passed on macOS with ASan/UBSan, including
single-byte delivery, multiple records in one read, and EOE-driven closure.
Live dispatcher capture, stream loss, privilege separation and durable
integration remain unverified.

### Live Ubuntu plugin framing probe

A temporary string-mode auditd plugin dropped UID, GID and supplementary groups
before reading its input. The process-scoped test produced SYSCALL, three EXECVE
records, CWD, two PATH records, PROCTITLE and EOE. The EOE colon was followed by
one ASCII space (hex 20) and the line delimiter. The probe reported record types
and framing only. Cleanup removed the temporary rule and plugin configuration
and restored the original ENRICHED setting. Auditd remained active.

The explicit auditd string profile now requires that exact EOE delimiter,
preserves the observed record and byte span, and excludes EOE from libauparse
input. PROCTITLE cannot close events in that profile, even if the fixture flag
is set. The updated C++ suite passed with sanitizers on macOS. This was a live
source and framing probe, without the production plugin-to-SQLite path.

The M3 socket receiver now authenticates through a caller-supplied peer policy,
allows one connection per lease, and closes the stream on revocation. Disconnect
or partial input ends the lease and resolves unfinished admissions as interrupted.
Two socket-pair tests cover split requests, disconnect suppression, lease reuse
denial and pre-read revocation. The tests use a fixture peer policy. Production
listener setup, live C++ wiring, and dispatcher loss telemetry remain pending.

The offline producer now drives the plugin session, which waits for durable
admission before feeding each framed record to reconstruction. It validates
only EOE-closed groups and waits for durable finalization before acknowledging
them locally. An incomplete stream or failed response ends the session.
The fixture adds the observed dispatcher EOE delimiter before feeding the
session and still uses private process pipes. Sixteen C++ test groups passed
with sanitizers, and the before/after-commit process-kill tests passed.

The C++ transport now exchanges bounded protocol-3 requests and validates
versioned JSON replies over a connected channel. An unexpected reply or
transport failure closes the stream. A macOS test passed with a real Unix
socket pair between the C++ fixture process and Python receiver, confirming
the final SQLite row and resolved frontier. The socket pair supplies private
endpoints for the test. Named listener ownership, mutual credentials, and
live Ubuntu plugin deployment are still open.

### Ubuntu named socket and live delivery

On Ubuntu 26.04.1 AArch64, the C++ plugin linked against the installed
`libauparse.so.0` with strict compiler warnings. A controlled fixture passed
through a named Unix socket between distinct non-root reader and ingestion
identities. Both ends checked Linux peer credentials, and the test confirmed
one durable SQLite row and a resolved frontier. M3 reuses M2's named listener
and socket ownership checks. The M3 reader identity is supplied by its launcher,
while the journal channel retains its existing default identity.

The receiver keeps an authenticated connection open while idle and applies a
deadline once a partial request arrives. The plugin also polls the receiver
socket while waiting for input so receiver closure ends an idle plugin session.
The offline C++ sanitizer suite and 13 Python tests passed, with the Python
suite also passing on Ubuntu.

The live auditd test subsequently passed on Linux 2. One controlled successful
execution with a 10,000-byte argument was reconstructed across multiple EXECVE
records, validated through libauparse and committed through the authenticated
named socket. The test matched the stored executable against Ubuntu's resolved
binary path, checked comm, success and two PATH records, and confirmed a resolved
frontier. Its rule-cleanup command also generated a distinct accepted execution.
Unsupported non-execution groups were rejected, and incomplete shutdown input
was interrupted. This is a bounded live integration result. Production activation,
stream continuity/loss telemetry and complete M3 acceptance remain open.

Two native differences were fixed after failed live attempts. Auditd sends HUP
on reload, including plugin startup. The immutable-configuration plugin now ignores
that notification while TERM, INT and backend closure end its session. Continuation
EXECVE records have two leading spaces. The explicit auditd profile accepts that
framing, preserves exact source bytes and offsets, and has an offline regression.
Observed native SYSCALL and PATH metadata are accepted as transient fields and
excluded from the normalized payload.

The two UTM guests had identical configured MAC addresses and cloned SSH keys.
Earlier SSH runs could switch guests and cannot establish Linux 2-specific
acceptance. Linux 2's NetworkManager connection now uses MAC
`9A:B8:88:B2:58:12`, yielding `192.168.64.7`. Its console confirmed the address,
and its SSH key was checked again. The current sources were rebuilt and the
13 Python tests, linked 16-group native suite and live integration were rerun
there. The UTM hardware configurations still contain the original duplicate MAC.
NetworkManager saved the guest override in persistent Netplan configuration,
confirmed by reading the matching file under /etc/netplan. Both VMs were checked
after the work and had active auditd, no rules, no temporary acceptance plugin
and their original ENRICHED setting.

Both live probes restored the original ENRICHED setting and removed their
process-scoped rule and plugin. Auditd was active after cleanup.

The explicit root-only acceptance harnesses run from the repository root and
require an already-built plugin executable and existing service identities.
`m3_named_socket_acceptance.sh` uses synthetic input.
`m3_live_plugin_acceptance.sh` is a VM-only experiment that temporarily changes
Audit configuration and restores it. Those changes belong to the test harness,
separate from application startup and installation behavior.

Backend process-crash tests now kill the Python receiver before final commit and
after commit before response. The C++ producer exits with an unconfirmed result.
Recovery suppresses the pre-commit identity, preserves the committed event and
deduplicates an identical retry. These passed on macOS and Linux 2. The linked
16-group native suite also passed on Linux 2 with ASan/UBSan. Shared M2 transport
and runtime regressions passed locally (35 vectors and the reader lifecycle suite).
The broader macOS M2 wrapper requires the separate Linux UAPI shim and was not run
in full in this round.

Plugin session ticks now enforce assembly deadlines even during idle input and
before accepting a later EOE. An expired group ends the stream and recovery
interrupts unfinished identities. The live profile now uses a provisional 10,000 ms limit after a real
EOE-delivery race with the 2,000 ms offline fixture limit. The regression checks
the live limit immediately before and at expiry. Deadline expiry cannot turn an incomplete group into acceptance.


### Activation and restart integration

The new `m3_runtime.py` and `m3_service.py` implement a separate serialized M3
service. Root control and reader data use separate sockets. Root activation
creates a fresh activation, stream generation and lease. A reader can claim that
lease once. Revocation takes priority over event readiness in the service loop.
A disconnected, timed-out or malformed stream becomes interrupted. A backend
restart reconciles unfinished admissions and records a possible gap. Fresh root
authorization starts a new interval, with byte position zero local to that stream.
Committed events and ended activation databases remain on disk.

Control state uses its own private SQLite database, separate from each interval's
progress/event database. The service holds an exclusive writer lock. An activation
ledger is created before the control activation commits. An interrupted creation
can leave an orphan ledger, which counts against the explicit capacity limit and
cannot be reused implicitly. An event-storage failure can be recorded in the
control database while the affected event database remains unresolved. Existing
M1/M2 databases are outside these writes.

The root-only control client supports `activate`, `deactivate` and `status`. Status
includes the current activation state, interruption code, reader connection state
and possible-gap flag. Authorization and update times are backend wall-clock
observations. A restart update time records discovery of the interruption, rather
than claiming the actual crash time. Prior interruption codes survive a later
explicit revocation.

The auditd launcher checks root-owned configuration and executable paths, obtains
an authorized lease before reading source input, disables core dumps, and invokes
`setpriv` to drop UID, GID, supplementary groups and capabilities before C++ runs.
The C++ `--current-tail` path then drains already queued input to an observed empty
queue before admitting records. It retains no drained bytes. Its provisional
byte budget uses the reconstruction aggregate limit, currently 8 MiB. Exhaustion,
EOF or cancellation prevents startup. This is a stream boundary, without proof
of upstream queue continuity. The older fixture mode supplies all synthetic input
directly and omits that flag.

Source artifacts now include `hids-m3.service`, `hids-m3.socket`,
`hids-m3.tmpfiles.conf`, the launcher and `m3-config.example.json`. They expect
existing distinct `hids-audit` and `hids-ingest` accounts plus `hids-ipc`. The
configuration template follows M2's explicit unset-budget convention. Set a unique
source UUID and measured/test-authorized activation, SQLite-page and position
limits before deployment. The units provide the root-owned control socket,
unprivileged backend and private state directory. Auditd configuration remains
an explicit host-administration step.

Local validation passed 24 Python tests, including process kill/recovery,
revocation races, stale leases, idle and partial input, accepted-row preservation,
control/event storage failure and capacity accounting. Socket-pair fixtures test
the service loop with explicit fixture peer policies. The native suite now has
17 groups and passed with ASan/UBSan, including current-tail draining, cancellation,
overflow and EOF. Twelve M2 Python contract/storage regression tests passed. Native
production translation units passed strict local syntax checks using the pinned
auparse headers.

The account usage limit temporarily prevented automatic approval review. Access
subsequently recovered, and the runtime was deployed and exercised on Linux 2 as
recorded below. The earlier direct-launch result remains a separate test path.

### Installed-runtime Ubuntu acceptance

The installed build on Ubuntu 26.04.1 AArch64 passed these cases through its normal
service, root control client and auditd launcher entry points.

- Socket activation starts an unprivileged backend without authorizing collection.
  An unauthorized launcher leaves queued source bytes unread.
- Ordinary users cannot use root control. An IPC-group peer with the wrong reader
  UID is rejected before claiming a lease. The dedicated reader cannot read event
  state, modify installed collector code or connect to root control.
- The reader runs under `hids-audit`, with its own primary group, only the IPC
  supplementary group, zero effective/permitted/inheritable/bounding/ambient
  capabilities, and `NoNewPrivs=1`.
- Pre-start fixture records are drained. The C++ reader then submits a scoped
  `boundary` message, which Python commits before acknowledging source readiness.
  Production ingestion requires this marker before event admission. The first
  post-boundary fixture is stored once; the queued pre-boundary identity is absent.
- Root revocation closes an idle reader and preserves its accepted rows.
- An actual backend SIGKILL ends the old stream. Startup recovers admitted unfinished
  identities, reports `backend_restart` and waits for fresh root authorization.
- Restart safely recovers the stale named socket left by SIGKILL. Recovery verifies
  the private directory, socket ownership/mode, connection refusal and unchanged
  inode/metadata. Live listeners, regular files, symlinks and unexpected modes are
  preserved, as covered by endpoint regression tests.
- An external event-database writer lock triggers bounded storage failure. Root
  control remains available through its separate database. The uncommitted event
  remains absent and its unresolved prefix stays blocked. A service restart and
  fresh root authorization resume collection.
- Malformed native input and a live 10-second assembly timeout produce durable
  `collector_input_failure` and `assembly_timeout` reports. Scoped `gap` messages
  contain allowlisted codes, and the stream closes after the final acknowledgment.
  Incomplete groups produce interruption dispositions and no accepted execution.
- Temporary position and activation budget reductions exercise `progress_capacity`
  and `capacity_exhausted`. Existing data remains on disk and the HIDS configuration
  is restored afterward.
- A process-scoped native execution with fragmented arguments passes through
  auditd, the root authorization gate, the capability-free C++ reader, the named
  socket and Python-owned SQLite. The temporary Audit rule/plugin are removed,
  the original ENRICHED configuration is restored and auditd remains active.

The 64-event fixture burst committed in 0.659 seconds. The observed collector high
water mark was 4,924 KiB and the backend high water mark was 20,452 KiB. Both showed
zero additional CPU ticks during a 1.014-second idle sample. These measurements
cover this controlled fixture workload and sampling resolution. Broader workload,
slow-receiver, disk-growth and sustained-load budgets still require measurement.

The kernel Audit status probe reported `lost=0` and `backlog=0` after the run, with
auditd active. These are host-wide observations. Plugin-queue continuity requires
separate evidence. An earlier native test waited for storage before removing its
scoped rule and reached its eight-second test deadline; matching events were
visible afterward. The final harness removes its rule promptly and then waits for
the native EOE-closed event. The quiet-source investigation below distinguishes
clean daemon startup from a plugin-removal/re-addition reload failure. The live
10-second assembly deadline remains provisional.

All 31 Python M3 tests passed locally and on Ubuntu, including three real endpoint
security regressions. The native reconstruction/current-tail suite has 17 groups
and passed locally and on Ubuntu with ASan/UBSan and the linked libauparse adapter.
The production plugin linked against the VM's
installed libauparse with strict warnings. The installed runtime acceptance
harness is `tests/integration/m3_runtime_ubuntu_acceptance.py`. It runs as root on
an explicitly provisioned VM, preserves event history, and optionally runs the
Audit and capacity tests using `--live-audit --capacity-limits`.

The VM now has root-owned application code under `/usr/lib/hids`, root-owned
configuration under `/etc/hids/m3.json`, and private state under `/var/lib/hids/m3`.
The dedicated `hids-audit` account was provisioned for the reader. The installed
test configuration uses 32 activation files, 512 SQLite pages per database and
1,024 source positions per interval. These are explicit test ceilings, separate
from release performance thresholds. State-file ownership and mode checks passed
with no exceptions. Both M3 units were left inactive with the final interval revoked.

Source artifacts provide the matching systemd units and an unset configuration
template. Normal startup uses `sudo systemctl start hids-m3.socket`, followed by
root control from `/usr/lib/hids`, for example
`sudo python3 -B -m engine.ingestion.m3_control status`. Source activation and host
Audit plugin/configuration remain explicit administration steps. This runtime
result closes the first build's control/restart acceptance round. Sustained
collection, upstream loss telemetry and the remaining source-contract hardening
continue in the backlog.

### Quiet-source delivery and dispatcher reload regression

On the same Ubuntu VM, `auditd` and `libaudit1` are
`1:4.1.2-1ubuntu0.1`. A separate, unprivileged metadata-only observer plugin
recorded only native record types and monotonic elapsed times for one PID-scoped
execution. It observed the same stream as HIDS without its durable-admission
round trips. No arguments or native payload values were retained by the observer.

After plugins had been removed and re-added using Audit reload, 4-, 8- and
12-second quiet probes received SYSCALL through PROCTITLE immediately, but EOE
arrived only when removal of the scoped test rule generated further Audit traffic.
The dispatcher snapshot showed two active plugins, one queued record, no reported
overflow and no suspension. At 12 seconds, HIDS had already durably recorded
`assembly_timeout`, with `possible_gap=true`, `source_ready=false` and an
interrupted interval. The late EOE produced no accepted execution. Committed
history was preserved.

A clean Audit daemon restart with the same plugins and execution delivered EOE
within 0.49 ms of the first observed SYSCALL in the repeatable positive run. HIDS
stored exactly one execution before rule removal and stayed streaming through a
12-second quiet period. The dispatcher queue snapshot then showed depth zero.
These are controlled observations, not a general latency guarantee. Both paths
had already delivered the other record types, so absence of configured execution
coverage does not explain this difference.

The likely mechanism follows from the pinned
[queue implementation](https://github.com/linux-audit/audit-userspace/blob/v4.1.2/audisp/queue.c)
and [dispatcher lifecycle](https://github.com/linux-audit/audit-userspace/blob/v4.1.2/audisp/audispd.c):
removing the last plugins can exit reconfiguration before clearing `disp_hup`;
subsequent initialization does not clear it. The next dequeue can consume a
semaphore notification while returning before removing the queued record. This
explains a persistent one-record delay, matching the observed queue depth. This
is a source-based diagnosis supported by paired probes; the daemon was not
patched or instrumented. Ubuntu's package patch series does not alter these
dispatcher files. The published upstream 4.1.2 release tarball's queue source
matches the pinned tag.

The native reader's observed `SigBlk` was zero. Upstream `safe_exec` explicitly
unblocks signals before executing a plugin. No signal-mask workaround was added.
The `end_of_event_timeout` setting concerns userspace event aging; changing it
does not establish native EOE delivery on an idle stream.

Run the explicit root-only probe only on an isolated, provisioned acceptance VM
with no Audit rules, no active plugins and an inactive M3 service. Run these in
order: cleanup of the first case removes the plugins by reload, establishing the
precondition for the second case.

```sh
sudo python3 -B tests/integration/m3_quiet_source_ubuntu.py --audit-start restart --expect accepted
sudo python3 -B tests/integration/m3_quiet_source_ubuntu.py --audit-start reload --expect assembly_timeout
```

The probe temporarily changes RAW formatting, installs two test plugins and one
PID-scoped rule, then revokes the interval, removes its rule/plugins, restores the
original configuration, verifies auditd is active and stops M3. It retains private
metadata evidence under `/run/hids-m3-quiet.*`; source logs and HIDS history are
never removed. A clean test-administration restart after the pair clears the
upstream reload state. Restarting or configuring auditd is not a HIDS runtime
action. The existing EOE-only decision and timeout policy were preserved; neither
fabricated completion nor periodic synthetic Audit traffic was introduced.

M3 status now explicitly reports `upstream_loss.kernel` and
`upstream_loss.dispatcher` as `unknown`. An authorized, connected, boundary-ready
reader and `possible_gap=false` do not establish upstream continuity. Root-only
probe snapshots are host-wide observations at measurement time, not continuous
monitoring or exact per-HIDS loss counts. Automatic upstream loss telemetry,
independent durable timeout dispositions and sustained-load
measurements remain open M3 work. The 32-test Python suite includes a regression
that passes the service's status response through the actual control-client
contract checks.

### Assembly clocks during durable backpressure

The native reconstructor now maintains separate inactivity and maximum-lifetime
checks on an active monotonic timeline. A new record resets only inactivity.
Nested intentional pauses subtract their union once; resuming does not charge
the paused interval retroactively. Reverse clocks, unbalanced resume and input
admission while paused fail closed. The production plugin pauses the timeline
around synchronous durable registration and finalization exchanges, using the
same monotonic clock as its reader loop. IPC's existing two-second request bound
still applies; the assembly pause creates no unbounded storage wait.

The live inactivity and lifetime thresholds both retain the existing provisional
10-second ceiling. The new inactivity setting can be tuned independently; no
release threshold was inferred from the quiet-source measurement. Upstream queue
delays still count as active time. This change therefore does not hide the Audit
reload failure or make a missing EOE complete.

The 19-group native suite passes with ASan/UBSan locally and with the linked
libauparse adapter on Ubuntu. It includes independent inactivity/lifetime expiry,
nested pause accounting for each deadline, and interleaved assemblies whose
simulated durable callbacks collectively wait over ten seconds. The earlier
event survives those waits and closes with EOE, while a later event with ten
seconds of actual active elapsed time still times out. These injected-clock tests
exercise the scheduling behavior, not measured production storage latency.
The linked production plugin uses this clock path. Timeout still conservatively
interrupts the stream; per-event durable timeout reasons and continued independent
event processing remain separate hardening work.

The rebuilt collector also passed the complete installed-runtime acceptance harness
again with `--live-audit --capacity-limits`: unauthorized-input exclusion, peer and
privilege checks, current-tail filtering, revocation, backend SIGKILL/recovery,
fresh authorization, event-database contention, malformed input, the live active
assembly deadline, native Audit execution and both capacity failures. The fixture
burst committed 64 executions in 0.607 seconds. Observed high water marks were
4,932 KiB for the collector and 20,208 KiB for the backend, with zero additional
CPU ticks in a 1.008-second idle sample. These remain controlled workload samples.
The installed collector separately passed the paired 12-second quiet tests after
its clock change: prompt EOE/one accepted event after clean startup and durable
`assembly_timeout`/zero accepted events after the reload regression.

Accumulated test history approached the original 32-interval test budget. The VM
configuration was deliberately increased to 64 activation files, preserving its
512-page/database and 1,024-position/interval limits. No history was deleted.
This is a reversible VM test budget, not a release storage threshold; the source
configuration template still requires explicit budgets. Final checks confirmed
root-owned configuration at mode 0640, ingest-owned state directory at 0700 and
all state files at 0600. Audit returned to ENRICHED with no rules or active test
plugins, auditd active and both M3 units inactive. A clean Audit restart after
cleanup cleared the test-induced dispatcher state. No commits or pushes were made.

From the provisioned repository checkout, the full runtime invocation is:

```sh
sudo systemctl start hids-m3.socket
sudo python3 -B tests/integration/m3_runtime_ubuntu_acceptance.py tests/fixtures/audit/structural-exec.log --live-audit --capacity-limits
sudo systemctl stop hids-m3.socket hids-m3.service
```

The optional live-source case uses temporary Audit administration and requires an
isolated VM with no existing rules or colliding acceptance plugin. The separate
quiet-source probe above tests quiet EOE delivery; prompt rule removal in this
broader harness does not substitute for that test.

### Per-event timeouts and sustained workloads

This increment supersedes the earlier first-build stream-wide timeout behavior.
A production timeout now sends sanitized per-event evidence over the authenticated
reader lease. Python validates policy version, allowed reason, integer bounds,
monotonic ordering, pause accounting and the actual expired deadline. In one
transaction it stores the evidence, rejects the identity and advances only eligible
progress. It rejects a timeout for an EOE-closed, accepted or interrupted identity.
A byte-identical committed retry is idempotent; conflicting evidence is rejected.
A failed disposition/frontier transaction rolls back both. Failure to confirm a
timeout commit still stops the stream; independent progress never bypasses storage
uncertainty.

The additive `m3_timeouts` table stores no source payload. Its timing domain is the
one plugin stream/generation's steady-clock milliseconds: first/last active time,
active and monotonic time at observed expiry, cumulative paused time, both limits,
policy 1 and inactivity/lifetime reason. These are operational measurements, not
activity timestamps or a claimed crash time. The existing provisional live limits
remain ten seconds each.

New positions for a finalized identity are durably classified as `suppressed`,
with bounded position/EOE/prior-state metadata in `m3_late_positions`. The native
reader advances past them without reconstructing their payload. Physical replay
still verifies the previously registered range and EOE classification first.
Suppressed late EOE cannot cause a second execution or amend accepted/rejected
history. Position/page budgets still apply; no tombstones or stored events are
automatically removed to obtain progress.

The root status response includes `event_health.timeouts` and `late_records`.
Known incomplete events set `possible_gap` without ending a usable stream.
Read-only committed counts remain available after revocation and backend reopen;
unavailable or legacy evidence stays unknown rather than being silently zeroed.
The control client validates the updated response. Upstream kernel/dispatcher
loss remains independently unknown.

The live reconstructor now releases acknowledged payload/history after the safe
volatile frontier passes an immutable finalized group. The already committed
Python disposition remains authoritative and must classify every later record
before C++ can admit assembly. Offline replay tests retain their previous history
mode. A 2,000-event native retirement regression under tiny history budgets checks
bounded cache use and that retiring ownership does not mutate delivered immutable
objects. Timeout/late handling tests preserve independently finalized B, suppress
late A, continue C and stop on an unconfirmed timeout disposition.

All 35 Python M3 tests passed locally and on Ubuntu. All 21 native groups passed
with ASan/UBSan locally and with the actual linked Ubuntu libauparse adapter. The
rebuilt production plugin and matched backend/client passed the complete installed
runtime harness, including restart/kill, privilege separation, source exclusion,
revocation, blocked storage, native Audit and capacity failure cases. Its updated
live timeout test stores B after A's timeout, suppresses A's later EOE, leaves no
execution for A and reaches a fully resolved frontier.

The paired native 12-second quiet probes also passed with per-event behavior.
Clean startup delivered EOE about 0.191 ms after the observer's first SYSCALL and
stored exactly one event. The reload regression delayed EOE about 12.158 seconds;
HIDS durably timed out the identity, reported a possible gap, stayed streaming and
suppressed late EOE without storing that execution. Neither an increased deadline
nor fabricated completion hid the upstream defect.

The separate installed-runtime workload is:

```sh
sudo python3 -B tests/integration/m3_load_ubuntu.py tests/fixtures/audit/structural-exec.log --events 4096
```

It requires an inactive M3 service and a provisioned isolated VM. It modifies no
Audit configuration or rules. It temporarily sets the HIDS position budget to
24,676 and the per-database page budget to 8,192 for this fixture, then restores
the original HIDS configuration and stops both M3 units. It retains every test
ledger and a private configuration backup; restored budgets do not shrink or
silently delete the intentionally larger completed test ledger.

The full-speed run committed all 4,096 distinct expected execution identities and
24,576 record positions in 20.505 seconds (199.75 executions/second). Scanned and
resolved frontiers matched, with zero timeout or late dispositions. Collector RSS
was 4,744 KiB after the first 64 events and 4,748 KiB from 512 through 4,096 events.
Backend RSS rose from 21,068 to 23,116 KiB and remained at that sampled value from
1,536 through 4,096 events. The database held 882 pages of 4,096 bytes (3,612,672
bytes of main-database pages), excluding SQLite sidecars and filesystem overhead.
These are measurements of a sanitized fixture workload, not release performance
thresholds or representative coverage of all real native records.

Before the full-speed phase, the harness admitted an incomplete A and applied
32 successive 0.4-second external SQLite writer locks while independent B events
were sent. The phase took 16.744 wall seconds. All 32 B executions committed;
A remained open with zero timeout dispositions because intentional storage waits
froze its clocks. A's eventual EOE produced an ordinary incomplete rejection, not
an accepted execution. This tests actual installed storage waits in addition to
the injected-clock native cases.

For a longer paced workload, use `--duration-seconds 300`. Batch pacing is explicit;
its overall rate includes deliberate waiting and must not be presented as maximum
throughput. Broader real-host, multi-hour, mixed-source and release-budget evidence
remains separate from these bounded acceptance tests.

The additional paced run completed 4,096 executions over 300.021 seconds
(13.65/second including deliberate pacing). It again verified every expected
identity, all 24,576 positions, a resolved frontier, zero timeout/late dispositions
and an 882-page main database. Collector RSS was 4,740 KiB at 64 events and
4,744 KiB from 512 through 4,096. Backend RSS was 20,908 KiB initially and
22,956 KiB from 1,024 through 4,096. Its preceding 32-lock storage-pressure phase
took 17.001 wall seconds and again preserved incomplete A without a timeout while
all independent B events committed. The five-minute run provides a longer bounded
fixture observation; it is not a multi-hour or mixed real-host benchmark.

### Upstream health permission evidence and pending architecture decision

A separate read-only VM probe sent only unicast `AUDIT_GET`, with no event-group
subscription and no Audit configuration operation. Under the capability-free
`hids-audit` UID 993 it received kernel `EPERM`; under root it read host-wide
`lost=0`, `backlog=0` and the auditd PID. These sampled zero values do not prove
continuity of the HIDS plugin stream.

After a clean daemon restart, the dispatcher state file was absent. Following an
explicit test-administration state request while HIDS collection was stopped,
`/run/audit/auditd.state` was root:adm mode 0640 under root-owned mode-0755
`/run/audit`. The reader was denied access, while root could read the recognized
queue metadata. With no active plugins, queue capacity zero and queueing suspended
reflect an inactive dispatcher, not active-source overflow. The actual host's
`report_interval` is zero; HIDS has not changed that setting.

The owner subsequently approved the separate checker. The implemented health-only
interface and isolation are described below; the original permission evidence
above remains relevant. Existing logging settings continue under host administration.

### Installed health-checker acceptance

The owner approved the separate privileged checker; this section supersedes the
previous pending-decision record. Implementation/acceptance updated November 11,
2026. The original event reader and backend remain capability-free. The new C++
helper performs only a fixed unicast kernel `AUDIT_GET` request and bounded reads
of `/run/audit/auditd.state`; it never subscribes to events, changes Audit rules or
configuration, resets counters, or signals auditd. No new dependency was installed.

The helper communicates through `/run/hids/m3/health/metrics.sock`, owned by
hids-ingest:hids-ipc at 0660 under a 0750 directory. The backend checks root peer
credentials before reading a request. This endpoint supports only scope discovery
and scoped health reports: no source activation/deactivation, lease issuance,
security-event submission, arbitrary paths, shell operations or SQL. The helper
verifies the backend peer and bounded response shape. Non-root IPC-group peers are
rejected. Stale reports cannot be attached to another activation/generation.

`hids-m3-health.service` runs as a bounded one-shot root process with only
`CAP_AUDIT_CONTROL` in its effective/permitted/bounding/ambient sets and
`NoNewPrivileges=1`. Its network namespace is isolated; only AF_UNIX/AF_NETLINK
socket families are permitted. Its private `/run` exposes the health endpoint and
read-only Audit metadata directory, hiding the administrative/data sockets and
other privileged services. Stored event data, credentials and logs are inaccessible;
the host filesystem is read-only. The process installs an additional syscall filter
that denies executing programs, sending signals, debugging and cross-process memory
operations. A 32 MiB memory ceiling, one-task ceiling, limited file descriptors and
three-second service timeout bound the helper. These are initial protective limits,
not release performance guarantees. The helper itself uses a two-second deadline.

The actual service-policy probe confirmed that administrative/event IPC and event
storage were inaccessible; internet sockets, host-file creation, exec and signals
were denied; only the Audit-control capability remained. This does not create a
kernel-enforced read-only Audit permission: exploitation of that remaining capability
is a residual risk. The implementation deliberately gives it to neither event
service and accepts no security-event payload in the helper. The test-only isolation executable is separate from the production checker and
was removed from the installation after acceptance; its source/build remain available.

The timer is wanted by M3 and reschedules five seconds after the helper exits,
with one-second scheduler accuracy. Consecutive actual samples in the periodic-report
case were about six seconds apart. `PartOf`, `BindsTo` and `After` bind both checker
units to the backend: normal shutdown and an actual backend SIGKILL stop them. A
revoked/inactive interval returns no authorized scope, so the helper exits before
reading host counters. A missing/untrusted metadata endpoint is reported as
`health_endpoint_unavailable` while ingestion remains usable. A health-table write
fault reports `health_storage_failure` without stopping the event reader or root
control. Successful later reporting clears that non-durable reporting error.

The Python backend independently validates report shape, integer ranges, boot UUID,
queue flags/counts, sender time/receipt window and freshness. Unknown fields and raw
payloads are rejected. A duplicate committed sample cannot renew freshness, and
conflicting/out-of-order samples fail. One row per activation keeps the latest
observation, first readable kernel baseline, previous readable kernel observation
for comparisons, sticky incident flags and prior-unavailability flags. This is a
bounded health projection, not a full sample-by-sample history. Latest receipt time
does not identify the time of an older sticky incident.

The control database migrates transactionally from schema 3 to 4 by adding
`m3_health`; existing intervals and event files are preserved. Python owns every
write. The metadata uses internal IPC version 3 and fits the existing 2 KiB control
bounds. Status distinguishes `sampled`, `inactive` and `unknown`, plus fresh/stale/
historical observations. The current freshness window is fifteen seconds. A fresh
counter snapshot is an observation, not proof of continuous coverage. Source-ready
continues to describe the authorized reader/boundary rather than upstream loss.

Kernel loss increases, counter decreases/resets, boot changes, daemon PID changes,
disabled/missing auditing, active-dispatcher overflow/suspension and sampling gaps
are distinct sticky flags. Counts already present at the first sample are labeled
as baseline host loss and are never assigned to HIDS or dated before/after activation.
No exact HIDS lost-execution count is inferred from host counters. Counter changes,
resets and boot/PID transitions were tested with injected metadata, without causing
real host Audit loss or resetting kernel counters. Real kernel reads were also
validated through the isolated service.

All 46 Python M3 tests passed locally and on Ubuntu. Native metadata parsing passed
ASan/UBSan locally and on Ubuntu, including strict recognized fields, duplicate
rejection, bounded data, malformed values, impossible queue depth, missing fields,
stale/future timestamps and trust rejection. The existing 21-group native event
pipeline remains separate from this metadata suite. The complete installed M3
regression harness passed with the checker enabled: source authorization/exclusion,
privilege separation, revocation, backend kill/recovery, storage contention,
per-event timeout/late suppression, real Audit delivery and capacity limits.
Its 64-event fixture burst committed in 0.606 seconds, a controlled regression
measurement rather than a general throughput guarantee.

`m3_health_ubuntu.py` passed actual timer-driven kernel sampling, missing metadata,
non-root peer denial, rejection of activation operations, fresh inactive-dispatcher
metadata, stale/malformed/symlink rejection, missed-sample expiry, recovery with
retained sampling gaps, health write-fault isolation, the actual unit-policy probe,
and durable health evidence after revocation/backend restart. The harness's explicit
operator state request happens outside the product checker; the checker itself
never requests state dumps or generates traffic to flush EOE.

`m3_health_periodic_ubuntu.py` is an explicit lab-only operator test. It temporarily
changed `report_interval` from 0 to 1, then observed three consecutive passive timer
samples of real kernel and periodic dispatcher metadata while event ingestion
continued. Successive report modification times increased and the report ages at
sampling were about 0.89 seconds. The host had no active auditd plugins, so dispatcher
status correctly remained `inactive`. The test restored the exact original Audit
configuration and derived metadata report. No Audit rule changed. Production startup,
installation and the helper never change that host setting.

`m3_health_lifecycle_ubuntu.py` temporarily made the health directory unavailable to
the backend. The error was visible while a fixture execution committed and root
control stayed available. Backend SIGKILL stopped the checker and timer automatically.
Restoring the directory allowed backend recovery, preserved the committed event and
required fresh authorization before source collection. The original directory was
restored and all units stopped afterward.

The three installed tests run from the provisioned Ubuntu checkout:

```sh
sudo python3 -B tests/integration/m3_health_ubuntu.py tests/fixtures/audit/structural-exec.log --isolation-probe /usr/lib/hids/health-isolation-probe
sudo python3 -B tests/integration/m3_health_periodic_ubuntu.py
sudo python3 -B tests/integration/m3_health_lifecycle_ubuntu.py
```

For the first test, build the test-only probe from
`tests/unit/m3_health_isolation_probe.cpp` plus `collector/src/health/snapshot.cpp`
and install it root-owned under `/usr/lib/hids` before running. The production
checker builds from `collector/src/health/main.cpp` and `snapshot.cpp`, using C++20,
strict warnings and include paths `collector/include` and `collector/third_party`.
It does not depend on libauparse. Install the checker, matched Python modules,
updated M3 service/tmpfiles and new checker service/timer together; create the
protected health runtime directory with the tmpfiles artifact and reload systemd.
The timer is tied to M3 startup and is not independently enabled at boot.

On the restored host, `report_interval=0` means a continuous fresh dispatcher report
is not supplied. The checker samples kernel status normally and correctly leaves
missing/stale dispatcher evidence unknown. Fresh dispatcher monitoring is supported
when an administrator already publishes periodic reports; the application never
silently changes logging policy to obtain them. This dependency closes the health
implementation/testing item with an explicit availability limitation, not a claim
that every upstream queue is continuously observable on the default configuration.

Historical sample age is explicitly unknown when an old monotonic timestamp cannot
be compared with the current clock epoch; it is never silently converted into a
fresh zero-age report. The reboot-related status regression passed. Final cleanup
verified the original Audit configuration, no test rules/plugins, private retained
state, and inactive M3/checker units. No Git commits or pushes were made.
