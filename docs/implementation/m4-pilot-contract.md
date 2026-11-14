# M4 one-event fixture pilot contract

Status: owner-approved for the fixture-only pilot after the walkthrough; implemented
and tested within that scope. This is not a finalized production schema.
Authority: ADR-007's accepted one-event detection boundary; D-07/D-08 require review
of persistence/rule semantics. This pilot introduces no correlation, remediation,
new collection, broader access or dependencies. Python owns evaluation and SQLite.

## First deliverable and boundary

One synthetic accepted M3 fixture → independent validation → event persistence →
one bounded declarative rule → one persisted, explainable demo alert.

Use only new private prototype databases and synthetic fixtures at first. Do not
open/migrate existing M3 databases, hook running services or enable a live rule.
Production integration needs its own reviewed migration/cutover step. The fixed demo and its implementation evidence are recorded in
[M4 pilot acceptance](../validation/m4-pilot-validation.md). Real security-rule
coverage and live detection remain unimplemented.

## Event and identity

The pilot envelope carries explicit contract/profile version, source UUID,
activation UUID, generation UUID, native Audit identity, and the current normalized
M3 execution payload. Validate the complete M3 payload independently; reject an
unsupported version/profile, malformed scope or incomplete required M3 fields.
Nullable auid/session remain unknown; never substitute zero or an activity time.

Event identity is a domain-separated SHA-256 of the canonical versioned tuple
(source, activation, generation, native identity). Retain that tuple alongside the
key. PID alone is never an identity. Identical repeated delivery is idempotent;
the same identity with a changed payload is a conflict, not an overwrite.

A future live adapter must supply an actually committed event and verified scope.
Configured source identity from metadata-only status, rejected native groups,
interrupted assemblies and unavailable history cannot manufacture an event.

## Approved fixture rule semantics

Use standard-library JSON initially; YAML and executable rule plugins are not
required for the pilot. A rule has immutable id/revision, exact source profile,
content hash, required-field set, bounded `all_of` equality predicates and a fixed
explanation. Maximum four predicates on this initial allowlist:

| Field | Comparison and missing-data behavior |
|---|---|
| exe_base64 | Exact canonical Base64 bytes, respecting M3's existing size/NUL checks; no path guessing, decoding loss or symlink rewriting. |
| uid | Strict uint32 equality; Boolean values are not integers. |
| auid | Strict uint32 when known; explicit null is unable-to-evaluate; missing M3 payload keys reject at receipt. |
| success | Strict Boolean equality. |

Check all rule-required values before matching. Any unavailable required value
produces unable-to-evaluate, never a false clean/nonmatch. Otherwise all equalities
must hold to match. Invalid rules are rejected before registration. Unknown keys,
operators or fields, SQL, scripts, regex, network access and history/window queries
are unsupported. An evaluator sees only its one validated event; retry bookkeeping
is operational persistence, not behavioral correlation.

The first rule is explicitly a demo: match the synthetic executable
`/opt/hids-fixture/probe`, with wording "Configured executable matched (demo)."
It is opt-in for fixtures and has no default live activation or ATT&CK mapping.
Approved pilot severity is `informational`, identifying a configured condition;
it does not assert maliciousness or finalize a severity taxonomy. Meaningful
security rules/mappings and their benign explanations need subsequent evidence.

Changing a definition without changing its id/revision is rejected. Store the
canonical definition/hash so historical findings retain the exact rule meaning.
No numerical or qualitative confidence score is generated.

## Approved fixture persistence

Use a fresh, marked prototype SQLite file in an owner-private 0700 directory;
database and sidecars 0600, WAL and foreign keys enabled. Refuse production/M3
files and unknown prototype versions; no automatic migration or evidence removal.
These table/column names are pilot proposals, not global ECS/HIDS field decisions.

| Table | Minimum record and invariants |
|---|---|
| m4p_events | event_key primary key; source/activation/generation/native identity/profile; immutable validated payload and hash; processing receipt time. Exact scope also unique. |
| m4p_rules | rule id + revision primary key; immutable canonical definition/hash, demo flag and proposed severity. Same revision/different content rejects. |
| m4p_evaluations | event key + rule id + revision primary key; foreign keys to the one event/rule; pending, matched, no_match, unable or error; fixed reason code and evaluation processing time. |
| m4p_alerts | deterministic alert id; unique event/rule/revision tuple; foreign keys to the triggering event/rule/evaluation; fixed explanation, matched predicate values, demo/severity and creation processing time. No multiple-event evidence graph. |

Event persistence precedes evaluation. Transaction 1 stores the event and pending
work against an immutable rule snapshot. Transaction 2 atomically records the
final evaluation and, only for a match, its single alert. Failure cannot delete or
roll back an already committed event or mark unevaluated work as a nonmatch.

Retry pending work from the already persisted normalized event after a crash;
never reconstruct native input or turn an interrupted M3 group into an event.
Alert identity is a separate domain-separated hash of event key + rule id/revision.
Unique constraints prevent duplicate evaluations/alerts. Any M3 production ACK,
writer ownership, schema migration or scheduling change remains outside this
fixture-pilot approval and requires an integration review.

Receipt/evaluation/alert creation times are processing clocks, distinct from the
source activity identity. Do not invent activity timestamps. No dashboard sort
order or global clock policy is finalized here.

## Finite acceptance checklist

1. One matching fixture produces exactly one event, matched evaluation and linked demo alert.
2. Nonmatch produces a no_match evaluation and no alert.
3. Known optional auid can match; unknown required auid produces unable and no alert.
4. Invalid/incomplete M3 input, unsupported profile and conflicting identity are rejected.
5. Duplicate delivery/evaluation retries preserve one event/evaluation/alert.
6. Different activation/generation scopes never collide merely because native identity/PID repeats.
7. Unsupported fields/operators, executable content and rule-revision drift are rejected.
8. Failure/crash between event commit and evaluation preserves pending work and the event.
9. Evaluation/alert transaction failure leaves no partial alert or false completion; retry succeeds once.
10. Private permissions/unknown-store-version rejection pass; existing M3 files remain untouched.
11. Demonstration output labels synthetic data and demo rules; no threat or ATT&CK coverage claim.

## Approval and remaining boundary

The owner accepted the bounded M3 integration closeout and this fixture-only M4
pilot direction after the walkthrough, then instructed implementation. That approval
covers the rule behavior and minimal fixture persistence semantics above. It does
not approve a final production schema/severity taxonomy, live rule activation,
M3 migrations, a release, commit/push or broader privileges. Those remain governed
by the standing rules and later concrete integration evidence.
