# M1 fixture-to-database pilot contract proposal

**Status:** Architecture approved in principle; P-01–08 await explicit owner approval before implementation  
**Recorded:** November 7, 2026  
**Proposed event contract:** `m1.process-exec/0.1.0`  
**Proposed wire protocol:** integer version `1`  
**Scope:** M0 design for one sanitized EXEC fixture; no pipeline implemented

## 1. Purpose and decision boundary

Demonstrate one small vertical slice:

**Synthetic native EXEC bytes → existing C++ parser → C++ limited normalization/
validation → Unix stream socket/JSON Lines → independent Python validation →
Python-owned SQLite commit → retrieval by event ID.**

The accepted C++20/Python split, Unix sockets/JSON Lines, Python-owned SQLite,
ECS 9.5.0 foundation and [ADR-001–007](../decisions/) remain unchanged. This note
supplies specific **recommended pilot choices**, not an accepted production
schema, service deployment or permission policy. Approval of this exact pilot
would settle only the listed M1 choices. Changes discovered during coding must
return for review rather than silently changing the contract.

The [readiness plan](v0.1-implementation-plan.md#decision-register) retains the
broader decision register. This proposal narrows D-01–04, D-06–07 and D-13 for
fixtures; D-05 enrichment, D-08 detection, D-09 production retention, D-10 live
recovery, D-11 other sources, D-12 human authentication and D-14 first-run controls
are not prerequisites for this synthetic test. No live source is selected or
initialized. The [confirmation gate](../product-experience.md#first-run-experience)
still applies before any later real collection.

## 2. Repository inspection and reuse

Inspection was performed in the canonical repository, without Git operations.
Paths below describe existing files, not proposed coverage.

| Existing artifact | Observed interface / behavior | M1 use |
|---|---|---|
| [process_collector.hpp](../../collector/include/hids/process_collector.hpp) | `NativeEvent`, `Lifecycle`, optional parent/EXIT values; native CPU, sequence and `uint64_t kernel_monotonic_ns`; internal types explicitly not ECS/IPC | Input to a separate limited normalizer; preserve PID/TID versus TGID semantics |
| [process_connector_protocol.cpp](../../collector/src/process_connector_protocol.cpp) | `decode(span<const byte>, DecodeSink&)` validates lengths, source IDs and kernel-format data; uses aligned copies | Decode a constructed fixture without socket creation; ARM64 layout checks remain exercised |
| [process_collector.cpp](../../collector/src/process_collector.cpp) | `Collector` owns serialized subscription lifecycle through injected `ConnectorIo`; `Sink::on_event` is `noexcept`, nonblocking, borrowed-data-only | No rewrite. Future live handoff can copy into bounded downstream state; socket/DB work must never occur in this callback |
| [linux_process_connector.cpp](../../collector/src/linux_process_connector.cpp) | Dedicated Linux netlink backend; not a normalized transport | Do not construct/open it in the pilot executable |
| [process_collector_test.cpp](../../tests/unit/process_collector_test.cpp) | Native packet builder, `DecodeSink`, fake I/O, malformed/alignment/lifecycle/ACK/sequence tests | Follow packet-construction pattern with synthetic identifiers; do not depend on private test helper linkage |
| [linux_process_connector_test.cpp](../../tests/unit/linux_process_connector_test.cpp) | Offline syscall doubles, CLOEXEC/readiness/error/cleanup cases | Keep existing suite separate and unchanged |
| [process_collector_link_smoke.cpp](../../tests/unit/process_collector_link_smoke.cpp) | Links all production translation units; never starts collection | Preserve this separate regression check |
| `engine/ingestion/`, `engine/database/`, `shared/schemas/`, `tests/integration/`, `tests/fixtures/` | `.gitkeep` scaffolding; no pipeline, shared validator or fixture contract | Add only approved pilot modules/fixtures during a future M1 task |
| [collector/README.md](../../collector/README.md#compile-and-run-offline-tests-on-ubuntu) | Explicit compiler recipes; no build/dependency manifests found in repository inspection | Extend explicit recipes rather than introduce CMake/package tooling for M1 |

Recommended fixture path: a small test-only C++ builder creates zero-initialized
`nlmsghdr`, `cn_msg` and `proc_event` values using the installed Linux headers,
sets EXEC members and copies them into a byte buffer as existing tests do. This
avoids committing a compiler-layout-dependent struct dump. A reviewed declarative
fixture records the synthetic field values; C++ reads it using the JSON library,
validates it and constructs the native packet. Python receives only normalized
wire events, never native netlink bytes.

For M1, propose `tests/fixtures/process/synthetic-exec-001.json` containing exactly
the `native` object from the example below, with the same closed field/type rules.
Header lengths/connector identifiers are constructed from installed UAPI types,
not accepted from fixture input. Tests inject clocks/IDs separately; no live host
identifiers are needed to create or interpret this fixture.

Call `decode()` directly with a test-only `DecodeSink`. Its callback copies the
single fixed-size `NativeEvent` into an optional slot and counts events/errors;
no allocation, JSON serialization, IPC or exceptions occur inside the callback.
Outside it, require exactly one EXEC and zero diagnostics/ACKs, then normalize.
An additional event, unexpected type or parser error fails the fixture run.
No `Collector::start()`, `LinuxConnectorIo::open()`, LISTEN, child process or real
`/proc` read is needed. Unit tests can additionally inject a `NativeEvent` into
the normalizer, but that shortcut does not replace the native-parser round trip.

The normalizer should accept an injected observation clock and ID generator for
deterministic tests. It owns a copy, not a reference to callback arguments. A later
live `Sink` adapter can reuse it after handoff, without changing the collector's
native API or its scheduling promises. This does not design that live queue now.

## 3. Limited envelope and complete JSON Lines example

All values below are **synthetic**, including identifiers and observation time.
They are neither a replay of the reported Ubuntu child nor an assertion that PID
4242 executed on the test host. The monotonic value deliberately exceeds exact
IEEE-754 integer precision to exercise lossless handling.

The following is **one complete line**. Its transport terminator is one LF byte
immediately after the final `}`; the Markdown fence is not transmitted.

```jsonl
{"protocol_version":1,"message_type":"event","contract_version":"m1.process-exec/0.1.0","ecs_reference_version":"9.5.0","event_id":"84990d10-90c8-4ed5-a96a-9dbaebf3cfba","producer_instance_id":"15729e8d-54b8-4cd0-a74f-09e7492ad870","source":{"adapter":"linux.cn_proc","mode":"sanitized_fixture","fixture_id":"synthetic-exec-001","boot_id":null},"native":{"what":"PROC_EVENT_EXEC","what_code":2,"pid":4242,"tgid":4242,"parent":null,"cpu":3,"connector_sequence":2,"timestamp_ns":"12345678901234567","timestamp_unit":"ns","timestamp_clock":"linux.cn_proc.timestamp_ns"},"timestamps":{"activity_wall_time":null,"activity_wall_time_reason":"not_emitted_by_source","observed_at":"2026-11-07T20:00:00.000000Z","observation":"fixture_decode"}}
```

### Exact pilot validation rules

Every key shown is required; reject additional keys at every object level. This
closed pilot avoids accidental field retention. It does not require the eventual
production schema to reject every unknown native field. No arrays are used.

| Field/group | Pilot rule |
|---|---|
| `protocol_version`, `message_type` | Exact integer `1`, exact string `event`; integer checks exclude booleans and floating-point values |
| `contract_version` | Exact `m1.process-exec/0.1.0`; reject other versions rather than guess compatibility |
| `ecs_reference_version` | Exact `9.5.0`, independently tracked from wire/event versions; reference metadata, not a claim of a finalized ECS event |
| `event_id`, `producer_instance_id` | Lowercase, hyphenated UUIDv4 syntax, RFC variant bits; event ID assigned once per newly normalized observation; producer instance identifies the original normalizing invocation and is preserved by a replacement sender retrying that event |
| `source.adapter`, `source.mode`, `source.fixture_id` | Exact `linux.cn_proc`, `sanitized_fixture`, `synthetic-exec-001`; no arbitrary host/user/path labels |
| `source.boot_id` | Required JSON null: synthetic source has no established actual boot scope; never use the VM boot ID to authenticate synthetic time |
| `native.what`, `native.what_code` | Exact `PROC_EVENT_EXEC`, integer `2`; derive from decoded `Lifecycle::executed`, not arbitrary source text |
| `native.pid`, `native.tgid` | Integers 1 through 2147483647. `pid` preserves kernel `process_pid`/C++ `tid`; `tgid` preserves `process_tgid`. They may differ; do not collapse threads |
| `native.parent` | Required null for this EXEC contract; source event supplies no parent. Do not infer it from another event or `/proc` |
| `native.cpu`, `native.connector_sequence` | Integers 0 through 4294967295; zero is valid native data. Preserve values beyond the adapter's sequence-tracking array as data, not a fabricated lookup |
| `native.timestamp_ns` | Decimal ASCII string matching `0` or `[1-9][0-9]{0,19}`, numeric value at most 18446744073709551615; no sign, leading zero, exponent or rounding |
| `native.timestamp_unit`, `native.timestamp_clock` | Exact `ns` and `linux.cn_proc.timestamp_ns`; source monotonic value, never a Unix epoch timestamp |
| `timestamps.activity_wall_time` | Required null. In this narrowly accepted pilot an absent activity wall time is valid, not a rejected event or fallback request |
| `timestamps.activity_wall_time_reason` | Exact `not_emitted_by_source` |
| `timestamps.observed_at` | UTC Gregorian timestamp, exact `YYYY-MM-DDTHH:MM:SS.ffffffZ`, years 0001–9999, valid calendar/time, seconds 00–59. C++ observes successful fixture decode; injected time in deterministic cases |
| `timestamps.observation` | Exact `fixture_decode`; discloses what was observed |

All keys/constants/allowed variable strings are ASCII in this pilot. Reject
non-ASCII decoded strings, duplicate object keys (including escaped-equivalent
keys), nulls outside the specified positions, floats/exponents for integer fields,
non-finite numbers, invalid UTF-8, BOMs and unpaired surrogates. Do not coerce
strings to numbers or booleans to integers. Decode one complete JSON object only;
comments and trailing non-whitespace content are errors. Bound nesting to eight
containers before building a DOM; bound individual strings to 256 decoded ASCII
characters. Those are pilot parsing limits, not field-catalog limits.

C++ independently validates the extracted native values and every outgoing
envelope field before serialization. Python independently enforces the same
envelope rules before any write. Tests exercise both validators with a shared
valid/invalid vector corpus; successful serialization alone is not validation.

### Timestamp and ECS boundaries

The original cn_proc timestamp retains source monotonic semantics and nanosecond
units. In a synthetic replay it is not comparable to this VM's current monotonic
clock; boot scope is absent. No wall-clock conversion, ordering across boots,
`@timestamp`, zero epoch or observation-time activity substitute is introduced.

Capture `observed_at` once after decode, before the first send, from an explicit
UTC wall-clock observation. If the clock cannot be obtained/formatted, fail before
sending rather than invent a date: report `local_failure / not_submitted` with
`observation_clock_failed`, discard the copied native event and exit unsuccessfully.
Do not form/hold an incomplete envelope, allocate its event ID, transmit bytes or
automatically retry the clock. A separately requested new fixture run is a new
observation. This local pre-transmission failure is not a receiver rejection or
an uncertain DB commit and creates no automatic retry. A frozen envelope retry never reads a new observation
clock. The clock may move backward and does not prove native
activity time. Retrying retains it. Python separately records first receipt time
and a pre-commit storage-attempt observation; neither enters the immutable envelope
or pretends to be the exact instant of durable commit.

These transport field paths are a provisional native-preserving pilot wrapper,
**not the approved canonical ECS schema or a finalized `hids.*` namespace**.
`ecs_reference_version` is not a renamed claim of populated ECS `ecs.version`.
Future mappings must follow the [schema process](../schema-design-process.md) and
[schema draft](../event-schema.md). Event ID/observation time and TGID are candidates
for pinned ECS review; this pilot does not approve those mappings or force native
CPU/sequence/monotonic fields into unrelated ECS semantics. Structured native data
is not placed in textual `event.original`. Moving to a canonical ECS envelope will
require a new explicit contract and compatibility/migration decision.

## 4. Identity, retries and collisions

Recommend random UUIDv4 event IDs generated by C++ from Linux `getrandom()` bytes,
setting the UUID version/variant bits only after obtaining all 16 random bytes.
Use the same mechanism for the producer instance ID. Request bytes using
`GRND_NONBLOCK`: advance an offset on each positive partial read, retry EINTR for
the remaining bytes, and treat zero progress or any other error (including EAGAIN)
as terminal generation failure. Discard partial bytes/IDs and fail locally before
transmission; no incomplete ID, random-byte retry loop on terminal errors, held
event or PID/time/sequence/`rand()` fallback. Inject partial reads, EINTR and terminal
failure in tests. The existing libc interface introduces
no UUID library. See the [Linux getrandom reference](https://man7.org/linux/man-pages/man2/getrandom.2.html).

Assign identity after native validation and observation, once before first send.
Freeze the complete envelope and encoded line in a one-item pending slot. A retry
reuses the same ID, producer instance, time and content; it must not renormalize
the native event. A newly replayed fixture is a new observation with a new event
ID, even if its native values match. Fixed IDs/times in test vectors are confined
to isolated test databases. Neither PID, TGID, CPU sequence, a content digest nor
the adapter's local `session` counter is a globally unique identity.

The receiver produces a comparison representation after strict validation using
Python `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True,
allow_nan=False)`. All accepted values are constrained ASCII strings, integers
or specified nulls; no float/Unicode normalization ambiguity is permitted. This
is a **pilot comparison encoding**, not a general JSON canonicalization standard.
It contains the entire event envelope, including provenance, versions, producer
instance and observation time; it excludes the LF and receiver-local metadata.
C++ need not produce the same key order. Semantically equal accepted objects with
different whitespace/key order compare equal; duplicate keys were already rejected.

| Incoming event ID / content | Receiver action |
|---|---|
| New ID | Insert exactly one immutable event row and commit before ACK |
| Existing ID, equal valid comparison encoding | Do not update payload/times or insert again; verify existing row, then ACK `duplicate` |
| Existing ID, different valid encoding | Reject `id_conflict`, preserve original row, close connection; never overwrite, merge, assign a replacement ID or silently treat as retry |
| Unsupported contract version, whether ID exists or not | Reject `unsupported_version` before DB identity comparison; original row unchanged |
| Unsupported protocol version, whether ID exists or not | Reject `unsupported_version` before DB identity comparison; original row unchanged |

Framing/JSON and version/field validation precede database identity comparison.
An unsupported version is not a valid competing payload for collision tests;
changing a valid native value, producer instance or observation time is.
Correctly typed but unsupported protocol/contract/reference version values yield
`unsupported_version`; missing or incorrectly typed version fields yield
`invalid_event`. No validation rejection reaches the identity/write transaction.

Compare full canonical text, not only a hash. A collision with identical complete
content cannot be distinguished from redelivery; acknowledge this inherent limit.
Independent random event/producer IDs reduce accidental ambiguity but do not prove
authenticity or malicious-collision resistance against an authorized peer. A forced
different-content collision must be tested. No exactly-once transport claim: this
is bounded retry that may redeliver within one producer lifetime, with idempotent
insertion by ID; it does not guarantee that any attempt succeeds.

Pending state is RAM-only. Producer crash loses its own unacknowledged state;
there is no production restart replay guarantee or spool. For restart fault tests,
the producer supplies its complete frozen line to the parent through a bounded
private control pipe before its first send. The harness retains that synthetic
line in RAM only, not a disk outbox or payload log. An explicitly authorized
replacement producer receives that exact line over its trusted control pipe,
independently validates it and resends the same bytes, including original event ID,
producer instance and observation time. It does not normalize again, regenerate
IDs or relabel the event with its new PID/instance. If the harness has no complete
original line, stop the retry case; do not reconstruct guessed original content.
This is a test-only mechanism within the retry budget, not production durability.

## 5. IPC recommendation and failure semantics

### Endpoint and test peers

Use Linux pathname `AF_UNIX`, `SOCK_STREAM`, bidirectional, with close-on-exec
descriptors. Python listens at `<run-directory>/events.sock`; C++ connects. No
abstract socket, TCP, broker, socket activation or separate handshake is needed.
Each frame carries protocol version; an authenticated first event is sufficient.

The unprivileged harness creates a new private **VM-local** `/tmp/hids-m1-XXXXXXXX`
directory using secure temporary-directory creation and umask 077. Require mode
0700 and actual invoking UID ownership; all processes use that same non-root UID
with matching real/effective IDs and no special capabilities. Reject UID 0. Use a
path that fits Linux `sockaddr_un.sun_path`, including NUL; fail on an overlong path.
Do not use the UTM share, repository, home-wide socket or predictable fixed name
for runtime state. VM local-filesystem placement must be checked before running;
locality is not inferred from a directory name.

Python binds a fresh socket, sets/verifies mode 0600 before declaring readiness,
and refuses any pre-existing socket/path rather than unlinking it. The enclosing
0700 directory protects the bind-to-chmod interval. Both peers inspect Linux
`SO_PEERCRED`: receiver requires the harness-authorized producer PID and invoking
UID/GID; sender requires the harness-launched receiver PID and same UID/GID. Wrong
credentials close before reading event bytes, with no ACK or DB write. Credentials
refer to the connected peer's connection-time identity, not a user-supplied JSON
field. See [Linux Unix socket credentials](https://man7.org/linux/man-pages/man7/unix.7.html).

Use inherited harness control pipes to communicate expected child PIDs/readiness,
not an unauthenticated socket registration request. Launch receiver, wait for
startup readiness (DB initialization/settings/schema and socket setup successful),
launch a held producer, send its PID to receiver over the parent-owned
control pipe, wait for policy readiness, then release producer with the known
receiver PID. On an explicit receiver restart, update the producer's expected
receiver PID through this trusted harness path before reconnecting. On an explicit
producer restart, send the replacement producer's PID to the receiver through its
trusted control pipe, wait for policy readiness, and only then release the held
replacement with the current expected receiver PID and retained original line.
Revoke the old producer PID and close its old connection before authorizing the
replacement; serialize this with completion of any in-flight transaction. Both
peers must still match the exact expected PID and invoking UID/GID. A new PID
does not authorize a new event identity or an unauthenticated registration.
No event processing begins before the peer policy exists.
This scopes the test to two known children; it is not a production identity system.

### Framing and concrete pilot limits

These proposed numbers are conservative test/protocol bounds, **not measured
product CPU/memory budgets or production defaults**.

| Concern | Recommended M1 choice |
|---|---|
| Framing | Strict UTF-8 JSON object followed by one LF; no pretty-printed multiline documents. No blank lines, CRLF, BOM or raw CR. Normal JSON spacing within a frame is accepted |
| Event size | At most 65,536 payload bytes excluding LF. At capacity, consume an immediately following LF separately; reject the next non-LF byte before appending it. No unbounded `readline()` or discard-until-newline loop |
| Responses | At most 512 bytes excluding LF; same strict framing, exact control-frame keys/types and duplicate-key checks |
| Buffering | One 65,536-byte frame accumulator and a receive chunk no larger than 4,096 bytes; parse/process complete frames sequentially without retaining an unbounded list |
| Sender pending work | Exactly one immutable event/encoded line outstanding; do not admit another fixture until ACK. No disk spool or background queue |
| Receiver concurrency | One authenticated connection and one synchronous validation/transaction at a time; listen backlog 1, no worker pool |
| Deadlines | Five seconds per connect/frame-write/ACK-read/receiver partial-frame or idle wait, measured by a monotonic deadline that partial progress does not extend; each retry operation has its own 30-second total deadline |
| Reconnect | Initial operation and the one permitted explicit retry operation each allow at most three connection attempts, with 100 ms then 500 ms waits. Automatically retry only disconnection/timeout before a valid terminal response, using frozen pending content. Malformed responses stop automatic retries with outcome unconfirmed |
| DB busy | 1,000 ms SQLite busy timeout; report failure after timeout, no application infinite retry |
| Pilot growth | At most 100 distinct stored events per test database; refuse a new ID at the cap; identical duplicates still ACK. Bound total attempts by harness case/deadline and close readers/transactions promptly |

Consume LF as framing, never append it to the payload accumulator. Thus 65,536
payload bytes plus LF fit a 65,536-byte accumulator; the delimiter is not a 65,537th
buffered payload byte. Inspect each bounded receive chunk incrementally and check
capacity **before** appending a non-LF byte. Apply the equivalent rule to the
512-byte response accumulator. A complete frame still needs independent JSON and
contract validation. The sender also checks serialized payload length before its
first write; nothing accumulates an unbounded frame before checking its size.

Use nonblocking descriptors and readiness waits with remaining deadlines. Partial
`send()`/`recv()` is normal; keep byte offsets, retry EINTR against the same deadline,
and wait on EAGAIN/EWOULDBLOCK. Use `MSG_NOSIGNAL` for C++ socket sends. EOF with a
partial frame discards that frame and never persists it. EOF at a boundary closes
normally. A write completing proves only bytes sent, not receipt or commit.
One receive may contain split or multiple complete frames; consume each in order
within the cap, even though the normal sender waits for each ACK. Do not grow a
coalesced-message queue or process later frames after a terminal rejection.

### ACK, rejection and storage-error frames

Send this only after successful event commit; for an already committed equal row,
use `duplicate` instead of `stored`. Both mean the same immutable event is present.

```jsonl
{"protocol_version":1,"message_type":"ack","event_id":"84990d10-90c8-4ed5-a96a-9dbaebf3cfba","result":"stored"}
```

The C++ peer validates protocol, exact shape, matching event ID and result, which
must be exactly `stored` or `duplicate`. An unknown/mismatched/malformed response
is a terminal protocol error: stop automatic retries, retain unconfirmed outcome
and never infer rejection or successful persistence from it.
No native cn_proc ACK is involved, and this ACK promises no detection, enrichment,
backup, historical coverage or kernel delivery guarantee.

Terminal rejection shape:

```jsonl
{"protocol_version":1,"message_type":"reject","event_id":"84990d10-90c8-4ed5-a96a-9dbaebf3cfba","code":"id_conflict"}
```

Allowed rejection codes are `invalid_json`, `invalid_event`, `unsupported_version`,
`frame_too_large`, `id_conflict`, `capacity_exceeded`. `event_id`
is null unless a syntactically valid UUID can be obtained from an unambiguous
decoded frame; never echo arbitrary malformed text. No free-form payload/error
echo. After a bounded best-effort rejection write, close. Wrong peer credentials
are closed silently. A framing/JSON error uses `invalid_json`, except over-cap
frames use `frame_too_large`; unsupported wire/contract/ECS-reference version uses
`unsupported_version`; other field/type violations use `invalid_event`.

A storage exception must not use the rejection frame. Use this separate terminal
error shape, with exact keys and the single allowed code `storage_error`:

```jsonl
{"protocol_version":1,"message_type":"error","event_id":"84990d10-90c8-4ed5-a96a-9dbaebf3cfba","code":"storage_error"}
```

Here `event_id` must match the validated pending event. The error stops automatic
retry but means **unconfirmed**, even if rollback was attempted or the exception
appeared to precede commit. Use it for per-event storage exceptions only after the
pending event was validated; startup and later retrieval failures are separate.
no database exception alone proves absence of a committed row. If sending it fails,
closure without a terminal response remains unconfirmed. Attempt the response
within the response-write deadline, then close in either case; do not process
later frames from that connection. This is a clarification
of the provisional control vocabulary, not an additional transport or durability
mechanism.

### Complete producer response validation

All responses are single JSON objects within the 512-byte payload limit, with
the strict UTF-8/framing/depth/string rules already specified. Each row's key set
is exact: reject missing or unexpected keys and duplicate decoded JSON keys,
including escaped-equivalent duplicates. `protocol_version` must be the integer
`1`; a Boolean, float or numeric string is invalid. All other non-null values below
are strings, with no coercion. UUID strings use the same exact format as the event.

| Response | Exact keys | Required values and correlation |
|---|---|---|
| ACK | `protocol_version`, `message_type`, `event_id`, `result` | Integer version `1`; type `ack`; event ID matches the pending event; result exactly `stored` or `duplicate` |
| Reject | `protocol_version`, `message_type`, `event_id`, `code` | Integer version `1`; type `reject`; event ID is JSON null or matches the pending event; code exactly one of `invalid_json`, `invalid_event`, `unsupported_version`, `frame_too_large`, `id_conflict`, `capacity_exceeded` |
| Error | `protocol_version`, `message_type`, `event_id`, `code` | Integer version `1`; type `error`; event ID matches the pending event and cannot be null; code exactly `storage_error` |

Unknown response types, result/code values, unsupported response versions,
wrong/null IDs outside those rules and all malformed responses are terminal local
protocol errors. Stop automatic retries, retain **unconfirmed** transport outcome
and never accept such a frame as ACK or definite rejection. A malformed remote
response is not `local_failure / not_submitted`: transmission already occurred.

### Producer outcome and retry rules

| Outcome | Evidence / meaning | Producer action |
|---|---|---|
| Acknowledged | Valid matching `ack` with `stored` or `duplicate`: persistence of this immutable event confirmed | Clear pending slot and report success; no automatic resend |
| Rejected submission | Valid `reject`: this submitted candidate was definitely not accepted by the rejecting attempt; an `id_conflict` leaves a different original record intact | Stop automatic retries, report code, preserve pending identity/content until harness shutdown; do not change ID/content to bypass the rejection |
| Unconfirmed | `error/storage_error`, invalid ACK/control response, or closure/timeout without a valid result: persistence cannot be established | Keep frozen pending content while process lives; report uncertainty, not confirmed loss or rejection. Only closure/timeout automatically uses the bounded reconnect allowance; storage/protocol errors and exhausted attempts stop automatic retries |

Local preparation has a separate outcome, **`local_failure / not_submitted`**.
Use it for `observation_clock_failed`, UUID-generation failure and local native/
normalized validation, normalization or serialization failure before transmission.
Report the local stage/reason to the harness, fail the operation and transmit
nothing. It is neither receiver rejection nor unconfirmed DB commit, creates no
automatic retry and claims no receiver receipt. Discard incomplete state; never
hold an incomplete envelope for later submission. An operation that definitively
sent no event bytes in any attempt can likewise report `not_submitted` when its
connection budget ends, with no further automatic retry. Do not use this label
to erase any earlier uncertain transmission of the same candidate: a local failure
during a later retry is reported separately while the event remains unconfirmed.

A later rejected attempt does not erase uncertainty about an earlier attempt that
could have committed. If any earlier attempt remains unresolved, keep the whole
pending event **unconfirmed** unless a matching ACK confirms it (or a separately
authorized harness check establishes its stored content). Rejection is about the
submitted candidate/attempt, not a claim that no row with that ID has ever existed.
An acknowledged event is not undone by a later unrelated failure.

After a stopped unconfirmed operation, the harness may explicitly request retry
of the **original immutable event** once the receiver/storage fault is resolved;
use the same ID, provenance and clocks. A rejected original may likewise be
explicitly retried only after resolving its stated blocking condition; a conflict
must be investigated, never overwritten or assigned a new ID as an automatic fix.
If rejection requires changing the proposed content/contract, that is a separately
reviewed new submission, not a retry. No operator retry is implicit, no durable
outbox is added, and producer crash still loses RAM-pending state. Harness-retained
synthetic envelopes for fault tests remain a test-only mechanism. Idempotent
insertion protects resends; it does not establish exactly-once delivery.

**Explicit retry budget:** the initial transport operation has at most three
connection attempts and one 30-second monotonic deadline starting when its first
connection attempt begins. Delays before attempts two and three remain 100 ms and
500 ms and count toward that deadline; per-stage deadlines are capped by remaining
operation time. Exhaustion stops the operation, never resets its own budget and
never invokes an explicit retry automatically.

The harness permits **at most one additional explicit retry operation per original
event in an M1 test case**, requested deliberately after inspecting/resolving the
failure. That operation receives a fresh three-attempt budget, the same delays
and its own independent 30-second total deadline. It must use the exact original
frozen line, including original event/producer IDs and timestamps, even if a new
producer sends it. The harness records/limits this allowance across process
restarts; neither a new PID nor receiver restart resets it. Thus the two operations
allow at most six connection attempts total, not an unlimited operator-triggered
loop. Startup/inspection/waiting for explicit authorization is outside each
transport operation's timer but remains bounded by the test-case harness deadline.
After the one explicit operation ends, report the final acknowledged/rejected/
unconfirmed outcome (or a proven local `not_submitted` failure) and stop the case.
Additional investigation requires a separately authorized test, not automatic
counter reset or a replacement event ID to bypass this limit.

An incomplete original event from a local preparation failure cannot be retried
as an immutable event. A separately requested new fixture observation reruns local
preparation and is not called redelivery. A complete original retained before a
known `not_submitted` transport failure may use the same one explicit allowance.

### Receiver failure stages and deterministic recovery

| Stage | Required report and behavior |
|---|---|
| Startup before readiness | DB open/WAL/profile/schema initialization or socket setup failure: report `startup_failure` with bounded stage/reason to harness over the trusted control pipe, clean up owned handles and exit unsuccessfully. Do not declare readiness, accept event bytes or send event-specific `storage_error`; no validated pending event exists |
| Per-event storage | After successful event validation, any storage operation/receiver storage-clock failure: stop accepting events, attempt `error/storage_error` with that event ID within deadline, roll back where possible, close/clean up, report failure to harness and exit unsuccessfully. The producer's event outcome is unconfirmed |
| Terminal request protocol failure or any terminal rejection | Stop accepting events; attempt the appropriate rejection if safe, close/clean up, report failure to harness and exit unsuccessfully. No later coalesced frame or new connection is processed |
| Post-commit retrieval | Separate harness-invoked read-only verification failure: report `retrieval_failure` and fail that verification step, without event-wire `storage_error` or rollback of a completed ingest. A known successful commit remains committed; an already acknowledged event stays acknowledged. If no ACK was observed, failed retrieval cannot resolve that uncertainty |

There is **no in-process reopen-and-continue path** after terminal storage/protocol
failure. Close the listener as soon as that failure is detected; cleanup does not
enable another event. Only an explicit harness action may restart a receiver,
using the same protected known pilot database after verifying its version/schema
and independently configuring a new writer connection. The restarted process
rechecks stored content through normal ID deduplication. No automatic supervision,
background recovery, spool replay or production crash-recovery guarantee is added.

Plain transport disconnect/timeout is distinct from a terminal request/storage
failure: discard an incomplete frame, or finish/clean the current transaction,
close that client connection and remain available for the already bounded reconnect
policy if no terminal failure occurred. A lost ACK write after successful commit
is such a transport failure; retain the committed row for deduplication. Wrong-peer
credentials still close before reading any event bytes. The harness may stop a
receiver when the producer reports a response protocol error; no automatic restart
follows. Neither disconnect nor a failed ACK write authorizes reopening a damaged DB.

Receiver startup still refuses a pre-existing socket path. For explicit restart,
first reap the old receiver and complete cleanup; if its socket pathname remains,
the harness may remove only that exact recorded socket after checking its type,
ownership and recorded file identity. A mismatch aborts restart. Do not sweep stale
paths or delete/replace the database, WAL or SHM files. All operations occur only
within the original harness-owned private directory.

### Persistence order, backpressure and shutdown

For each authenticated complete frame: strict decode → validate → canonicalize →
transaction/deduplicate → commit → ACK. No early receipt ACK. If the receiver is
slow, the single pending slot stops fixture intake and stream buffers apply
backpressure; no discard-as-success behavior. Sender timeout may reconnect while
the old transaction completes; receiver finishes/cleans that transaction before
serving a new connection if no terminal failure occurred; otherwise it exits and
only an explicit harness restart can serve a subsequent retry. Deduplication in
the continuing or explicitly restarted healthy receiver handles the uncertain result.

On orderly shutdown stop intake; finish or roll back the current transaction and
attempt its response against a five-second shutdown deadline, then close sockets
and DB. This is a cooperative cleanup target: synchronous SQLite/filesystem I/O
can exceed it; the busy timeout bounds lock waiting, not a stalled device. The
harness must flag deadline failure and request termination of its owned child,
without claiming a hard I/O cancellation or guaranteed cleanup/commit outcome.
SIGINT/SIGTERM handlers request shutdown only; cleanup runs in normal
control flow. A killed process cannot promise cleanup or delivery. Lost ACK after
commit is safe to retry; disconnect before any complete frame produces no row.
Do not recreate native LISTEN/IGNORE operations as part of IPC retry.

Receiver records bounded stage/error-code diagnostics and returns failure on
storage/protocol failure; producer reports acknowledged/rejected submission/
unconfirmed transport outcome, or `local_failure / not_submitted` for proven local
non-submission, according to the rules above, separately from the fact that
automatic retries have stopped. Logs contain IDs/reason codes only for these synthetic tests,
never event payloads. The harness enforces an overall test deadline, reaps only
its own children and preserves failure evidence privately. Only after closing all
handles may it remove the exact fresh directory it created; no broad `/tmp` cleanup.

### Alternatives considered

| Alternative | Why not recommended for this pilot |
|---|---|
| Datagram/SEQPACKET socket | Adds message-boundary/truncation semantics; stream + LF directly exercises the accepted initial framing and partial I/O requirements |
| Receipt-only/no ACK | Cannot establish the requested durable storage boundary |
| Durable producer spool | Useful future option but adds crash recovery, disk/retention and privacy obligations unnecessary for one RAM-pending fixture |
| Multiplexing, handshake negotiation, batches | Explicit versions, one outstanding event and terminal unsupported-version response suffice; no need to negotiate unspecified contracts |
| UID-only peer allowlist | Broader than the two intended test processes; exact PIDs plus UID/GID narrow this harness without defining service accounts |

## 6. Dependency and build assessment

### What was actually checked

The repository has no CMake/Make configuration, Python dependency manifest,
lockfile, vendored JSON library or shared executable schema. Its existing C++
adapter uses standard/system headers, not a JSON dependency. The current local
macOS PATH resolves `/usr/bin/python3` (Python 3.9.6), Apple compiler commands
`clang++`/`g++`, and no `cmake`/`pkg-config` command. Python reports SQLite runtime
3.43.2. Distribution metadata for `pydantic`, `jsonschema`, `orjson`, `pytest` is
absent for that interpreter; no corresponding dependency is declared in-repo.
Top-level module discovery also found none of those four modules importable there.
No nlohmann, Boost.JSON, RapidJSON or json-c headers were found at their usual
names under `/usr/include`, `/usr/local/include`, `/opt/homebrew/include`. This
is a scoped check, not proof that no other environment/package location has them.

No Ubuntu VM was inspected during M0. The owner-reported GCC 15.2.0 and native
offline-test results are preserved in the [validation record](../validation/collector-ubuntu-validation.md).
Ubuntu Python/SQLite versions, JSON headers, license notices and tool availability
must be inventoried **before M1 execution** with existing tools; missing tools
stop that run rather than authorize installation. Local macOS Python 3.9 is not
the recommended deployed interpreter or proof of Ubuntu compatibility.

### Recommended minimum

| Component | Proposal, version and license | Alternatives / assessment |
|---|---|---|
| C++ JSON | **One new dependency:** nlohmann/json **3.12.0**, MIT. Use library values/serializer for event/control JSON and library parser for fixture/control input | Header-only and no linked JSON runtime. Pin exactly; do not fetch latest during build. More compile-time/DOM cost than a specialized codec, acceptable for this bounded pilot; measure before production claims |
| Python JSON/validation | Existing CPython 3 standard-library `json` plus explicit closed-contract validation; recommend existing Ubuntu CPython 3.10+ if available, record exact version; PSF license terms/notices | No Pydantic/jsonschema/fast JSON package required. Exact-key/type/range/null checks and shared vectors are small enough here. Reassess generated/shared schema tooling later rather than introduce a second dependency now |
| Python tests/control | Standard-library `unittest`, `subprocess`, `socket`, `tempfile`, `uuid`, `datetime`; same interpreter/license | No pytest requirement, virtualenv package install, HTTP stack or broker for M1 |
| SQLite | Standard-library Python `sqlite3` linked to the VM's existing SQLite **3.22.0+**, exact runtime recorded; SQLite deliverable is public domain | Feature minimum for read-only WAL retrieval under the access conditions below; no C++ SQLite dependency or Python ORM. Stop if required support/access is absent; no package upgrade implied |

Version/license evidence: [nlohmann/json 3.12.0 release](https://github.com/nlohmann/json/releases/tag/v3.12.0),
[pinned MIT license](https://github.com/nlohmann/json/blob/v3.12.0/LICENSE.MIT),
[official single-header integration](https://json.nlohmann.me/integration/),
[Python license](https://docs.python.org/3.13/license.html), and
[SQLite dedication](https://www.sqlite.org/copyright.html). The runtime's actual
license notices must accompany any future redistribution; no dependency was
downloaded, installed or added to manifests during this proposal.

**Recommendation requiring approval:** vendor the pinned upstream single
`json.hpp` with MIT license and a provenance/digest note under
`collector/third_party/nlohmann/` in the future M1 change. No configure-time
network fetch, system package install or new build framework. Review upstream
artifact provenance and record its digest when obtaining it; no checksum is
invented here. Use existing `c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror`,
repository include paths and the reviewed third-party include directory; put
objects/executables in a private temporary build directory. Preserve the existing
offline-suite and complete production-link recipes.

Use library SAX callbacks to bound nesting and detect duplicate object keys before
the C++ DOM parse of untrusted fixture/response JSON; abort on violations. This is
validation through the library parser, not hand-written JSON syntax/escaping.
See [nlohmann SAX API](https://json.nlohmann.me/api/basic_json/sax_parse/).
Catch allocation/parse/serialization exceptions outside native callbacks and fail
the pending operation. Never concatenate JSON strings manually.

Python must UTF-8-decode strictly, enforce the frame cap and a string-aware
container-depth precheck (honoring quotes/escapes), then use `json.loads` with an
`object_pairs_hook` that rejects repeated keys and `parse_constant` that rejects
NaN/Infinity. The depth precheck limits resources; the standard parser remains
the syntax authority. Reject float types in the contract and use `type(x) is int`
for integers. Validate calendar dates explicitly. Built-in parser defaults alone
are insufficient; see [Python JSON behavior](https://docs.python.org/3.13/library/json.html).
Use the same strict decoding for retrieval integrity checks.

Other C++ alternatives: Boost.JSON would add Boost components without existing
repository support; RapidJSON could provide a bounded SAX-based implementation
but is not currently present; json-c adds a C interface/linked runtime. No choice
among their versions is requested because none is recommended or introduced.
Standard C++20 has no built-in JSON codec. An ad hoc serializer/parser is rejected;
if the proposed library is not approved, revise M0 rather than implement escaping.

## 7. SQLite pilot model and retrieval

Recommend one table and `PRAGMA user_version=1` for a **separate disposable pilot
database**, not the production schema version. Python alone creates, migrates,
opens for writing and commits it. C++ never receives a DB handle or path as a
storage interface. SQL values are bound parameters, never string interpolation.

Proposed DDL for review, not an installed schema:

```sql
CREATE TABLE pilot_events (
    event_id TEXT NOT NULL PRIMARY KEY,
    contract_version TEXT NOT NULL,
    source_adapter TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    storage_attempt_at TEXT NOT NULL,
    CHECK (contract_version = 'm1.process-exec/0.1.0'),
    CHECK (source_adapter = 'linux.cn_proc'),
    CHECK (source_mode = 'sanitized_fixture')
);
```

`envelope_json` is the validated comparison encoding of the entire immutable
message, bounded by the frame/contract validation. It preserves event identity,
producer/source/fixture provenance, native fields, versions, monotonic decimal
string/units, explicit null activity time and original observation. No raw netlink
blob, command lines, environment, user/host identifiers or structured `event.original`
is retained. Redundant columns support source/version inspection; Python derives
them from the validated payload and checks them on retrieval. Only the primary
key index is needed for this retrieval-by-ID milestone.

`received_at` records the receiver's UTC observation when the first complete
accepted message was received. `storage_attempt_at` is another UTC observation
taken just before insertion within the transaction. Use the same six-digit UTC
format as `observed_at`. Neither field is an exact commit timestamp, guaranteed
chronological ordering, activity time or part of duplicate-content comparison.
Keep original row times on duplicate. Clock-read failure fails before insertion.
In receiver per-event storage preparation, such a clock failure uses the validated
pending ID and the terminal storage-failure path; it is not the producer's local
pre-transmission clock failure.

Python uses explicit transaction management (`isolation_level=None` plus explicit
`BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`), avoiding interpreter-dependent implicit
transaction defaults. Inside the transaction: look up the ID; compare full text
if present; otherwise check the 100-row cap, insert, then commit. On an ID conflict
roll back; never `INSERT OR REPLACE`. Serialize writes through this single owner.
On a per-event storage error roll back when possible and report
`error/storage_error` with unconfirmed outcome, not proof of non-commit. Stop
accepting events, close the connection and exit unsuccessfully; do not reopen and
continue inside that receiver. Only an explicit harness restart may open a new
connection after cleanup/inspection. A subsequent successful lookup may establish
existing content, but a failed lookup establishes no absence. Use the normal
immutable-ID comparison when an explicitly restarted receiver receives a resend.
Do not delete the database as a recovery technique. SQLite errors can affect
transaction state differently; see [SQLite transaction error handling](https://sqlite.org/lang_transaction.html#response_to_errors_within_a_transaction).

### Database settings versus connection settings

Configure each new connection, including explicit receiver restart and retrieval, before
starting any transaction. Do not rely on another connection's settings or Python
wrapper defaults. Only WAL journal mode below persists in the database; the other
four settings must be configured per connection (and per `main` database where
applicable). Pilot schema `user_version` is separately persistent metadata.

| Setting / scope | Writer connection | Read-only retrieval connection |
|---|---|---|
| `main.journal_mode` — WAL is persistent | On fresh DB set `WAL` outside transactions and verify returned `wal`; on reopen query and require `wal`, no silent mode conversion | Query and require `wal`; never issue a journal-mode change |
| `main.synchronous` — per connection/database | Set `FULL`, query and require `2` on every open | Explicitly set/query `FULL` (`2`) outside transactions for a deterministic connection profile; it does not establish durability of another writer's commit |
| `busy_timeout` — per connection | Set/query `1000` milliseconds | Independently set/query `1000` milliseconds; busy/read failure is an error, not missing event |
| `wal_autocheckpoint` — per connection | Set/query `1000` pages on every open | Set/query `0`; this connection does no writes or explicit checkpoints |
| `main.journal_size_limit` — per connection/database | Set/query `1048576` bytes on every open | Independently set/query `1048576` for a deterministic profile; no writer/checkpoint role is assigned to the reader |

These are pilot connection profiles, not production retention defaults. The
retained-journal limit does not cap active WAL growth. Keep row/frame caps, short
readers and bounded tests; commit ACK still depends on successful writer commit
and platform durability. Fail on unsupported settings or unexpected query results.
References: [journal mode](https://sqlite.org/pragma.html#pragma_journal_mode),
[synchronous](https://sqlite.org/pragma.html#pragma_synchronous),
[journal size limit](https://sqlite.org/pragma.html#pragma_journal_size_limit),
[connection busy handler](https://sqlite.org/c3ref/busy_timeout.html) and
[connection autocheckpoint](https://sqlite.org/c3ref/wal_autocheckpoint.html).

Initialize version 0 to pilot version 1 in an explicit Python transaction on a
fresh database; reject an unexpected nonempty/versioned database rather than
guessing a migration. For recovery tests an explicitly restarted receiver opens
only the known owned version-1 database and verifies its schema/settings before
declaring readiness. Initialization failure is `startup_failure` through the
harness, never an event-specific error. Future production migrations and reuse
of pilot files require a separate decision; do not import them automatically.

Retrieval is a Python internal repository method, proposed
`get_event(event_id) -> validated envelope or None`, with a UUID argument and a
parameterized primary-key query. No arbitrary SQL/path operation, HTTP endpoint
or new retrieval wire message. After commit, use a fresh read-only connection
(`mode=ro`, not `immutable`) to the harness-known path and verify ID/columns/
contract/content, after applying the retrieval connection profile above. Missing
ID returns `None`; invalid stored data or DB failure is
an explicit error, never a fabricated empty history. The harness receives only
synthetic results and compares the envelope to the sender's expected values.

Opening fragment for the retrieval connection, after the harness has approved an
existing absolute path inside its private directory:

```python
from pathlib import Path
import sqlite3

db_path = Path(harness_db_path)  # Trusted harness path, not a supplied URI.
if not db_path.is_absolute():
    raise ValueError("retrieval requires an approved absolute database path")
db_uri = db_path.as_uri() + "?mode=ro"
reader = sqlite3.connect(db_uri, uri=True, isolation_level=None, timeout=1.0)
```

`Path.as_uri()` encodes path characters such as spaces, `%`, `?` and `#`; appending
the fixed query to that URI cannot turn filename characters into URI parameters.
It does not perform the required ownership/no-symlink/path authorization checks.
Before lookup, apply and verify every retrieval-profile setting above; always
close `reader` in `finally`, including profile/lookup failure. The fragment is an
opening example, not a complete validator or retrieval implementation. References:
[Python path URI conversion](https://docs.python.org/3.13/library/pathlib.html#pathlib.Path.as_uri),
[Python SQLite URI connections](https://docs.python.org/3.13/library/sqlite3.html#how-to-work-with-sqlite-uris)
and [SQLite URI filenames](https://sqlite.org/uri.html).

Lookup errors after a known commit are `retrieval_failure` in the harness, not
ingest `storage_error`. They cannot revoke a commit ACK, trigger event rewriting
or classify the event as rejected/uncommitted. Keep successful commit/ACK evidence
separate from failed retrieval evidence; failed retrieval proves neither presence
nor absence. An unexpected `None` when verifying a known committed event also
fails retrieval verification; it does not revoke prior commit/ACK evidence.
If retrieval fails while initializing its connection profile, that
is likewise a retrieval-operation failure, not receiver startup failure.

### Read-only WAL access requirements

Require SQLite **3.22.0 or later** for this pilot's read-only WAL retrieval.
SQLite's [read-only WAL documentation](https://sqlite.org/wal.html#read_only_databases)
requires readable existing `-wal` and `-shm` files, or directory write permission
to create them; it also describes an immutable option, which this pilot excludes
because the database may change. Main-DB read permission alone is insufficient.

The same-UID pilot uses its owned 0700 local directory and 0600 DB/sidecars: while
the writer remains open, verify existing sidecars are readable and permit the
normal shared-memory coordination. After writer shutdown, sidecars may have been
removed; retrieval must be able to create required files within that same private
directory, or report failure. Do not manually create/copy/delete WAL/SHM files or
change to `immutable` to bypass an access problem. `mode=ro` prevents event-table
writes through that connection; it does not promise zero filesystem side effects
from SQLite sidecar creation/coordination. Do not remove a live WAL as temporary
garbage or interpret access/locking failure as `None`/empty history.

SQLite DB/WAL/SHM files must be owned by the test UID, mode 0600 or stricter, and
contained in the 0700 directory. Verify any sidecars while open. No shared-folder
database or public export. The C++ process sharing this UID could technically open
the file; test-harness restrictions are not production privilege separation.

## 8. Proposed test matrix and acceptance evidence

All tests use synthetic fixtures and local private state; no root, HTTP listener,
live netlink socket or real system-record reader. Standard-library Python tests
orchestrate built C++ producers and receiver processes; native unit tests remain
independent. Failure hooks are internal injectable test seams, never public API
commands. Each case has a fresh run directory/DB except intentional recovery cases.

| Case | Required assertions |
|---|---|
| Valid EXEC round trip | Construct native packet → existing parser → C++ normalizer/validator → stream → Python validator → commit ACK → fresh-connection lookup; exact IDs, provenance, native types/values and all clocks preserved |
| Missing activity wall time | Required null/reason accepted and retrieved unchanged; no `@timestamp`, epoch zero or observation-time substitution |
| Monotonic/PID semantics | Above-2^53 timestamp and uint64 maximum round-trip as strings; reject overflow/negative/noncanonical values; differing PID/TGID preserved; EXEC parent null; CPU/sequence zero accepted |
| Invalid event | Both validators reject missing/unknown keys, boolean/float IDs, bad UUID/constants/calendar/ranges/parent, wrongly typed version fields, activity-time substitution and non-ASCII strings; zero inserts, no success ACK |
| Unsupported versions | With an already stored ID, separately change otherwise valid contract version and protocol version: each yields `unsupported_version` before identity comparison, never `id_conflict`; original row unchanged. Reference-version mismatch follows the same rule |
| Local pre-transmission failures | Inject observation read/format failure (`observation_clock_failed`), native/normalized validation, normalization and serialization failure: `local_failure / not_submitted`, unsuccessful operation, no receiver rejection or uncertain commit claim, no event bytes or automatic retry. Discard incomplete state; an event already uncertain from an earlier operation stays uncertain |
| UUID failure/partial progress | Inject positive short reads and EINTR before completing 16 bytes; both IDs receive correct UUIDv4/variant bits. Inject zero return, EAGAIN and terminal error after partial progress: `local_failure / not_submitted`, no incomplete ID/fallback/transmission or automatic terminal-error retry |
| Malformed JSON | Bad UTF-8/BOM/CRLF/blank line, trailing data, duplicate/escaped-equivalent keys, non-finite numbers, over-depth/over-string-limit and invalid escapes rejected with bounded behavior; no payload echo |
| Native malformed input | Truncated/wrong native fixture produces no envelope; zero diagnostics required for successful source decode; no socket opened to collect native data |
| Split/coalesced frames | One byte at a time including split LF; two complete frames in one write; sequential correct ACKs and bounded accumulators, no loss/extra event |
| Partial writes/readiness | Force short writes, EINTR, EAGAIN, stale readiness and peer closure; correct offsets/deadlines, no SIGPIPE or duplicate ID assignment |
| Malformed ACK/control response | Invalid JSON/UTF-8, missing/extra keys, duplicate keys, wrong types, mismatched event ID, unsupported response version and unknown ACK result (for example `pending`) all stop automatic retries with unconfirmed outcome, no success or definite rejection; explicit frozen-event retry remains possible after resolving the protocol fault |
| Malformed reject/error frames | Apply the complete response table to both: missing/extra/duplicate keys, Boolean version, wrong types, wrong ID, unknown type/code or version are protocol errors with unconfirmed outcome and no automatic retry. Reject with null or matching ID is valid; error with null ID is invalid. No malformed frame becomes definite rejection |
| Oversized message | Exactly 65,536 payload bytes plus separately consumed LF fit a 65,536-byte accumulator; the next non-LF byte is rejected before append, with/without a following LF. Response cap 512 similarly tested. Contract validity is independent; bounded chunks cannot cause oversized accumulation or a draining loop |
| Duplicate delivery | Same immutable event repeated, plus whitespace/key-order variation: one row, `duplicate` ACK, original receiver times unchanged; same native values with a fresh event ID insert a distinct row |
| ID collision | Existing ID with changed native value, producer instance or observation, still fully valid under supported versions: `id_conflict`, original row/times unchanged, no success ACK. Equal valid content gets `duplicate`; version changes belong in the unsupported-version case |
| Disconnect before persistence | Before LF: no row. After complete frame but before commit: injected rollback variant has no row; a receiver allowed to finish may commit. No ACK means unknown; resend resolves via insert/dedup |
| Disconnect after persistence | Commit then suppress/lose ACK; resend original envelope after reconnect/restart gives one row and `duplicate`, proving no exactly-once transport assumption |
| Startup initialization failure | Inject DB open, WAL/profile setup or schema initialization failure before readiness: harness `startup_failure`, unsuccessful receiver exit, no readiness/event acceptance/event-specific response or fabricated pending ID; owned cleanup only |
| DB write failure | Inject write/commit/busy/full failures, including commit-success-then-exception: terminal `error/storage_error` with validated ID, unconfirmed outcome and no automatic retry or false rejection. Stop accepting, attempt rollback/close, report failure and exit; only explicit inspected restart can receive an original-envelope resend and insert/deduplicate. Failed lookup proves no absence; no deleted DB |
| Terminal receiver recovery | Bad JSON/version/event/ID-conflict rejection and terminal storage failure stop listener, do not process later coalesced frames or queued connections, report failure and exit without in-process reopen. Explicit restart revalidates known DB/settings and reauthorizes peer PID; plain transport disconnect/lost ACK may still use bounded reconnect without DB reopen |
| Outcome transitions | Valid ACK confirms storage; valid reject confirms non-acceptance by that attempt; storage/protocol failure remains unconfirmed. Later rejection cannot erase unresolved prior-commit uncertainty. Test explicit same-envelope retry after fault resolution, and exhausted automatic attempts without an exactly-once claim |
| Explicit retry budget | Exhaust initial three attempts/30-second operation, verify no automatic reset, then explicitly authorize the one additional operation: fresh three attempts, 100/500 ms delays and independent 30-second deadline. Exact frozen line retained; restart does not reset allowance; reject a second explicit operation in the same case. Stop earlier on ACK/terminal response; no real waiting required in deadline unit tests |
| Retrieval after commit | Fresh `mode=ro` connection retrieves exact payload by ID; known absent ID yields `None`; corrupt/mismatched payload or read/access/locking failure raises an error. Verify readable WAL/SHM while writer is open and allowed private sidecar creation after writer shutdown; no `immutable` fallback |
| Post-commit retrieval failure | Inject read-only connect/profile/query/content-validation failure after successful commit/ACK: harness `retrieval_failure`, failed verification step, original committed row/ACK retained, no retroactive reject/uncommitted claim or ingest error frame. Failed retrieval with missing ACK leaves unconfirmed outcome |
| Read-only URI example | Syntax-check opening fragment and verify path URI encoding for spaces, `%`, `?`, `#` and non-ASCII filenames; fixed `mode=ro` query cannot be injected by a filename. Later integration must verify read-only opening, full connection profile, no event writes and guaranteed close |
| Connection initialization/reopen | Record SQLite version at least 3.22.0; new writer/read-only connections each apply/query their specified profile. Change nondefault settings on one test connection and verify fresh connections are independently configured, without assuming inheritance; persistent WAL survives reopen. Missing sidecar access is an explicit failure |
| Bounded growth/backpressure | Slow receiver/DB holds one sender pending item; timeout/cap behavior visible. 100 distinct IDs accepted, next new ID rejected, existing duplicate still acknowledged; no spool/unbounded queue |
| Peer/path security | Wrong allowed PID/UID/GID rejected, positive matching credentials on Ubuntu; preexisting/symlink/overlong path rejected; directory/socket/DB/sidecar permissions checked; root invocation fails |
| Producer restart/reauthorization | Reap old producer, serialize old transaction completion, revoke old connection/PID, hold replacement until trusted control-pipe PID policy readiness. Old/wrong PID cannot communicate; correct replacement retains same non-root UID/GID and receiver-PID check and sends exact harness-retained original line/IDs/time. No original line means no reconstructed retry; explicit-operation budget survives restart |
| Shutdown/deadlines | SIGINT/SIGTERM during framing/transaction/ACK follows bounded cleanup; no orphan harness child; stop/unknown result reported honestly; cleanup touches only owned run state |
| Existing regressions | Both native offline suites, strict C++ compilation, complete production link smoke; ASan/UBSan where already supported. No native code changes expected |

The first M1 Ubuntu run must record exact OS/kernel/architecture, compiler,
Python/SQLite/library versions, dependency artifact digest, invoked recipes,
fixture identity, test outcomes and private-state permissions. Unit results and
actual two-process integration results must be distinguished. The harness can
assert that no production netlink backend is linked into its producer and no
live-source calls occur; unit doubles are not a substitute for the Ubuntu Unix
socket/credential/filesystem round trip.

**M1 acceptance:** one fixture demonstrably reaches durable storage/retrieval;
the failure/identity/framing/security matrix passes; C++ and Python independently
validate; Python owns every write; absent activity time remains absent; bounds and
uncertain outcomes are explicit. This is not v0.1 release acceptance, a resource
benchmark, production identity validation or live collection reliability evidence.

## 9. Security boundary and explicit non-goals

This is an isolated same-user **synthetic-data harness exception**, not permission
for an ordinary human to read real HIDS security records. Root-only production
dashboard/data authorization, unprivileged Python service design and per-adapter
collector privileges remain unchanged. No production accounts, group grants,
capabilities, sudo, service units or real records are introduced. A same-UID
compromise can interfere with the pilot; exact peer PIDs and 0700/0600 modes do not
claim isolation between processes sharing that UID or protection against root.

No M1 source discovery UI, real-source confirmation state, `/proc` enrichment,
authentication/system-log adapter, live cn_proc subscription, ACK kernel probe,
kernel/logging/Audit/PAM change, package installation or Ubuntu configuration.
No alerts/rules, correlation, evidence aggregation, dashboard, FastAPI/SSE,
HTTP/TCP, AI analysis or remediation. No production retention policy, service
identity, dashboard authentication, final ECS mapping or universal DB/IPC contract.
No producer crash-durable spool, unbounded replay, throughput or delivery guarantee.
No benchmark or experiment is run by writing this design.

## 10. Owner approval package and remaining gates

The architecture is approved in principle; each concrete P-01–08 package below
still requires **explicit owner approval**. Approve or amend these together before
M1 coding; there should be no hidden architectural choice left to implementers.

| Approval | Concrete choice to review | Scope retained as unresolved |
|---|---|---|
| P-01 — fixture integration (D-02) | Direct existing parser → copied native event → separate normalizer; one synthetic EXEC fixture, no collector start/rewrite | Live handoff/scheduler and other event families |
| P-02 — envelope/time (D-02/D-04) | Exact versioned shape/rules/example above; explicit absent activity wall time, lossless monotonic decimal string, observation clock and native provenance | Canonical ECS/custom paths, cross-boot/namespace identity and activity-time policies for other sources |
| P-03 — identity (D-03) | C++ random UUIDv4 event/producer IDs, frozen retry content retained in test-harness RAM for replacement sender, full-text semantic duplicate comparison, conflicting ID rejection | Production producer crash replay, source-native duplicate identity, collision handling UI |
| P-04 — IPC (D-06) | Stream/JSON Lines, complete ACK/reject/error validation, acknowledged/rejected/unconfirmed plus local not-submitted outcome, commit ACK; three attempts/30 seconds per operation and one explicit extra operation, bounded one-pending state, LF outside payload cap, no spool | Multiplexing/batching/negotiation and production reconnect/durability budgets |
| P-05 — harness security (limited D-01) | VM-local private state, same non-root UID, exact PID+UID/GID checks and trusted-pipe reauthorization for either replacement peer, 0700/0600 modes, original synthetic event only | Production service identities/source privileges, root-only human auth and installed socket path |
| P-06 — storage (D-07/limited D-09) | SQLite 3.22.0+, one pilot table/version, explicit transactions and verified writer/reader profiles, WAL/FULL/bounds, immutable rows, encoded read-only URI/sidecar requirements; separate startup/storage/retrieval failures, terminal receiver exit and explicit-only restart | Production tables/indexes/migrations/retention, detection transactions and service recovery |
| P-07 — dependency/build (D-13) | Approval to obtain/vendor nlohmann/json 3.12.0 with MIT/provenance; no other added dependency; existing compiler recipes and standard-library Python validators/tests | Global build/package tooling, deployed dependency/runtime versions |
| P-08 — evidence/limits | Full matrix, separately recorded Ubuntu execution/preflight and unchanged native regressions; pilot thresholds explicitly not product budgets | Live connector/service-account validation, v0.1 resource benchmarking and release acceptance |

Approve acquisition method/version/license before adding the JSON header. If VM
preflight finds an absent or incompatible tool/runtime, report the exact blocker
and request a separate dependency decision; do not install or silently change
technology. Owner approval of this document alone does not install accounts,
grant privileges, authorize real collection or finalize production contracts.

**Next action after review:** a separate M1 implementation task referencing the
approved P-01–08 choices, limited to the fixture/parser/normalization/IPC/validation/
SQLite/retrieval slice and tests. Preserve broader product/security decisions and
return any discovered contract conflict to the owner before changing this pilot.
