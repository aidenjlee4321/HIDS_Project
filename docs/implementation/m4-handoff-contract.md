# M3 → M4 committed-event handoff: accepted direction and production proposals

Status: the owner accepted this implementation direction after reviewing the
proposal. The adapter and independent worker are now implemented/tested with
synthetic data; [implementation evidence](../validation/m4-handoff-implementation-validation.md)
records exact scope and remaining gates. The later [production storage/trial packet](m4-production-review.md) was accepted
and its [bounded real import](../validation/m4-real-data-trial.md) passed. No
unattended unit or live security rule is enabled. Wider D-08/D-09/D-10 and release
threshold/authentication gates remain beyond those recorded scopes.

## Recommended first integration

Use a separate Python M4 worker under the existing unprivileged `hids-ingest`
identity. It reads explicitly selected M3 activation databases using short SQLite
read-only transactions and writes a separate private M4 database. It does not sit
on M3's ingestion/ACK path or own M3's writer lock. Retain the accepted C++/Python
boundary; no new broker, collector, database server or dependency is proposed.

Root must explicitly select the source and activation(s) to hand off. The first
integration targets a newly authorized M3 activation; it does not automatically
import the 355 retained lab databases or alter collection consent. M4 never starts,
reactivates or expands M3 collection. Selected older activations, if later desired,
need an explicit import request and compatibility checks. Import time remains
separate from source activity/observation time.

Real security rules remain disabled until separately accepted with their source
requirements, evidence and limitations. The existing informational rule remains a
lab-only demo; transporting real events does not make that demo a supported threat
detection. Import counts, pending work and no enabled rules must remain visible,
so an empty alert list cannot imply that events were checked or found safe.

## Verified repository facts

These are observations of the current code, not new design assumptions:

- `m3_runtime.py` control schema version 4 records one source UUID and explicit
  activation/generation bindings; the activation database is named by activation.
- Each ledger's `m3_cursor` stores its activation, generation, boundary, scanned
  position and resolved frontier. Stream positions are not event times.
- `Progress.accept` writes `m3_execution` (identity, unique first_offset, payload),
  metadata and progress advancement in one transaction. Accepted records remain
  immutable under the current implementation. The ledger has no event deletion,
  compaction or source-retention implementation.
- Acceptance can occur out of native order: B may commit while earlier A remains
  open. The frontier stays behind unresolved A. Accepted rows are identified by
  `m3_execution`, not a nonexistent `state='accepted'` disposition value.
- Metadata records have format 1, nullable arch/profile/first observation, and
  distinct backend receipt/persistence-start times. Older rows may lack metadata;
  copying today's profile onto them would invent evidence.
- M3 uses WAL. A consumer must honor the real WAL view. Do not use `immutable`,
  read only the main database file, copy a live database with ordinary file copy,
  or create missing source files as an access workaround.

Relevant implementation: [Runtime](../../engine/ingestion/m3_runtime.py),
[acceptance/frontier](../../engine/ingestion/m3_progress.py),
[metadata](../../engine/ingestion/m3_event.py),
[installed privileges](../../packaging/systemd/hids-m3.service).

## Source authorization, identity and validation

The proposed root-owned configuration enumerates allowed source UUIDs and activation
UUIDs under the fixed canonical M3 state directory. Derive filenames from checked
UUIDs; requests must not supply arbitrary SQL, filesystem paths or socket commands.
Verify configuration ownership/mode and the existing service-account file/sidecar
policy, reject links/special/multiply-linked files, and check directory/owner identity.
Do not persist or expose M3 lease tokens; M4 does not need collection authority.

In bounded read-only transactions, verify the supported control schema/version,
source singleton and selected activation/generation. Verify that ledger cursor
scope matches. The control registration precedes accepted input, and generation
bindings do not change during a registered interval. Recheck binding on reopen;
revocation ends collection but does not erase already accepted selected events.
Unexpected scope, file replacement, schema or frontier regression blocks that
binding and reports a specific failure. Never reset a cursor and silently reinterpret
another database. System/root compromise remains outside the trust claim.

For each committed execution, require its EOE/ledger acceptance witnesses and
matching metadata record, independently validate the closed M3 payload, and retain
its exact source/activation/generation/native identity and first_offset. Known
arch/profile values must match their supported definitions. Preserve an explicitly
unknown observation triple as unknown; profile-dependent evaluation is unable when
profile is unknown. A missing metadata row, contradictory witness or unsupported
schema/profile is a blocked source-data condition requiring inspection, not a
silently skipped or rewritten event.

The handoff envelope is a distinct versioned format, proposed
`m4.audit-exec-handoff/1`, with source bindings, native identity, first_offset,
normalized execution, original format-1 metadata and M4 import processing time.
Do not relabel real data `synthetic=true` to pass the fixture-only API. Reuse the
pure predicate evaluator/closed execution validation where appropriate, with an
explicitly separate store/envelope adapter. Never remove the fixture API's safety gate.
Event IDs retain the approved scoped identity principle; define the live domain
separately from fixture IDs. No global ECS/custom namespace or universal activity
clock is finalized here.

## Bounded progress that does not lose late commits

Do not use the maximum observed native timestamp, first_offset or a hidden rowid
as the durable import watermark. Earlier A can commit after B, and neither arrival
order nor a single maximum first_offset describes all accepted records.

Proposed scan state is per source/activation/generation, stored only in M4:

- `settled`: every accepted event with first_offset strictly below this boundary
  has been durably imported. Initialize to the verified M3 boundary.
- `sweep_target`: the resolved M3 frontier captured at the START of this sweep.
- `scan_after`: last first_offset durably visited in this sweep, initially
  settled minus one. This is pagination, not proof that earlier A was imported.

Read bounded pages in a consistent source transaction: capture the frontier when
starting a sweep, then fetch accepted rows with `first_offset >= settled` and
`first_offset > scan_after`, ordered by first_offset. Never infer a global temporal
order from this operational ordering. Commit imported immutable event snapshots,
associated evaluation work and the updated scan state together in M4 before
moving to another page. A failed M4 transaction advances nothing.

At an empty page, move settled only to the captured sweep_target, then start a new
sweep. Do not substitute the newest frontier observed at sweep completion: A may
have appeared behind scan_after during that sweep. Revisit unsettled higher-offset
rows in later sweeps; scoped identity/content checks make that replay idempotent.
Bounded page continuation ensures later B events are not starved by repeatedly
reading the first page while A remains unresolved.

Example: A starts at 0, B at 10. B commits; frontier stays 0. M4 imports B with
sweep_target 0. A then commits behind the page cursor. The first sweep can finish
only at settled 0. The next sweep finds A, rechecks B idempotently, and can then
settle through the newly resolved frontier 20. M3's ACK behavior never waits for
this process.

This relies on M3's current append-only acceptance and resolved-frontier semantics.
Any later source deletion, rewriting, compaction or changed position semantics
requires revisiting the contract. It is not a generic SQLite change-data-capture
protocol. Root-manipulated or replaced evidence cannot be made trustworthy by a
consumer cursor alone.

## Destination schema and transactions proposed for review

Use a NEW private store with its own application id/version, 0700 directory,
0600 database/sidecars, exclusive writer lock, WAL/FULL synchronous and foreign
keys. No M3 schema migration or in-place conversion of fixture stores is proposed.
The following is the minimal logical schema; exact DDL must be included in the
implementation review before durable real-data operation under D-07.

| Record | Required contents/invariant |
|---|---|
| Source binding/progress | Source/activation/generation primary key, approved source format/boundary, settled/sweep_target/scan_after and scoped failure/status. No lease token. |
| Event | Scoped event key; source binding FK; unique binding/native identity and binding/first_offset; immutable canonical payload and original metadata with content hash; import processing time. |
| Rule snapshot | Immutable rule id/revision and canonical definition/hash; activation/configuration is explicit. The existing fixture demo is not automatically enabled here. |
| Evaluation | One event + rule/revision key; pending/matched/no_match/unable/error and fixed reason/time. Missing source profile remains unable, never no_match. |
| Alert | Unique event/rule/revision; foreign keys to its one event/rule/evaluation; exact explanation, matched values, approved rule severity and creation processing time. |

Import transaction: event + selected immutable rule snapshots/pending evaluations
+ scan state. Evaluation transaction: result + optional alert, as in the approved
pilot. Immutable duplicate retries succeed; any changed payload, metadata, scope
or same-revision rule content conflicts rather than replacing history. An event
committed to M4 remains accessible if evaluation later fails. A source reread is
not required to complete its already persisted pending work.

The worker supports no automatic expiry/deletion or backups in this first step.
Require explicit bounded page/WAL/state/free-space admission settings before any
unattended real-data run; unset or exceeded limits block M4 imports honestly.
Use measured lab values for implementation testing, not invented final release
budgets. D-09/D-15 resource/retention acceptance remains a gate for unattended use.

## Scheduling, isolation and honest failure

One independently supervised worker, round-robin across explicitly selected
bindings, performs short source-read pages and bounded destination evaluations.
No M4 exception, rule outcome or pending alert is passed into M3's acceptance or
ACK transaction. Do not add M4 calls to the native reader, Service dispatch or
`Progress.accept`. On source busy/unavailable or destination pressure/failure,
release read transactions, report pending/blocked work, and retry with bounded
backoff. A failed binding must not silently disable working selected bindings.

Proposal for reversible LAB tuning: pages of at most 64 events, short connection
busy timeout and SQLite statement progress budget, yielding between pages and a
bounded idle/backoff interval. Measure contention and WAL growth before choosing
production defaults. A statement progress budget does not guarantee a deadline
against a stuck filesystem syscall. Long-lived source snapshots are forbidden.
Shared CPU/storage can still affect M3; a separate process is not full host-resource
isolation and application admission is not a hard filesystem quota.

The proposed unit keeps `User/Group=hids-ingest`, no supplementary IPC group or
capabilities, no network listeners, read-only M3 filesystem access and only the new
M4 state directory writable. Hide M3 sockets from this worker. Existing readable
source WAL/SHM must work with read-only access; if they do not, stop that binding
and report unavailable rather than granting source writes or inventing history.
Prove this under the actual installed sandbox before claiming isolation. No Mac
system change, new account, dependency or OS logging change is part of the proposal.

Status must distinguish imported work, pending evaluation, blocked/unknown source
history, rule-disabled/ineligible work and actual completed evaluations. Expose
only bounded aggregate operational status through a root-authorized mechanism;
keep event/alert access protected. This does not pre-approve dashboard/API auth.
An M4 backlog does not overwrite M3's collection-health account.

## Deployment, rollback and finite next acceptance

First implement against private synthetic M3 ledgers and a new private destination.
Then verify real service-identity/read-only-sandbox behavior with synthetic input.
Only after exact DDL, budgets and explicit live scope are reviewed should a root
opt-in live lab run select a newly authorized M3 activation. Preserve original
source files and all existing databases. No automatic historical backfill or
production security-rule activation is included.

Rollback is stop/disable only the new M4 worker and retain its protected state;
M3 binary/config/schema/ACKs are unchanged. Unknown destination versions refuse;
no downgrade, schema replacement or evidence deletion is automatic. Future
migrations require reviewed rollback/export handling rather than rewriting old
rule/event meaning.

Finite acceptance before claiming this handoff supported:

1. Actual selected source/control/ledger binding and schema checks; forged,
   replaced, unselected and incompatible inputs refuse without source writes.
2. B-before-A, late-A behind a page, multiple pages, newly arriving work, repeated
   sweeps and restart all retain every eligible committed event exactly once.
3. Uncommitted/rolled-back, rejected, interrupted and missing/contradictory metadata
   never manufacture accepted inputs. Null observation metadata stays unknown.
4. Preserve all clock roles, native/profile/identity information and same-identity
   conflict detection; live envelopes cannot enter the fixture API by relabeling.
5. Destination failure/crash at import/progress and evaluation/alert boundaries
   advances neither partial progress nor a false completion; retries are idempotent.
6. Actual least-privilege service sandbox cannot write M3 or use its control/data
   endpoints; source WAL visibility works, missing WAL/SHM fails honestly.
7. Busy/slow reader, lock contention, M4 full/readonly/WAL limits, worker restart
   and per-binding failure preserve M3 ACK correctness and measure resource impact.
8. Root selection/configuration, disabled rules, backlog/status privacy and rollback
   preserve consent/history; no hidden collection or source-policy changes.
9. Exact DDL/transactions, operational budgets and a live lab scope are reviewable
   before real-data activation. No security coverage or release-complete claim.

## Evidence and accepted implementation decision

`tests/unit/test_m4_handoff_design.py` is a synthetic-only design harness using the
actual M3 Progress writer and a separate read-only SQLite connection. It reproduces
the unsafe max-offset counterexample and exercises the candidate sweep ordering,
pagination, destination-failure retry, uncommitted visibility, recovery/metadata and
read-only write denial. It is not the production adapter; its cursor is in-memory,
so it does not establish durable destination atomicity, source authorization,
installed isolation, contention budgets or live acceptance. Those remain checklist
items for the next implementation.

[Executed design evidence](../validation/m4-handoff-design-validation.md): all
30 M4 tests (23 existing pilot + 7 design), all 87 M3 Python regressions and the
demo passed on Ubuntu. The local design/pilot phase passed, but local M3 setup
was blocked by its existing low-space guard; that report remains failed. No
production storage/ACK code was changed to obtain the passing VM result.

The owner accepted the independent read-only worker + separate protected
destination, explicit activation selection, frontier-safe sweep and transaction/
rollback boundaries as the implementation direction, with synthetic testing.
[That implementation now passes its selected acceptance](../validation/m4-handoff-implementation-validation.md).
The owner subsequently accepted the exact first-trial storage/budgets/live scope
in [the production packet](m4-production-review.md), and its bounded real import
passed. The lab entry remains guarded; a separate fixed-path real entry implements
that scope. Unattended operation and real security rules retain separate gates.
