# Repository guidance

## Purpose and current state

Build a functional, local-first Host-Based Intrusion Detection System for an
individual's computer, initially supporting **Ubuntu 26.04 LTS only**, with a local
web dashboard. The product name is undecided.

The repository now contains M1/M2 components and an implemented M3 Audit
execution pipeline. M3 has been built and exercised on Ubuntu 26.04 AArch64 with
root-controlled activation, separate reader/backend identities, current-tail
framing, independent validation, SQLite persistence, recovery/suppression, resource
limits and a separate metadata health checker. See the chronological evidence and
current limits in [M3 verification](tests/integration/M3-README.md). Tests of selected
paths do not establish complete native coverage, continuous monitoring or release
readiness. Proactive storage admission, distinct event metadata and bounded root rejection
diagnostics are implemented; broader workloads, hard filesystem quotas, release
thresholds, reproducible distribution and other acceptance gates remain open.

M1/M2 validation remains separate: consult [M1 validation](docs/validation/m1-pilot-validation.md),
[M2 lifecycle validation](docs/validation/m2-lifecycle-validation.md) and their test
readmes before claiming those milestones complete. The process adapter's own
[Ubuntu validation](docs/validation/collector-ubuntu-validation.md) is distinct from
M3 Audit execution. A usable dashboard, detection rules and completed product
packaging are still later work. Do not describe planned behavior as implemented
or treat a passing test count as proof of all milestone requirements.

## Decision authority and reading order

Follow explicit user instructions. The established constraints below capture the
owner's current decisions and take precedence over conflicting older documents.
Do not silently revise them; explain conflicts and record agreed changes and their
rationale in documentation and, where appropriate, an ADR.

Read [product experience](docs/product-experience.md),
[release scope](docs/release-scope.md), the
[v0.1 readiness plan](docs/implementation/v0.1-implementation-plan.md),
[architecture](docs/architecture.md), the
[ADRs (including the ADR-004 amendment and provisional ADR-006 and accepted release-scope ADR-007)](docs/decisions/), [threat model](docs/threat-model.md),
[evidence policy](docs/confidence.md), and
[schema research process](docs/schema-design-process.md),
[field discovery](docs/research/field-discovery.md), and
[authentication research](docs/research/authentication.md) and
[process connector research](docs/research/process-connector.md) before relevant work.
[proposed event schema](docs/event-schema.md) contains the unfinalized field
contract. The former misleading filename is retained as a compatibility pointer. [todo.md](todo.md) is a backlog, not decision authority
or proof that an item has not already been documented.

## Established architecture

Intended flow: Ubuntu sources → C++ collector → Python backend → SQLite →
FastAPI → local dashboard.

| Location | Responsibility / accepted baseline |
|---|---|
| `collector/` | C++20 OS collection, source-native ingestion/parsing, normalization, collection-side event processing, and transport |
| `engine/` | Python normalized-event receipt/contract validation, enrichment, individual-event detection, alerts and SQLite writes in v0.1; correlation/multi-event evidence deferred to v0.2; no independent OS collection |
| `rules/` | Rule definitions separate from engine implementation; authentication, process, and filesystem scaffolding |
| `api/` | FastAPI routes and API schemas; initially modules within the Python service |
| `frontend/` | React + TypeScript dashboard, Vite tooling, SSE for initial live updates |
| `shared/schemas/` | Planned shared, versioned event contracts and schema fixtures |
| `packaging/` | M2/M3 systemd/configuration artifacts; complete Debian packaging remains planned |
| `tests/` | Native/Python unit and integration suites, sanitized fixtures and explicit Ubuntu acceptance harnesses; detection coverage remains planned |
| `docs/` | Architecture, security requirements, schema work, evidence policy, and ADRs |

- Collector and backend are separate processes, communicating through Unix domain
  sockets using JSON Lines initially. Version and document shared interfaces.
  C++ validates native input and outgoing normalized representations; Python
  independently validates received normalized contracts. Preserve validation on both sides.
- Preserve accepted C++20, Unix sockets/JSON Lines, FastAPI, React/TypeScript/Vite,
  SSE, Debian/systemd and Python-owned SQLite writes. Reconsideration requires
  explicit approval and a documented decision.
- Python owns SQLite writes; the collector must not independently write to it.
  Accepted storage requirements include WAL, appropriate indexes, deduplication,
  configurable retention, bounded growth, and migrations.
- Prioritize a reliable end-to-end real-event pipeline before sophisticated rules
  or frontend features. Detection and multi-event correlation remain distinct.

## Release scope

[ADR-007](docs/decisions/007-initial-release-scope.md) accepts v0.1 as a complete
minimal collection-to-dashboard HIDS: cn_proc lifecycle, best-effort `/proc`
context, supported existing authentication/system logs, health/degradation,
C++ normalization, Unix socket/JSON Lines, Python validation/SQLite and a root-only
search/detail/basic-alert dashboard. Simple deterministic rules evaluate one event;
repeated failures, success-after-failures, detection windows, process/behavioral
sequences and cross-source correlation are v0.2 plans, not v0.1 requirements.

Preserve event identifiers, provenance, original type/native information, available
timestamps and process/parent IDs, and rule identity. A v0.1 alert must link to its
one triggering event and explain its matched condition. Do not build multi-event
supporting-evidence stores, aggregation, graphs or complex relationships in v0.1;
do not hide correlation inside enrichment/normalization. Native multi-record
parsing and transport deduplication are distinct operational responsibilities.
v0.2 remains a planned direction, not a finalized specification or delivery promise.
Do not finalize schemas or add dependencies based solely on these release goals.

The accepted product direction also requires root-authorized first-run source
recommendations/individual selection and confirmation **before** security-event
collection. Preflight is metadata/non-collecting access assessment, not log payload
sampling, `/proc` context gathering or a hidden cn_proc subscription. Discovery,
assessment, draft/confirmed configuration, selected initialization and runtime
health are separate. Source selection controls HIDS only, and failed initialization
must not stop working confirmed subsets or authorized configuration/history access.
Overview is the landing page; alerts sort severity then recency, ordinary events
belong in Activity, and technical detail uses progressive disclosure. Navigation
and severity labels remain proposals; no confidence/suspiciousness scores. Require
idle/typical CPU, memory, disk/burst and slow receiver/database benchmarks, with
actual acceptance thresholds established after measurement, not invented budgets.

## Product and security constraints

- **Detection and explanation only.** Do not automatically block, terminate,
  quarantine, delete, disable, or otherwise remediate. Existing scope also excludes
  threat remediation recommendations as a product feature. Monitoring coverage
  recommendations are within scope: explain missing fields/sources, consequences,
  and information that would improve monitoring, without automatic system changes.
- Use existing Ubuntu logging/auditing. Throughout the initial release, HIDS must not
  modify journald configuration, PAM configuration, auditd configuration, or Linux
  Audit rules. This applies during installation, startup, discovery, and runtime.
  HIDS application files and its own service units are distinct from Ubuntu logging
  configuration. Additional logging configuration requires separate design and
  approval as a stretch goal.
- Research actual Ubuntu source availability and behavior. The owner now prioritizes
  the narrow production process adapter; cn_proc is the provisional primary live
  lifecycle candidate, `/proc` provides best-effort enrichment, and journald remains
  a complementary planned source; Audit is an intended source whose usable coverage depends on
  existing configuration. Do not assume auditd is installed or that execution
  events are recorded. Never compete with auditd for the kernel audit stream.
  `/proc` snapshots are context, not a complete execution history.
- Restrict initial human dashboard and security-data access to root. Maintain
  privilege separation: this does not require a root browser or root backend.
  Python runs as an unprivileged service account with necessary data access;
  collector privileges must be justified per adapter. Do not run everything as root.
- Bind the API to localhost. Localhost is not authentication: enforce backend
  authentication and authorization on sensitive endpoints, with Host/Origin
  validation and appropriate CSRF protection. Expose no arbitrary shell, SQL, or
  filesystem operations. Treat collected event content as untrusted input.
- Protect databases, associated files, raw records, backups, exports, and temporary
  data from ordinary users; authorized service-account access is distinct from
  human access. Do not claim protection from a fully compromised root account.
- Keep data local by default, with no default external telemetry or cloud
  dependency. Minimize sensitive collection and sanitize fixtures.
- Never generate numerical confidence scores, probabilities, or automatic
  qualitative confidence labels. Severity describes potential impact and is
  separate from confidence. Preserve detection indicators and supporting evidence; these are not confidence
  scores. Show rule conditions, missing information,
  benign explanations, and limitations; a match does not prove malicious intent.
  Interpretation belongs to the user or an optional future AI with relevant context.
  AI interpretation must remain distinct from observations and rule findings.

## Schema and research discipline

- Use **ECS 9.5.0** as the initial reference: appropriate Core fields first, then
  relevant Extended fields. Verify meanings and types against the pinned official
  reference; do not invent ECS fields or repurpose their semantics.
- Add custom fields only for demonstrated gaps. **`hids.*` is provisional**;
  neither that namespace nor proposed custom field paths are finalized.
- Develop mappings incrementally from actual Ubuntu records and detection needs.
  Document source semantics, permissions, required configuration, provenance,
  multi-record grouping, and collection limitations. Preserve original information
  where practical and privacy-appropriate; distinguish raw source records from
  normalized events. Do not use textual `event.original` as an arbitrary structured
  record container.
- Distinguish activity time, collection/observation time, and processing/storage
  time. Missing/unreliable activity timestamps are an unresolved schema decision;
  never invent them or silently substitute collection time. No fallback policy is
  finalized. Do not hide other unknowns behind empty strings, zeroes or guessed defaults.
- Track ECS and HIDS schema versions separately. Preserve historical meaning;
  breaking contracts require explicit versioning and compatibility/migration plans.
- Ubuntu sources emit native records, not ECS events. C++ produces normalized
  events; preserve useful native information and provenance where practical without
  forcing immediate ECS mapping or silently discarding unmapped fields.
- Validate normalized events at Python receipt. Future normalization and rule work needs
  representative sanitized fixtures and meaningful positive, negative, incomplete,
  duplicate, and failure cases. Test reliability, bounded resource use, and access
  controls as those features are implemented. Native adapter compilation, offline
  unit-test commands and the complete production link smoke test are documented
  in [collector/README.md](collector/README.md); M3 integration evidence is tracked
  separately in [M3 verification](tests/integration/M3-README.md).

## Field and capability discovery

- Maintain a broad evolving candidate catalog separate from source-native fields,
  the normalized ECS contract, and rule-specific detection requirements. Do not
  assume every source/event supplies every candidate or collect all values.
- The System Capability Manager assesses existing sources/mechanisms and access;
  the Field Discovery and Coverage Analyzer assesses what records actually provide;
  the engine assesses rule requirements; the dashboard explains concrete limitations.
  These are logical responsibilities, not implemented services or fixed process placement.
- Source discovery is initially read-only. Graceful degradation is an initial-release
  requirement. If a collection source is missing, inaccessible, or failing, other
  functioning sources must continue operating. The dashboard and stored data must
  remain accessible under the existing authorization policy. Report the affected
  source's status and limitations of rules that require unavailable information;
  recovery must be detectable. This does not promise historical backfill. Concurrency,
  process isolation, and supervision mechanisms remain undecided.
- Support startup discovery, periodic reassessment, availability changes,
  collection-gap/failure identification, and recovery without claiming historical
  backfill. Read permissions must be checked for actual service identities.
- Use scoped availability states: Observed, Not observed in sample, Not emitted by
  source, Not applicable, Inaccessible, Collection failure, Unknown. Record evidence,
  environment, source/event role, time and assessment freshness; do not equate states.
- Rules declare Required/Important/Optional fields; Sensitive is independent.
  No numerical importance scores, universal rankings, or security-coverage percentage.
  Empty history is not proof of working monitoring; missing data is not proof of no activity.
- Preserve native information where practical before mapping is settled. Discovering
  existence does not authorize retaining values. Protect raw research records;
  sanitize examples, especially arguments, environment variables, and messages.
- Catalog growth alone must not change the core schema. Schedules, sampling,
  assessment storage, retention/redaction, and rule requirement syntax remain open.

## Proposals and unresolved questions

Do not treat examples as final contracts. Exact event fields and requirements,
custom namespace, database tables/indexes, API endpoints, dashboard layout, rule
format (YAML is proposed), example rules/severities, filesystem interfaces,
and network coverage require further design or source validation.

M3 now has tested choices for Audit plugin integration, reader/backend identities,
scoped IPC, current-tail authorization, bounded assembly and interruption recovery.
Consult the M3 specification and executed evidence before reopening those decisions.
Broader source coverage, system-wide isolation/availability guarantees, hard filesystem quotas and broader disk safeguards, release thresholds, general schema compatibility, reproducible
packaging, production asset serving, missing/unreliable activity times for other
sources, and encryption/key management remain open. A tested M3 component does not
settle these questions for every source or for the whole application.
Root-only authentication must be designed before dashboard implementation;
whether sudo-authorized administrators qualify alongside UID 0 is explicitly open.
Do not broaden access by assumption. AI assistance, remote monitoring/evidence,
additional distributions, eBPF, ML, and YARA are future possibilities.

## Documentation status

The original November 5 design reconciliation and later implementation evidence
are retained chronologically. ADR-004's installation-time Audit-rule permission is
superseded history. `docs/event-schema.md` remains a schema draft, and architectural
layout examples still include planned files. `todo.md` contains overlapping and
historical gates; an unchecked broad item does not invalidate a later scoped test,
and a checked scoped item does not close all broader acceptance requirements.

Current M3 execution/health/recovery evidence belongs in
[the M3 verification record](tests/integration/M3-README.md). Preserve its explicit
unsupported cases and remaining gates. When documentation conflicts with observed
repository state or newer owner approvals, reconcile the specific stale statement
without weakening accepted architecture, privacy or evidence requirements.

## Working constraints

Prefer understandable, maintainable implementations and small, justified changes.
Research instead of guessing; preserve historical reasoning and user work. The
owner's later M3 implementation/testing approvals supersede the old November 7
M1-only task restriction; do not repeatedly stop at that stale restriction.

The owner's standing HIDS workflow is: prioritize host safety, project progress,
then avoiding unnecessary interruptions. Make reversible decisions within the
approved design, build missing testable pieces, fix failures, and continue through
routine tool/access problems using safe alternatives. The owner has authorized
reversible work on the Linux 2 test VM, including needed implementation, tests,
application setup and documentation. Preserve VM access secrets outside the repo.
This does not relax the product's prohibition on automatic Audit/journal/PAM
configuration changes. Explicitly authorized lab source tests must preserve and
restore host policy and retain protected evidence.

Ask the owner for specific commits/pushes, fundamental architecture or product/value
decisions (including reversing an approval), breakage needing their attention, or
blockers that cannot be resolved with existing access and authorization. Read-only
Git inspection and routine reversible implementation do not require repeated
permission. Batch routine results into the final report. Existing approvals apply;
this file records them rather than granting unlimited new scope or overriding tool
approval requirements. Do not add correlation, remediation, wider human access or
finalized global ECS mappings under an M3 implementation task.
