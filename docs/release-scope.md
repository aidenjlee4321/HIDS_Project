# HIDS release scope: v0.1 and v0.2

**Status:** Accepted v0.1 scope; v0.2 planned direction, not a delivery commitment  
**Documented:** November 6, 2026  
**Last updated:** November 7, 2026  
**Decision:** [ADR-007](decisions/007-initial-release-scope.md)  
**Initial platform:** Ubuntu 26.04 LTS, one machine

## Purpose and current state

Deliver a usable local HIDS by completing a small collection-to-dashboard pipeline
before building complex analysis. Prior architecture and research provide the
foundation; they do not establish implemented product coverage. The repository now has scoped M1/M2 evidence, an implemented M3 plugin pipeline
with accepted bounded integration closeout, and a tested synthetic M4 rule/alert/
read-only-handoff path. The approved bounded M4 real import also passed; ongoing monitoring, supported security rules, complete product
orchestration, dashboard and distribution remain unfinished. See
[current state](current-state.md) for exact implementation/evidence boundaries.

This document defines release boundaries and acceptance criteria. It does not
implement features, authorize further code changes, promise release dates or
finalize schemas, rules, dependencies or database tables. Architecture phases are
engineering steps, not product version numbers. See [architecture](architecture.md)
for components and [schema research process](schema-design-process.md) for contract
work. Explicit owner requirements and existing accepted technology/security
decisions remain in force.

The accepted [product experience](product-experience.md) adds a v0.1 first-run
confirmation gate and lightweight-operation/benchmark requirements. Its navigation
and severity labels remain proposals; its examples do not finalize contracts or
change root-only access. This scope clarification adds no implementation.

## v0.1 — Minimal functional HIDS

### Goal

A genuinely usable single-machine HIDS that collects real Ubuntu activity,
normalizes and validates it, persists searchable history, evaluates simple
individual-event rules, and presents understandable alerts and source health in
an authorized local web dashboard. A standalone adapter or empty dashboard is
not a completed v0.1.

### Required capabilities

| Area | v0.1 requirement |
|---|---|
| First-run discovery/selection | Read-only metadata and non-collecting access assessment, explained recommendations/preselection, editable individual HIDS sources, explicit confirmation before any security-event collection, then selected initialization and actual runtime status; usable subsets supported |
| Process collection | Live process lifecycle notifications through cn_proc, following the provisional direction and validation limits of [ADR-006](decisions/006-provisional-process-collection.md) |
| Process context | Best-effort `/proc` enrichment with explicit absence/race/access limitations; snapshots are not execution history |
| Existing logs | Supported existing authentication and system logs; journald and available Audit records are complementary sources, with actual source coverage documented |
| Efficiency | Event-driven/incremental work, bounded queues/memory, efficient SQLite writes, controlled disk retention/backpressure; required prototype benchmarks and measured acceptance thresholds, no invented CPU/memory budgets |
| Source health | Availability/access and collection-error reporting; functioning sources continue when another source is unavailable; authorized dashboard/history access remains available; report recovery without promising historical backfill |
| C++ boundary | C++20 source-native collection, ingestion/parsing, validation, normalization and outgoing representation validation |
| Python boundary | Normalized-event receipt and independent contract validation, enrichment/analysis at the established boundary, individual-event detection and Python-owned SQLite writes; no independent OS collection |
| IPC and storage | Separate collector/backend processes, Unix domain sockets and JSON Lines, local SQLite persistence with accepted WAL/indexing/deduplication/retention/bounded-growth/migration requirements |
| Detection | Simple deterministic rules evaluated against one normalized event and its available per-event context; basic event categorization and explicit missing-data behavior |
| Alerts | A rule finding traceable to its single triggering event, the rule identity and the condition that matched, with available provenance, limitations and benign explanations |
| Dashboard | Approachable Overview landing page with central alert feed ordered by severity then recency; ordinary events in Activity, searchable history, one-event alert detail and health indicators; proposed Overview/Alerts/Activity/Sources/System Health/Settings navigation with progressive disclosure; accepted FastAPI/React/TypeScript/Vite/SSE direction |
| Access/security | Root-only human dashboard and security-data access; backend authorization, localhost binding, Host/Origin checks and appropriate CSRF protection; privilege separation and least privilege |
| Locality/configuration | Local storage by default; no automatic remediation, mandatory extra collection configuration, or changes to journald, PAM, auditd configuration or Audit rules during installation, startup, discovery or runtime |

Missing sources are visibility limitations, not proof of absent activity. Do not
require installation of auditd, new Audit rules, changed logging levels or PAM
changes to satisfy this release. Keep per-adapter permissions justified; root-only
human access does not mean a root browser or an all-root application. Authentication
mechanism and sudo-administrator eligibility are now accepted for the bounded
D-12a/b/c implementation: explicit root/sudo sessions, unprivileged backend/browser
and protected selected history. Production origin/certificate lifecycle and broader
API scopes remain open; do not broaden access by assumption.

### First-run boundary

Discovery, availability/field assessment, user configuration, selected collector
initialization and runtime health are distinct operations. No live subscription,
event-reader initialization or security-event payload sampling occurs before the
user confirms. Pre-confirmation field information is documented possibility or
scoped prior authorized evidence; current observed-field sampling follows consent.
Static capability evidence is not demonstrated runtime functionality. Selection
controls HIDS collection, never Ubuntu logging/Audit rules or kernel settings.
A selected collector may fail; report its real state and continue the working
confirmed subset. Recommendation/preselection does not start a collector.

Root-only authorization covers discovery results and source configuration as well
as retained security data; the approachable product does not broaden eligibility.
See [product experience](product-experience.md#first-run-experience) for the flow.

### Detection boundary

| Example | Release boundary |
|---|---|
| Recognize and categorize one failed authentication event | v0.1: evaluate the outcome in that event; no assertion about previous attempts or intent |
| Match one process execution against a simple configured condition | v0.1, only if that event's supported fields/enrichment satisfy the rule |
| Detect repeated authentication failures | v0.2: counting related events is multi-event analysis |
| Detect repeated failures followed by a successful login | v0.2: requires event relationships, ordering and possibly a time window |
| Identify a suspicious creation → execution → privilege-change sequence | v0.2: process/behavioral sequence analysis |
| Associate observations from different sources into one activity finding | v0.2: cross-source correlation |

v0.1 rules must not query prior/other events to establish their match. They do not
count, aggregate, compare event sequences or use detection time windows. Searching
history by a date range, sorting displayed history, periodic health assessment,
transport retries/deduplication, and timestamp preservation are operational/UI
functions, not time-window detection. They do not authorize behavioral analysis.
Reading a source's multiple native records to parse one source-defined event is
also distinct from correlating independent normalized events. Normalization must
not hide a behavioral sequence inside a synthetic event to bypass this boundary.
Best-effort per-event enrichment may add context; it must not secretly query event
history or infer a multi-event match. A supplied parent identifier is native context,
not permission to build a process relationship graph in v0.1.

### Exclusions

No multi-event correlation, time-window/sequence-based rules, behavioral patterns,
alert evidence aggregation, multiple independent supporting events per alert,
evidence relationship manager, correlation graphs or complex event relationships.
No richer behavioral investigation timeline is required beyond searchable history
and one-event detail. These are v0.2 plans below. The existing exclusions for
remediation and threat-remediation recommendations, external telemetry by default,
additional distributions and unapproved logging configuration remain unchanged.
Optional AI, eBPF, ML, YARA, new filesystem collectors and remote monitoring are
not moved into v0.2 automatically; they remain separately deferred possibilities.

### v0.1 completion criteria

All criteria require implementation evidence on the supported Ubuntu platform;
research observations, source code or isolated adapter tests alone do not satisfy
them:

1. Demonstrate real supported process lifecycle activity and existing authentication/
   system-log events reaching C++ normalization → Unix socket/JSON Lines → Python
   independent validation → Python-owned SQLite → authenticated API → dashboard.
   Document actual source availability and field limitations; an empty history is
   not a working-pipeline demonstration or a security verdict.
2. Demonstrate the [first-run confirmation checks](product-experience.md#completion-checks-and-open-decisions): metadata-only discovery, explained/editable recommendations, no event collection before confirmation, selected-only initialization, truthful runtime failures and operation with a subset. Backend/collector authorization must enforce the gate, not merely UI state.
3. Demonstrate simple positive, negative and incomplete individual-event rule cases.
   A single failed authentication event can be categorized; a valid one-event rule
   produces an alert with the matched rule identity, condition and triggering-event
   reference. No acceptance test requires repeated failures or any other sequence.
4. Search persisted history and inspect individual events, alert details and
   collection health. Retained alert references resolve to their triggering events;
   define retention behavior so removed data is disclosed rather than silently
   misrepresented. No multi-event evidence manager is needed for this test.
5. Test native parsing, C++ outgoing validation and Python receipt validation,
   malformed/duplicate/failure cases, bounded resources, persistence/restart and
   configured retention/migrations at the implemented boundaries. Reliability does
   not imply lossless cn_proc delivery or backfill; expose detected gaps and limits.
6. Make a source missing, inaccessible or failing and verify other functioning
   sources, authorized history/dashboard access, source status and relevant
   individual-rule limitations continue. Recovery is detectable; do not claim that
   recovery fills earlier gaps.
7. Verify root-only sensitive-data authorization and restrictive data-file access,
   service privilege separation, localhost/API/browser protections and local-default
   behavior under actual service identities. Verify installation/startup/runtime
   does not modify Ubuntu logging configuration or Audit rules or demand new
   collection configuration. Accepted Debian/systemd packaging direction is retained.
8. Document supported inputs, rule limitations, operational/build/install procedures
   and unresolved coverage honestly. Resolve only the contracts needed for supported
   behavior through the established research/versioning process, not a speculative
   comprehensive event or database schema.
9. Benchmark idle/typical CPU, memory, disk growth, event bursts and slow receiver/
   database conditions. Record prototype/source/workload conditions, bounded-resource
   behavior and health visibility; establish and validate actual acceptance thresholds
   after measurement. No CPU/memory budgets are fixed by this scope document.
10. Demonstrate the approachable Overview landing page and severity-first, recency-
    second alert feed; ordinary events remain Activity records. Use a reviewed
    recency clock and event/rule traceability; proposed severity names/navigation
    are not frozen schemas or confidence/suspiciousness scores. Essential warnings
    stay visible while technical details use authenticated progressive disclosure.

## Preserve foundations without implementing correlation

v0.1 must preserve stable event identification, source provenance, original event
type and useful available native information subject to privacy/retention controls.
Preserve available timestamps with their clock/role semantics, process and parent
identifiers where provided, and the identity of the rule that generated an alert.
Do not use per-CPU sequence numbers or a PID alone as a globally unique event ID.

Activity time, observation time and storage time remain distinct. Missing or
unreliable activity time is not invented or silently replaced by collection time;
cn_proc monotonic nanoseconds are not wall-clock time. The policy and representation
for missing time still need explicit design before claiming a finalized contract.

The required v0.1 linkage is alert → one triggering normalized event → available
source provenance. Parsing provenance may reference the native records that formed
that one event; this is not a multi-event supporting-evidence system. Do not add
aggregate evidence stores, correlation graphs or generic relationship machinery
just to reserve space for v0.2. Existing privacy/access controls apply to retained
original information; preserving provenance does not authorize blanket retention
of arguments, environments or raw logs.

Concepts here are requirements for traceability, not finalized field names, ID
construction, ECS mandatory fields, table definitions or foreign keys. Choose and
validate the supported v0.1 contracts incrementally, keeping ECS 9.5.0 as the pinned
foundation and tracking ECS/HIDS contract versions independently. Preserve historical
meaning and provide compatibility/migration plans when contracts change.

## v0.2 — Correlation and richer investigation

### Planned goal and capabilities

Build on a working v0.1 pipeline to explain relationships and behavioral patterns
across events. This is a direction for future design, not an implementation
commitment, delivery date, finalized rule set or specification.

| Area | Deferred v0.2 direction |
|---|---|
| Correlation | Relationships across multiple events, time-window detection, authentication sequences, cross-source correlation and process lifecycle/behavioral sequences |
| Supporting evidence | Multiple supporting events per alert, evidence aggregation and relationship management, richer investigation timelines and explanations of behavioral patterns |
| Advanced detection | Context-dependent and behavioral patterns and more sophisticated evaluation; exact rule format, semantics and examples require further design |

v0.2 planning retains the same technology, privilege, local-first, existing-logging
and evidence-first constraints unless separately changed through an explicit
decision. It does not promise new sources, changed logging configuration, complete
coverage, automatic remediation, or AI interpretation. It must continue to separate
observations, rule findings and interpretation, without numerical or automatic
qualitative confidence scoring.

### Candidate completion criteria to refine before v0.2 implementation

These are planning checks, not a finalized release commitment:

- A separately reviewed correlation/rule specification defines supported event
  relationships, windows/order semantics, missing-data behavior and limitations.
- Approved representative multi-event cases (including benign, incomplete,
  duplicate and failure cases) pass meaningful tests without treating absent
  records as proof of no activity or deduplicated records as independent evidence.
- A correlated alert links its multiple supporting events and rule conditions;
  users can inspect the relationship and behavioral explanation in a richer
  investigation view while source provenance and v0.1 event traceability remain.
- Aggregation/relationship storage and any contract changes have justified schemas,
  bounded retention/resource behavior and compatibility/migration plans.
- Access controls, source degradation and uncertainty about timing/gaps remain
  visible across sources; no speculative confidence score substitutes for evidence.

Exact v0.2 scope and acceptance tests must be approved before implementation.
Deferral preserves future design space without making these features v0.1 blockers.
