# HIDS Documentation

First-build user trial: [instructions](USER_TRIAL.md) and
[final packaged/installed acceptance](validation/first-build-ready.md).

Current update: the first informational rule and v2 migration are approved and
implemented; bounded acceptance and post-cleanup independent preservation checks
passed. No missing HIDS state was identified. Read [the incident and observed results](validation/m4-first-rule-acceptance.md)
for the current state and correction of the earlier VM identity concern.

HIDS is the working name for a lightweight, local-first Linux Endpoint Security
Platform, initially targeting Ubuntu 26.04 LTS. The
[architecture](architecture.md#1-project-overview) records its intended monitoring,
assessment, detection engineering, investigation and eventual controlled-hardening
capabilities, CIS/ATT&CK/SSDF alignment and lightweight design principles.

The owner reports M1 synthetic-pipeline Ubuntu acceptance passed; M2 has separate
component/lifecycle/runtime validation records. M3 has reached its bounded integration closeout; current M4 work is a tested
synthetic pilot and read-only handoff, followed by an approved, passing bounded real-data import trial.
Start with [current state](current-state.md). The M3 [verification record](../tests/integration/M3-README.md) documents
implemented behavior, installed Ubuntu tests, and open acceptance gates. The
[roadmap](implementation/v0.1-implementation-plan.md#l-implementation-milestones)
remains the milestone plan; a working M3 component is not a completed release.
Historical validation records are retained.

## Documents

| File | Purpose |
|---|---|
| [validation/documentation-review.md](validation/documentation-review.md) | Repository-wide consistency/link review, corrected stale summaries and preserved historical evidence |
| [implementation/m4-production-review.md](implementation/m4-production-review.md) | Approved storage/copy policy and bounded real-data scope; trial evidence linked |
| [current-state.md](current-state.md) | Compact current checkpoint, standing approvals, VM prerequisites and next work; start here when resuming |
| [implementation/m3-closeout.md](implementation/m3-closeout.md) | Finite M3 integration evidence, preserved release gates and accepted fixture M4 entry |
| [implementation/m4-pilot-contract.md](implementation/m4-pilot-contract.md) | Approved fixture-only one-event/rule/alert semantics; production contract remains open |
| [implementation/m4-handoff-contract.md](implementation/m4-handoff-contract.md) | Accepted handoff direction; implemented synthetic adapter/worker, preserved production approval gates |
| [implementation/m4-first-rule-review.md](implementation/m4-first-rule-review.md) | Proposed opt-in informational root-shell condition, minimal history-preserving schema upgrade and explicit activation semantics |
| [validation/m4-first-rule-proposal.md](validation/m4-first-rule-proposal.md) | Existing real-data aggregates, 15 test-only semantic/migration cases, crash/backup evidence and unchanged live store |
| [validation/m4-recovery-contention.md](validation/m4-recovery-contention.md) | V2 process-crash boundaries, SQLite busy/full retry, WAL visibility and independent preservation |
| [validation/m4-ipc-contention.md](validation/m4-ipc-contention.md) | Installed Service/peer IPC ACKs beside sandboxed M4 contention, measured observations and VM identity guard |
| [validation/m4-continuous-polling.md](validation/m4-continuous-polling.md) | Actual bounded scheduler idle/burst observations, held-reader checkpoint/reclamation and restart |
| [validation/m4-filesystem-failures.md](validation/m4-filesystem-failures.md) | Real private-image critical-space/FULL rollback, pending-finding retry, readonly startup and fenced cleanup |
| [validation/m4-budget-admission.md](validation/m4-budget-admission.md) | Runtime backup-accounting fix, actual WAL/state refusal/recovery and 96 M4 + 87 M3 regressions |
| [validation/m4-binding-isolation.md](validation/m4-binding-isolation.md) | Actual sandbox failure isolation, per-binding backoff, paginated healthy progress and recovery |
| [implementation/m4-acceptance-review.md](implementation/m4-acceptance-review.md) | Bounded backend evidence matrix and preserved release/access gates |
| [implementation/dashboard-access-eligibility-review.md](implementation/dashboard-access-eligibility-review.md) | Accepted D-12a explicit root/sudo dashboard eligibility; D-12c separately scopes retained-history access |
| [implementation/dashboard-session-mechanism-review.md](implementation/dashboard-session-mechanism-review.md) | Accepted D-12b one-use bootstrap/tab session; synthetic-only implementation and threat boundary |
| [validation/no-ca-browser-comparison.md](validation/no-ca-browser-comparison.md) | Sandboxed Chromium direct-leaf trust and actual synthetic HTTPS authorization; no CA or real data |
| [validation/dashboard-security-fixes.md](validation/dashboard-security-fixes.md) | Implemented UI/size fixes, real browser race and exact TLS blocker evidence |
| [implementation/dashboard-ca-trust-amendment.md](implementation/dashboard-ca-trust-amendment.md) | Proposed replacement for unsupported Firefox leaf-peer trust; new profile only |
| [validation/first-run-acceptance.md](validation/first-run-acceptance.md) | Actual setup/draft/root-terminal implementation, crash/VFS/peer/M3-control tests, real empty preferences and preserved-state cleanup |
| [validation/first-run-design-validation.md](validation/first-run-design-validation.md) | Thirty synthetic D-14a model tests and current VM metadata; no production setup implementation |
| [implementation/first-run-control-review.md](implementation/first-run-control-review.md) | Accepted D-14a remembered choices/fresh root activation, browser drafts/root CLI controls and bounded implementation contract |
| [implementation/m4-history-view-review.md](implementation/m4-history-view-review.md) | Accepted D-12c bounded direct-leaf HTTPS, frozen selected records/pages/budgets and trial contract |
| [validation/m4-history-view-acceptance.md](validation/m4-history-view-acceptance.md) | Protected selected-history implementation, synthetic/real browser acceptance and independent preservation |
| [validation/dashboard-session-pilot.md](validation/dashboard-session-pilot.md) | Actual root/backend/browser pilot, expiry, failures/fixes and preserved-state evidence |
| [../api/README.md](../api/README.md) | Separate synthetic/history APIs, pinned private VM builds and explicit bounded acceptance workflows |
| [validation/m4-real-data-trial.md](validation/m4-real-data-trial.md) | 53-test M4 / 87-test M3 pass, fixed-path sandbox, 16 actual executions imported, preservation/restoration and next detection gate |
| [validation/m4-handoff-implementation-validation.md](validation/m4-handoff-implementation-validation.md) | 19 adapter cases, 49-test M4 / 87-test M3 pass, actual backend sandbox, late-commit recovery and remaining live gates |
| [validation/m4-handoff-design-validation.md](validation/m4-handoff-design-validation.md) | Seven synthetic ordering cases, Ubuntu 30-test M4 / 87-test M3 pass and honest local low-space failure |
| [validation/m4-pilot-validation.md](validation/m4-pilot-validation.md) | Implemented synthetic event/rule/alert pilot, 23 tests, actual crash recovery, Ubuntu evidence and next boundary |
| [validation/m3-quota-validation.md](validation/m3-quota-validation.md) | Real private-image UID quota denial, SQLite rollback/recovery, Service IPC failure latch, privileged-helper fences and limits |
| [validation/m3-readonly-status-validation.md](validation/m3-readonly-status-validation.md) | Root metadata status under read-only state, WAL availability, collection denial and explicit restart |
| [validation/m3-filesystem-validation.md](validation/m3-filesystem-validation.md) | Private bounded ext4: real reserve pressure, SQLITE_FULL rollback, read-only rejection, recovery and limits |
| [validation/m3-native-workload-validation.md](validation/m3-native-workload-validation.md) | Real execution forms, quoted PROCTITLE and shared-stream native framing corrections, retained failures and scoped acceptance |
| [validation/m3-rotation-validation.md](validation/m3-rotation-validation.md) | Real plugin-stream rotation, original source preservation, full regression and finite-retention limits |
| [validation/m3-performance-validation.md](validation/m3-performance-validation.md) | Controlled safeguard cost, measured accounting optimization and longer-workload status |
| [validation/m3-workflow-validation.md](validation/m3-workflow-validation.md) | Executed local/VM workflow acceptance, safe failures, cache measurements and limits |
| [m3-workflow.md](m3-workflow.md) | M3 test tiers, verified SSH transfer, matched VM build/deploy, private reports and cleanup |
| [development-workflow.md](development-workflow.md) | Standard-library local tests, immutable source snapshots, verified UTM transfer and offline Ubuntu reports; no deployment/live collection |
| [product-experience.md](product-experience.md) | Accepted v0.1 product/first-run confirmation and measured lightweight operation; navigation/severity labels proposed |
| [validation/collector-ubuntu-validation.md](validation/collector-ubuntu-validation.md) | Owner-reported Ubuntu ARM64/GCC 15.2.0 strict compilation, offline suites and production link success; live/account/reliability unvalidated |
| [implementation/v0.1-implementation-plan.md](implementation/v0.1-implementation-plan.md) | Readiness inventory, proposed end-to-end design, permission matrix, decision register and gated milestones |
| [implementation/m1-pilot-contract.md](implementation/m1-pilot-contract.md) | Owner-approved P-01–08 for synthetic M1 only; authoritative envelope/IPC/storage/security contract |
| [implementation/m2-journald-spec.md](implementation/m2-journald-spec.md) | Original M2 fixture contract and source policy; later authorized lifecycle/live evidence is recorded separately in the M2 validation documents |
| [implementation/m3-linux-audit-spec.md](implementation/m3-linux-audit-spec.md) | Canonical M3 decisions, state-machine requirements and current source/health implementation boundaries; links to controlled Ubuntu acceptance and remaining evidence gates |
| [validation/m2-runtime-acceptance/ubuntu-runtime-acceptance.md](validation/m2-runtime-acceptance/ubuntu-runtime-acceptance.md) | Owner-reported November 8 Ubuntu M2 runtime exercise, native archival gate and verified cleanup; backend-level negative control authorization remains unverified |
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

M3's supported plugin → C++ → protected IPC → Python/SQLite integration has
scoped Ubuntu acceptance and an owner-accepted [bounded closeout](implementation/m3-closeout.md).
Later storage safeguards, actual quota, metadata/rejection diagnostics and root
read-only status supersede limitations in the earlier focused-review record.
The [M4 fixture pilot](validation/m4-pilot-validation.md) and
[synthetic handoff/actual backend sandbox](validation/m4-handoff-implementation-validation.md)
are implemented and tested; the latest full component scope of 96 M4 tests, 87 M3 Python regressions and demo passed
on Ubuntu. A bounded fixed-path entry and [16-event real import trial](validation/m4-real-data-trial.md)
now pass; no unattended monitoring, supported threat rules, API/dashboard or
finished distribution is enabled. See [current state](current-state.md) for exact
checkpoints, standing approvals and remaining gates. Test counts describe executed
scopes, not complete native coverage, continuous monitoring or release readiness.

### Historical November 6 baseline

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

D-12a eligibility now permits explicit root/sudo authorization per session; D-12b
selects the tested synthetic-only mechanism. Production origin trust/real-data
API access, custom namespace,
permissions, IPC reliability details, retention, and encryption remain undecided.
Missing/unreliable activity-time handling and the mechanisms for source isolation,
concurrency and supervision also remain open. Do not infer approval from an example
or roadmap item. Graceful degradation is established even though its mechanisms
are undecided: functioning sources and authorized dashboard/stored-data access
continue, affected source status and rule limitations are reported, and recovery
is detectable.

For M3, the [master decision register](implementation/m3-linux-audit-spec.md#11-owner-decision-register)
now separates **Owner-approved**, **Provisional**, **Evidence-dependent** and
**Future goal**. The broad open questions above do not reopen the approved plugin source,
protocol-3/separate-database, conservative-recovery direction, Base64
executable-identity encoding, or no-deletion policies.
The [state-machine addendum](implementation/m3-linux-audit-spec.md#12-owner-approved-evidence-and-state-machine-addendum)
now distinguishes source-position re-reading from prohibited interrupted-event
reconstruction; exact grammar, permissions, tuning and schema/protocol mechanics
still require evidence. Later explicit owner tasks authorized implementation and VM testing.
The [current acceptance record](../tests/integration/M3-README.md#installed-health-checker-acceptance)
describes the installed source pipeline and isolated health checker without claiming
that every M3 or release gate is complete.

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

Current process source gate: [approved bounded trial](implementation/process-adapter-trial-review.md),
[offline preparation](validation/process-adapter-trial-preparation.md),
[actual intended-account evidence](validation/process-adapter-live-trial.md).

Next proposed integration boundary: [first-build process pipeline](implementation/process-live-pipeline-review.md)
(identity/live consent, event/ID/time contract and bounded private persistence).

Current process pipeline implementation and actual installed evidence:
[process pipeline acceptance](validation/process-pipeline-acceptance.md).
