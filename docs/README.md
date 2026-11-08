# HIDS Documentation

HIDS is the working name for a lightweight, local-first Linux Endpoint Security
Platform, initially targeting Ubuntu 26.04 LTS. The
[architecture](architecture.md#1-project-overview) records its intended monitoring,
assessment, detection engineering, investigation and eventual controlled-hardening
capabilities, CIS/ATT&CK/SSDF alignment and lightweight design principles.

The owner reports M1 synthetic-pipeline Ubuntu acceptance passed. The
[roadmap](implementation/v0.1-implementation-plan.md#l-implementation-milestones)
now prioritizes real journald integration as M2; later work requires separate
implementation authorization. Historical validation records are unchanged.

## Documents

| File | Purpose |
|---|---|
| [development-workflow.md](development-workflow.md) | Standard-library local tests, immutable source snapshots, verified UTM transfer and offline Ubuntu reports; no deployment/live collection |
| [product-experience.md](product-experience.md) | Accepted v0.1 product/first-run confirmation and measured lightweight operation; navigation/severity labels proposed |
| [validation/collector-ubuntu-validation.md](validation/collector-ubuntu-validation.md) | Owner-reported Ubuntu ARM64/GCC 15.2.0 strict compilation, offline suites and production link success; live/account/reliability unvalidated |
| [implementation/v0.1-implementation-plan.md](implementation/v0.1-implementation-plan.md) | Readiness inventory, proposed end-to-end design, permission matrix, decision register and gated milestones |
| [implementation/m1-pilot-contract.md](implementation/m1-pilot-contract.md) | Owner-approved P-01–08 for synthetic M1 only; authoritative envelope/IPC/storage/security contract |
| [implementation/m2-journald-spec.md](implementation/m2-journald-spec.md) | Owner-approved fixture implementation scope: prerequisites, service/IPC policy, separate SSH-journal contract and atomic progress/recovery; deployment/live testing not authorized |
| [validation/m2-lifecycle-validation.md](validation/m2-lifecycle-validation.md) | Wired M2 reader/ingestion/root-control lifecycle, offline tests and outstanding Ubuntu/deployment gates |
| [validation/m2-component-validation.md](validation/m2-component-validation.md) | Historical M2 component checkpoint; subsequent lifecycle wiring and remaining Ubuntu gates are in the lifecycle validation record |
| [validation/m1-pilot-validation.md](validation/m1-pilot-validation.md) | Historical M1 implementation/local test evidence; predates owner-reported Ubuntu acceptance and remains unchanged |
| [../tests/integration/README.md](../tests/integration/README.md) | Exact M1 build/regression/integration commands and private harness boundaries |
| [release-scope.md](release-scope.md) | Accepted minimal v0.1 requirements and completion criteria; correlation/multi-event evidence deferred to planned v0.2 |
| [architecture.md](architecture.md) | Overall system architecture, components, technology stack, roadmap, and implementation objective |
| [event-schema.md](event-schema.md) | Proposed canonical event structure and normalization conventions; ECS reference is established, detailed contract is not |
| [schema-design-process.md](schema-design-process.md) | Research workflow, event-family research matrix, and schema evolution |
| [research/field-discovery.md](research/field-discovery.md) | Broad candidate catalog, capability/field-discovery responsibilities, availability states, rule requirements and descriptive coverage |
| [research/authentication.md](research/authentication.md) | Owner-reported sudo and SSH journald experiments; observations and candidate ECS mappings, not raw fixtures or implemented coverage |
| [research/process-connector.md](research/process-connector.md) | Exact owner-reported Ubuntu lifecycle results, ACK limits, sequence investigation and provisional architecture implications |
| [../scripts/research/README.md](../scripts/research/README.md) | Temporary Ubuntu inventory/process research utilities; separate from HIDS; one owner-reported cn_proc Ubuntu run, broader validation pending |
| [confidence.md](confidence.md) | Evidence-first requirements; preserve detection indicators without confidence scores or automatic labels |
| [../AGENTS.md](../AGENTS.md) | Repository guidance and authoritative constraints |
| [../todo.md](../todo.md) | Documentation progress and pending research/design/implementation |
| [threat-model.md](threat-model.md) | Security objectives, privilege model, trust boundaries, privacy requirements, and known limitations |
| [decisions/](decisions/) | Architectural Decision Records (ADRs) explaining significant design choices |

## Architectural Decision Records

| ADR | Decision |
|---|---|
| [ADR-001](decisions/001-language-and-component-responsibilities.md) | Language and component responsibilities |
| [ADR-002](decisions/002-sqlite-storage.md) | Local persistent storage with SQLite |
| [ADR-003](decisions/003-local-ipc.md) | Local inter-process communication |
| [ADR-004](decisions/004-privilege-separation.md) | Privilege separation; November 5 amendment supersedes installation-time audit-rule permission |
| [ADR-005](decisions/005-platform-and-interface.md) | Initial platform and user interface |
| [ADR-006](decisions/006-provisional-process-collection.md) | Provisional cn_proc lifecycle candidate; native adapter milestone, with unresolved reliability and integration |
| [ADR-007](decisions/007-initial-release-scope.md) | Accepted minimal v0.1 release; correlation and multi-event evidence deferred to v0.2 planning |

## Documentation conventions

- `product-experience.md` defines user-facing first-run/consent, severity-first alert feed, proposed navigation and benchmark expectations; it does not implement them.
- `release-scope.md` defines v0.1 requirements/acceptance and v0.2 planning; roadmap phases are not release versions.
- `architecture.md` describes what the system is and how its major components fit together.
- `event-schema.md` proposes the shared event representation; exact fields and `hids.*` remain provisional.
- `threat-model.md` describes security assumptions, requirements, and limitations.
- ADRs record why significant decisions were made and what remains unresolved.

## Current status and decision boundaries

As of November 6, 2026, documentation, directory scaffolding and temporary
[research utilities](../scripts/research/README.md) exist. The utilities are not
HIDS application functionality.
A narrow [production C++ process adapter](../collector/README.md) and offline tests
now exist. The owner reports successful Ubuntu 26.04.1 ARM64/GCC 15.2.0 strict
compilation, both offline suites and complete production linking; see the
[validation record](validation/collector-ubuntu-validation.md). Live production
connector operation, intended service-account access and runtime reliability
remain unvalidated. The synthetic M1 pipeline now implements normalization,
transport, independent Python validation and SQLite persistence/retrieval; the
owner reports Ubuntu acceptance passed. This is not live-source integration or a
production backend/dashboard. Sudo, SSH and cn_proc observations are documented; complete raw
fixtures, validated mappings, and comprehensive event-family research remain pending.

- **Accepted release boundary:** [v0.1](release-scope.md#v01--minimal-functional-hids)
  completes the minimal pipeline, one-event deterministic rules and protected
  basic dashboard; v0.2 planning contains correlation/windows/sequences, multiple
  supporting events, aggregation and richer behavioral investigation. Preserve
  v0.1 event/rule/source traceability without building future evidence machinery.
- **Established initial-release requirements:** existing Ubuntu logging/auditing;
  no changes to journald configuration, PAM configuration, auditd configuration
  or Audit rules during installation, startup, discovery or runtime;
  detection and explanation only; evidence and indicators without numerical or
  automatic qualitative confidence; root-only human security-data access;
  least privilege; local storage and data minimization; ECS 9.5.0 with Core and
  relevant Extended fields preferred over custom fields. Broad field discovery
  keeps source-native information, normalized ECS, and rule requirements separate;
  capability discovery assesses sources/access, field analysis assesses actual
  information, and descriptive reports explain limitations without security scores.
- **Accepted architecture baseline:** C++20 collector, Python backend, SQLite,
  Unix sockets/JSON Lines, FastAPI, React/TypeScript/Vite, SSE, and planned
  Debian/systemd deployment. Accepted choices are not implemented features.
- **Proposals:** detailed schemas, tables, endpoints, rule format/defaults,
  dashboard layouts, additional monitoring sources, and source-specific coverage.
- **Stretch goals/future possibilities:** automatic logging/auditing configuration,
  optional AI interpretation, additional distributions and remote monitoring.
  Automatic remediation is excluded from the initial release.

Authentication, sudo-authorized administrator eligibility, custom namespace,
permissions, IPC reliability details, retention, and encryption remain undecided.
Missing/unreliable activity-time handling and the mechanisms for source isolation,
concurrency and supervision also remain open. Do not infer approval from an example
or roadmap item. Graceful degradation is established even though its mechanisms
are undecided: functioning sources and authorized dashboard/stored-data access
continue, affected source status and rule limitations are reported, and recovery
is detectable.

C++ owns native collection, ingestion, parsing, normalization and collection-side
processing. Python receives/validates normalized events and owns detection,
security analysis and SQLite writes; future correlation remains Python-owned
v0.2 work. Both IPC endpoints validate
appropriately; Python ingestion does not mean native OS collection. Native records
need not map immediately into ECS. Monitoring coverage recommendations are within
scope; threat remediation recommendations are outside initial scope. Additional
logging configuration requires separate design and approval; HIDS files and its
own services are distinct from Ubuntu logging configuration. Accepted technology
choices above require explicit approval before reconsideration.

## Product direction

The November 7 product direction adds explicit metadata-only discovery, explained
source recommendations and user confirmation before collection to v0.1. Selection,
initialization and actual runtime health are separate, and usable subsets are
supported without changing Ubuntu logging or kernel configuration. Overview is the
landing page; ordinary events belong in Activity, alerts sort by severity then
recency, and technical details use progressive disclosure. Resource benchmarks
are required, with thresholds set after prototype measurement. Navigation/severity
wording and confirmation/restart/recency details remain open; the event/IPC/DB
contracts and accepted technologies are unchanged.

## Implementation readiness

The [v0.1 plan](implementation/v0.1-implementation-plan.md) separates accepted
architecture from proposals for envelopes, IPC, storage and authentication. Its
permission matrix/decision register identify owner review gates; its milestones
prioritize a protected fixture-to-storage/read path before broad adapter/UI work.
The plan is not an implementation authorization or a finalized ECS/IPC contract.

## Reconciliation history

On November 5, 2026, current requirements replaced stale confidence and automatic
logging-configuration language. ADR-004 retains the superseded clause and rationale.
The schema draft moved from `event-schema-design-process.md` to `event-schema.md`;
[the old path](event-schema-design-process.md) remains a compatibility pointer.
Research reasoning and candidate mappings were preserved; no source research or
implementation was added by this documentation change. The subsequent alignment
correction clarified C++/Python ownership, validation on both IPC endpoints,
graceful degradation, lifecycle-wide logging restrictions, and recommendation
scope. Missing activity-time policy remains unresolved; ADR clarifications retain
the original wording and rationale as history.

The accepted release-scope revision in ADR-007 distinguishes a usable v0.1 from
future correlation/evidence work. Earlier architectural descriptions remain as
labeled v0.2 plans; existing ADR-001–006 and technology decisions are unchanged.
This reconciliation adds documentation only and does not advance implementation.
