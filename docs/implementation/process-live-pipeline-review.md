# First installable build: process pipeline contract review

Status: **owner approved C-01 through C-04 and the bounded implementation/acceptance sequence**.
Owner replied yes to the linked contract before implementation.
November 13, 2026. Existing M1/M2/M3/M4, D-12c and D-14a approvals remain valid.
The owner prioritizes a first installable Ubuntu build, then reassessment; this
review does not silently shrink or declare completion of the accepted v0.1 scope.

## Recommendation and decision

Approve one narrow, versioned process-lifecycle pipeline using the newly validated
zero-capability identity. Carry native fork/exec/exit metadata through C++
normalization and independent Python validation into a new protected store. Retain
explicitly missing activity wall time; do not invent an executable path, user,
process entity identity or security finding from these native records.

This settles only the contract/identity/storage/live-consent decisions below for
this pipeline. It is not approval for a new rule, `/proc` enrichment, log permission,
CA, autonomous restart, automatic deletion or Git publication. Collection still
requires explicit source selection and fresh root activation under D-14a.

## C-01: exact role and live consent

Use existing dedicated nonlogin `hids-process`, its own primary group, no
supplementary groups and zero capabilities; Python storage runs as the existing
`hids-ingest` service identity. Human security-data access stays root/sudo-only.
Collector has no database/log access; Python never opens the process source.
Root owns config, units and source/session scope. Use a root-created private Unix
stream listener, available only to the process role, with independent peer UID
checks at both ends; root/socket activation passes the listener to the backend.
The backend may not authorize collection on its own. No source is started during
installation, discovery, UI recommendation, draft staging or authentication.

After root confirms `proc_lifecycle` and starts it, collect system-wide native
fork/exec/exit records in the initial namespaces. Unlike the owned-child trial,
this explicitly permits retaining other processes' lifecycle metadata in the
protected local store. Stop before changing an active source selection. No live
payload goes to stdout/journal or unauthenticated APIs. Refuse root or capability
fallback. A runtime restart loses collection authorization; fresh root start is
required. No automatic source reconnect/subscription retries.

## C-02: closed, versioned event and native provenance

New contract `process.lifecycle/0.1.0`, JSON Lines protocol integer version 1;
M1's `m1.process-exec/0.1.0` fixture contract stays unchanged. No old source/store
is relabelled or imported. Every key has a documented role; additional/duplicate
keys, unsupported versions, wrong scalar types and invalid combinations reject.
Maximum event frame 16 KiB; maximum response 1 KiB. No arbitrary native text blob.

Required top-level objects: `protocol_version`, `message_type`, `contract_version`,
`ecs_reference_version`, `event_id`, `producer_instance_id`, `source`, `native`,
`timestamps`, `normalized`. `message_type` is `event`, ECS reference is `9.5.0`.

- `source`: adapter `linux.cn_proc`, mode `live` (or separate synthetic mode only
  in isolated tests), stable root-provisioned source UUID, fresh root activation
  UUID, canonical kernel boot UUID and fixed profile `linux.cn_proc.lifecycle/1`.
  Scope and exact authorized peer must match receiver configuration.
- `native`: `what`/`what_code` for FORK=1, EXEC=2, EXIT=2147483648; signed-positive
  32-bit `tid`/`tgid`; parent null for EXEC, otherwise the supplied parent TID/TGID
  pair (nonnegative 32-bit); unsigned 32-bit CPU and connector sequence; unsigned
  64-bit kernel monotonic nanoseconds as canonical decimal string; null exit status/
  signal for non-EXIT, unsigned 32-bit raw values for EXIT. No numeric conversion
  to a JavaScript floating-point timestamp and no reinterpretation as exit(3) code.
- `normalized`: ECS-based nested `event` and `process` objects, with only mappings
  below. Both validators require equality with their native/envelope inputs.

| Field | Exact proposed meaning |
|---|---|
| `event.id` | Same opaque UUID as envelope event_id |
| `event.kind` | `event` |
| `event.category` | Array containing only `process` |
| `event.type` | FORK `creation`, EXEC `start`, EXIT `end`, each a one-item array |
| `event.action` | `fork`, `exec`, `exit` respectively; no maliciousness assertion |
| `event.provider` | `linux.cn_proc` |
| `event.created` | Same collector observation UTC value as timestamps.observed_at |
| `process.pid` | Native TGID, not native TID |
| `process.thread.id` | Native TID |
| `process.parent.pid` | Native parent TGID only when positive; otherwise absent |

No `process.entity_id`, `process.start/end`, `process.executable`, user identity,
command arguments/environment, exit-code interpretation or process relationship
cache. Thread creation/exit remains visibly distinct through TID versus TGID;
UI must not label every such event a new/ended whole process.

Pinned primary references: [ECS 9.5 process fields](https://raw.githubusercontent.com/elastic/ecs/v9.5.0/schemas/process.yml),
[event fields/categories](https://raw.githubusercontent.com/elastic/ecs/v9.5.0/schemas/event.yml).
These define field meanings/types; the particular mappings above are HIDS proposals.
This is an **ECS-based subset envelope**, not full ECS conformance. In particular,
ECS requires `@timestamp`; HIDS deliberately omits it where activity wall time is
unknown. Keep `ecs_reference_version` metadata, not a claim via `ecs.version` that
this incomplete envelope conforms to all ECS requirements. See the pinned
[generated timestamp definition](https://raw.githubusercontent.com/elastic/ecs/v9.5.0/generated/ecs/ecs_flat.yml).
A future ECS export needs its own explicit missing-time policy.

## C-03: identity, time, retry and ordering

Generate a fresh random UUIDv4 producer-instance ID for each collector launch,
and a random UUIDv4 event ID outside the native callback before first send.
Use OS randomness; failure stops the interval without inventing a predictable ID.
Retries preserve the exact event ID and canonical payload. Receiver accepts an
exact duplicate as an idempotent success and rejects same-ID/different-content
conflicts. Native PID/CPU/sequence/time are provenance, not globally unique IDs.
No process entity ID is inferred. New producer after restart is a different scope;
there is no durable collector spool or promise to replay lost pending memory.

`timestamps` has `activity_wall_time:null`, reason `not_emitted_by_source`,
`observed_at` as collector read-time UTC and observation `native_decode`.
The callback samples a fixed-size observation clock alongside the copied native
record; formatting/serialization happens later. Backend stores its own separate
UTC receipt time. Neither substitutes for activity time; no monotonic-to-wall
conversion or assumed ordering of clocks. A failed/unrepresentable observation
clock degrades/stops the interval rather than fabricating a value.

Store order is backend-assigned monotonically increasing arrival ordinal, not
claimed activity order or UUID order. UI labels observation/receipt time and
unknown activity time. No per-CPU sequence is promoted to host-wide order.

## C-04: bounded delivery, storage and health

Native callbacks copy into at most 256 fixed-size pending slots without allocation,
blocking, socket writes or database access. Serialize/validate outside callbacks;
keep one fixed canonical pending frame until acknowledgement. On a queue/transport
failure, mark the interval incomplete and stop the affected source gracefully.
No unbounded buffers, silent event drops, root retry or repeated subscription.
Known ACK absence remains separate from observed delivery. Successful IGNORE
send/close still does not prove kernel-side completion. Source health failures
must not block authorized dashboard/history access or functioning other sources.

New store: `/var/lib/hids/process/store.sqlite`, private directory 0700 and files
0600 owned by `hids-ingest`, WAL with private sidecars. No M3/M4 migration or write.
Use a versioned schema/application ID and reject unknown layouts; independent
Python contract validation before any insert. Initial tables:

- `process_events`: arrival ordinal primary key, event UUID unique, source/activation/
  producer/boot scope, native kind, normalized PID/TID, observation/receipt UTC,
  canonical validated envelope and SHA-256 payload digest. Index arrival ordinal,
  event UUID and kind/PID with arrival tie-break.
- `process_intervals`: source/activation/producer scope and latest independent ACK,
  delivery, incomplete/stopped facts with bounded typed diagnostics. Diagnostic
  text cannot contain arbitrary source payload. No raw native datagram table.

Commit the event before success ACK. Exact duplicate returns the prior commit;
conflict never overwrites it. FULL/readonly/lock/rejection paths expose explicit
failure without resetting state, deleting history or continuing as if durable.
Unknown commit outcome is resolved with the same ID/payload if the existing
connection remains usable; disconnection stops this first runtime rather than
reopening the source. Python remains the only SQLite writer.

Prototype engineering caps: at most 10,000 retained process events and 64 MiB
combined process DB/WAL/SHM plus admitted temporary DB outputs, with existing
filesystem reserve/admission patterns adapted before writes. Cap settings are
visible and root-controlled; no automatic expiry or deletion is introduced.
On capacity exhaustion stop this source, preserve history and report capacity.
These conservative first-build safety caps are not measured performance acceptance
thresholds or a completed long-term retention policy. Existing source histories,
backups and unrelated application files are outside these caps and untouched.
A future retention/delete policy requires explicit owner approval.

## Implementation and acceptance sequence after approval

1. Implement deterministic synthetic native→C++ normalizer/outgoing validation→
   Unix JSON Lines→Python validation/commit/ACK. Exercise FORK/EXEC/EXIT, zero parent,
   threads, unsigned boundaries, absent clocks, malformed/unknown/conflicting data.
2. Test commit/crash/retry, bounded queues, slow/disconnected receiver, FULL/readonly/
   lock refusal, unauthorized peers and actual service identities on Linux. No
   new live subscription is needed for these fault-injection tests.
3. Integrate root activation/ownership/stop and honest health into the existing
   D-14a controller. Keep confirmation before source initialization; installation
   and unit restart never subscribe automatically. Test synthetic before actual.
4. Perform one deliberately authorized bounded installed integration trial with
   an owned child; initially retain only that fixture for acceptance. Broader
   user-selected runtime uses the consent scope above, not hidden test sampling.
5. Connect protected Activity/history and source status, then package using the
   accepted Debian/systemd direction. Use a separate clean test installation;
   do not overwrite/recreate Linux 2's existing M3/M4 state to fake a clean host.

This contract alone does not approve wider history HTTP fields/routes, TLS lifecycle,
new log permissions, a severity taxonomy or additional detection rules. Prepare
those concrete changes when the pipeline can exercise them; preserve existing
D-12c/D-14a boundaries. Zero-capability native lifecycle metadata supplies no
executable or UID, so the existing Audit root-shell rule cannot run on it. Display
that limitation rather than inventing a useful security detection from PID alone.

## First-build finish line

Produce an installable Ubuntu development build with explicit source confirmation,
a real collection→validated storage→protected display path, truthful failures,
protected state, supported one-event detection evidence where source fields exist,
and clean-install/restart/stop checks. Document unsupported sources/rules and open
v0.1 requirements. Reassess value and time investment there before extras. A
process viewer or a passing install command alone is not a complete HIDS/v0.1.

## Implemented evidence and operational refinements

The [bounded installed pipeline](../validation/process-pipeline-acceptance.md)
passed with actual owned-child events. PID 1 launches the two fixed-role services
under retained restrictions; the root coordinator holds the activation lease and
only CAP_CHOWN. Both source/backend capability sets are empty. NSS may repeat a
role's own primary GID in the supplementary vector; no other GID is allowed and
no additional group access is granted. Metadata directories are recreated at boot
without any grant or source initialization. Existing choice revisions remain
unchanged; the new saved choice is empty at revision 6. This evidence does not
expand the separately reserved process HTTP/UI/certificate boundary.
