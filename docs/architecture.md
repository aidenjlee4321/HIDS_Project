# HIDS — Linux Endpoint Security Platform
## Architecture

**Document version:** 0.4.0
**Status:** Initial design baseline  
**Last updated:** November 9, 2026 (M3 decision reconciliation)\
**Target platform:** Ubuntu 26.04 LTS  
**Project name:** HIDS (working name; permanent name undecided)

## Status and interpretation

Documentation, empty application scaffolding and temporary
[research utilities](../scripts/research/README.md) exist; the utilities are separate
from the HIDS application. A narrow production C++ process-source adapter and
offline tests now exist. Owner-reported Ubuntu ARM64/GCC 15.2.0 strict compilation,
unit suites and production linking passed; [validation record](validation/collector-ubuntu-validation.md).
Live production operation, service-account access and runtime reliability remain
unvalidated.
The synthetic M1 normalization/Unix socket/JSON Lines/Python validation/SQLite
persistence and retrieval pilot is complete, with Ubuntu acceptance passed as
reported by the owner. This does not establish live-source readiness. Historical
M1 validation evidence is preserved unchanged; detection, API and dashboard remain
unimplemented. Accepted technology choices are
an architecture baseline, not working functionality. Detailed fields, endpoints,
tables, rules, and layouts below are proposals unless explicitly identified as
requirements. Milestones after M1 remain planned work, not implementation authority.

Initial-release requirements: consume existing Ubuntu logging and auditing without
modifying journald configuration, PAM configuration, auditd configuration, or Linux
Audit rules during installation, startup, discovery, or runtime; detect and
explain only; preserve indicators and supporting evidence without confidence
scores or automatic confidence labels; restrict human security-data access to root;
maintain least privilege; store data locally and minimize sensitive collection.
Additional logging/auditing configuration is a stretch goal requiring separate design and approval. Changes to HIDS application files and its own service units are distinct from changes to Ubuntu logging configuration.

Release boundaries are defined in [release scope](release-scope.md) and accepted
[ADR-007](decisions/007-initial-release-scope.md): v0.1 is the complete minimal
pipeline, deterministic individual-event rules and a protected basic dashboard;
correlation and multi-event supporting evidence are deferred to v0.2 planning.
Future capabilities below are architectural direction, not implemented coverage
or a commitment to deliver v0.2 as specified.

## 1. Project overview

### 1.1 Purpose

HIDS is the working name for a lightweight, local-first Linux Endpoint Security
Platform, initially targeting Ubuntu 26.04 LTS. Its intended capabilities span
host-based intrusion detection and monitoring, security configuration assessment,
detection engineering and event correlation, understandable security findings and
investigation guidance, and eventually controlled hardening and remediation.

The application will monitor operating system activity, identify potentially suspicious behavior, and present security information in an understandable dashboard.

This project focuses on making host-level security monitoring accessible to ordinary computer users.

The intended [product experience](product-experience.md) lets an authorized user
install, choose available HIDS sources and operate without Linux logging expertise.
This usability goal preserves root-only access and least privilege. First-run
source confirmation and lightweight measured operation are v0.1 requirements.

The primary objectives are:

- Collect and normalize operating system events.
- Monitor process execution, authentication activity, and potentially suspicious system changes.
- Identify suspicious activity through configurable detection rules.
- In v0.2 planning, correlate related events to identify behavioral patterns.
- Explain security alerts in understandable language.
- Provide searchable event history and an interactive dashboard.
- Store collected information locally by default.

The long-term objective is to produce a properly packaged Linux application that users can install, operate, upgrade, and uninstall without needing to manually configure its development environment.

### 1.2 Project philosophy

The project prioritizes:

1. **Usability:** Security information should be understandable to users without specialized cybersecurity knowledge.
2. **Reliability:** Monitoring should operate continuously and report failures rather than silently losing events.
3. **Privacy:** Collected information should remain local by default.
4. **Modularity:** Components should communicate through documented interfaces and be independently maintainable.
5. **Efficiency:** The application should have a small resource footprint suitable for ordinary personal computers.
6. **Transparency:** Alerts should explain why they were generated and provide supporting evidence.

Use native Linux interfaces where practical and SQLite rather than heavyweight
database infrastructure. Keep idle resource use minimal through event-driven,
modular monitoring, bounded memory/queues/storage and few justified dependencies.
Expensive assessments run periodically or on demand; disabled optional features
must consume no ongoing execution resources. Local operation requires no cloud
dependency. Measure actual workloads before setting final resource budgets or
claiming performance guarantees.

### 1.3 Scope

The initial product is strictly a monitoring and detection application.

The HIDS will identify potentially suspicious activity, generate
security alerts, and explain the evidence behind each detection.

It will not automatically remediate threats or provide prescriptive
instructions for stopping or removing them.

Remediation functionality and threat remediation recommendations are outside the initial scope. Monitoring coverage recommendations are within scope: explain missing fields, unavailable sources and limitations, and identify information that would improve monitoring. Recommendations do not authorize automatic configuration changes or remediation.

This initial boundary does not exclude long-term hardening. Future work proceeds
in three separately designed and authorized stages:

1. **Security assessment:** assess selected CIS recommendations, identify
   misconfigurations and explain security implications; make no system changes.
2. **Guided remediation:** preview changes and consequences, obtain explicit
   authorization, back up original configuration, verify application and support
   rollback.
3. **Controlled automatic hardening:** user-enabled predefined profiles with
   narrowly scoped privileged operations, prerequisite/compatibility checks,
   an audit trail, verification and rollback; require explicit authorization for
   high-impact operations.

None of these future stages authorizes implementation or OS changes now. The
initial-release existing-logging constraint and privilege separation remain intact.

### 1.4 Framework alignment

The project is **framework-aligned**, not certified or fully compliant:

- **CIS Benchmarks:** primary configuration-assessment reference; initially
  selected recommendations from the Ubuntu Linux 26.04 LTS Benchmark. Record the
  benchmark version, recommendation identifiers, verification methods, evidence
  and limitations for each implemented check. The
  [official Ubuntu benchmark catalog](https://www.cisecurity.org/benchmark/ubuntu_linux)
  lists version 1.0.0; this is not a claim that any check is implemented.
- **MITRE ATT&CK:** map implemented rules to relevant
  [Linux techniques](https://attack.mitre.org/matrices/enterprise/linux/), recording
  required sources, detection logic, evidence and limitations. A mapping alone is
  not coverage; claim only behavior actually implemented and tested.
- **NIST SSDF (SP 800-218):** use the
  [secure development guidance](https://csrc.nist.gov/pubs/sp/800/218/final) for
  dependency verification, threat modeling, security testing, vulnerability
  handling and secure release practices. Alignment does not assert full adoption.

## 2. Target environment

| Property | Initial specification |
|---|---|
| Operating system | Ubuntu 26.04 LTS |
| Compatibility | Ubuntu only initially |
| Architecture | Modular, multi-process |
| Interface | Local web-based dashboard |
| Installation | Debian package (.deb) |
| Service management | systemd |
| Storage | Local SQLite database |
| Network exposure | Localhost only |
| Data transmission | None by default |

The architecture should avoid unnecessary Ubuntu-specific dependencies outside the collection and packaging layers, to make future distribution support easier.

## 3. Technology stack

| Component | Technology | Responsibility |
|---|---|---|
| Event collector | C++20 | Operating system integration and event collection |
| System log integration | systemd journal API | Collect structured system logs |
| Process monitoring | cn_proc (provisional primary lifecycle candidate) | Live FORK/EXEC/EXIT; one controlled ordinary-user feasibility observation, no complete-delivery guarantee |
| Filesystem monitoring (future proposal) | inotify / fanotify | Candidate additional monitoring; outside the initial existing-log baseline |
| Process information | /proc | Proposed best-effort context/enrichment; short-lived processes can disappear before reads |
| Inter-process communication | Unix domain sockets | Communication between collector and backend |
| Serialization | JSON Lines | Event transmission |
| Analysis engine | Python | Detection, enrichment, and correlation |
| API | FastAPI | Expose application functionality |
| Database | SQLite | Persistent local storage |
| Frontend | React + TypeScript | User interface |
| Frontend tooling | Vite | Frontend development and build |
| Deployment | Debian packaging | Application installation |
| Service management | systemd | Background execution and startup |

C++20, Unix sockets/JSON Lines, FastAPI, React/TypeScript/Vite, SSE, Debian packaging/systemd, and Python-owned SQLite writes remain accepted decisions. Any reconsideration requires explicit approval and a documented decision; implementation difficulties do not silently supersede them.

## 4. System architecture

### 4.1 High-level architecture

The application consists of five primary subsystems:

1. Collection
2. Analysis
3. Storage
4. API
5. Frontend

The intended data flow is:

**Ubuntu operating system → C++ collector → Python analysis engine → SQLite → FastAPI → React dashboard**

The collector and Python backend operate as separate processes.

C++ owns source collection, source-native ingestion/parsing, normalization, and collection-side event processing. Python receives normalized events from C++, validates their contracts, and owns detection, correlation, security analysis and SQLite writes. Python does not independently collect native OS records. Correlation remains
Python-owned future work for v0.2; v0.1 implements individual-event detection only.

The Python service initially hosts normalized-event receipt/validation, analysis, database, and API functionality. These will be separate internal modules rather than separate network services.

#### Capability discovery and field coverage

Maintain a broad, evolving [candidate field catalog](research/field-discovery.md)
independent of the normalized event schema. Discover what existing sources
actually provide; do not require every event to contain every candidate. Preserve
source-native information and original-record relationships where practical and
privacy-appropriate, leaving ambiguous ECS mappings unresolved.

Three layers remain distinct: source-native records/fields, justified ECS 9.5.0
normalization, and rule-specific detection requirements. New catalog entries do
not automatically require schema changes or value retention.

| Logical responsibility | Established boundary |
|---|---|
| System Capability Manager | Discover source/mechanism presence, configuration state, accessibility to actual service identities, and changes in availability |
| Field Discovery and Coverage Analyzer | Assess information actually present in records; track scoped availability, source types, mapping uncertainty, and field coverage |
| Detection engine | Use each rule's Required/Important/Optional evidence requirements to determine whether evaluation is possible and explain limitations |
| Dashboard/API | Communicate source health, missing evidence, affected detections, collection gaps, and recovery to the authorized user |

Support initial read-only startup discovery, periodic metadata/access reassessment,
source changes, collection failures/gaps and recovery. First-run operations are
separate, as defined in [product experience](product-experience.md#first-run-experience):

| Operation | Boundary |
|---|---|
| Source discovery | Identify recognized mechanisms/configuration using metadata; do not start subscriptions or event readers |
| Availability/field assessment | Check scoped access/capabilities under actual identities; pre-confirmation fields are documented possibilities/prior authorized evidence, not newly sampled event values |
| User configuration | Explain recommendations and preselect usable candidates, allow source-by-source draft choices and explicit authorized confirmation; choices affect HIDS only |
| Collector initialization | Initialize only confirmed selected sources; a requested source may fail to initialize |
| Runtime health | Report actual initialization, ACK/delivery, access, incomplete intervals and freshness separately from selection/static support; assess actual fields only after consent |

Before confirmation, do not inspect security-event payloads, subscribe to cn_proc or
initialize event readers for a hidden health/field probe. All consent/start checks
must be enforced in backend/orchestration, not only frontend controls. Unselected
or newly recognized sources cannot auto-enable. Previously confirmed settings,
new drafts and boot-resume/retry policy require explicit design, not assumed consent.
Working confirmed subsets and authorized configuration/history remain usable if
another selected source fails. Restored access does not prove backfill, static
availability does not prove live delivery, and empty history proves neither health
nor absence of activity.

Classify availability as Observed, Not observed in sample, Not emitted by source,
Not applicable, Inaccessible, Collection failure, or Unknown, with scoped evidence.
Rule importance is contextual; Sensitive is independent. No numerical importance
scores, universal field rankings, confidence labels, or overall security-coverage
percentage. Distinguish field existence discovery from retaining sensitive values.

These responsibilities and principles are established requirements; process/module
placement, interfaces, storage formats, schedules, sampling, and runtime status
names remain proposed. The Python backend may coordinate assessments using C++
adapter observations; this is an implementation option, not a new process mandate.
Discovery is read-only with respect to system sources and configuration. It cannot change logging configuration, install packages, or grant privileges.
Existing root-only human access, least privilege, and local privacy rules apply.
No capability manager, field analyzer, or descriptive coverage report exists yet.
See [field discovery](research/field-discovery.md) for methodology and examples;
its record-sampling workflow applies only after confirmed collection or separately
authorized research, not as automatic pre-confirmation discovery.

### 4.2 Collection layer (C++)

The collector is responsible for interacting with Linux and capturing system events.

It must support independently operating source adapters.

Graceful degradation is an initial-release requirement. If a collection source
is missing, inaccessible, or failing, other functioning sources must continue
operating. The dashboard and stored data must remain accessible under the existing
authorization policy. Report the affected source's status and limitations of rules
that require unavailable information; recovery must be detectable. This does not
promise historical backfill. Concurrency, process isolation, and supervision
mechanisms remain undecided.

#### Journal adapter

Uses the native systemd journal API (`libsystemd`) to retrieve structured journal entries.

Responsibilities:

- Collect system logs.
- Collect authentication-related logs.
- Preserve original timestamps and metadata.
- Maintain journal cursors.
- Handle service restarts and log rotation.

#### Process lifecycle adapter (provisional)

[ADR-006](decisions/006-provisional-process-collection.md) records the owner's
provisional direction: cn_proc for live lifecycle, `/proc` for best-effort context,
Audit for complementary security/authentication evidence, and journald for existing
system logs. The [single controlled experiment](research/process-connector.md)
received FORK/EXEC/EXIT as an ordinary user; this is not a reliability benchmark or
comprehensive monitoring. ACK confirmation and observed delivery remain distinct.

The first production milestone implements a bounded C++ adapter/native parser with
explicit unsubscription, error/status reporting and offline tests. It supplies
internal native records to a trusted caller, not a finalized ECS/IPC event or a
public event-printing executable. No Python collection, automatic escalation,
logging changes, `/proc` enrichment or database writes are introduced. Source
failure is local to the adapter; whole-service supervision remains open.

The owner now prioritizes this process adapter before the earlier journald-first
implementation sequence. Journal collection remains planned and the reliable
end-to-end pipeline remains the integration priority. Source-native monotonic time
is preserved without wall-clock substitution; sequence gaps are not a loss count.

#### Audit adapter

The proposed adapter consumes existing Linux Audit records where available. Do not assume auditd is installed, enabled, or recording a particular activity. Missing sources or fields must be reported as visibility limitations, not interpreted as absence of activity.

Candidate activities, subject to existing records and source validation:

- Process execution.
- User and privilege information.
- Relevant security-sensitive operations.

The existing audit daemon (`auditd`) should manage the kernel audit interface.

The collector must not attempt to compete with `auditd` for ownership of the audit event stream. Initial integration must use an already available read path, such as an existing audit log, without changing auditd or Audit rules. A dispatcher requiring configuration changes is a future option, not an initial installation step.

The [canonical M3 specification](implementation/m3-linux-audit-spec.md) records the
accepted semantic profile separately from the proposed file-source/pipeline design:
mandatory uid/euid/suid/fsuid/auid/session context, explicit unset handling, no GID
output, complete EXECVE information, optional validated-and-discarded PATH/CWD/
PROCTITLE, and unknown-field and duplicate-singleton rejection. Missing
EXECVE on a failed SYSCALL remains an unresolved case, not an incomplete sequence
with an automatically assigned outcome. Preserve useful exe/comm identity separately
from excluded arguments and environment. Exact M3 envelope/encoding remains open.

Structural reconstruction owns native identity, record order and byte progress.
Semantic parsing uses fresh libauparse BUFFER state, excludes EOE and truncates
only temporary timestamps to three digits. Parsing is non-root with no capabilities
merely for the library; verify configuration/log accesses under the actual identity.
No separate parsing daemon or elaborate filesystem isolation is required unless
testing demonstrates a need and the design is separately approved. Source access,
production bounds, isolation, rotation and durable recovery remain unresolved.
These decisions do not authorize implementation or change M1/M2 or ADR-006.

Future independently configurable retention may cover executable path, process
name, arguments, working directory, filesystem paths and process title. This is
not an M3 requirement or permission to retain excluded values. Field selection,
defaults, scope, interface/access controls, disabled behavior and whether transient
validation continues are deferred; see the canonical M3 specification rather than
assuming toggles or a finalized retention policy.

#### Filesystem adapter

Eventually monitors selected sensitive files and directories.

Potential targets:

- Authentication configuration.
- System configuration.
- Startup and persistence locations.
- Selected executable directories.

This component is not required for the first working prototype.

#### Process information adapter

Uses `/proc` to retrieve additional process information.

Potential information:

- PID and parent PID.
- Executable path.
- Process owner.
- Command-line arguments.
- Process state.

Process snapshots should be treated as contextual information rather than a guaranteed record of every process execution.

#### Normalization layer

Ubuntu sources produce native records, not ECS events. C++ ingests and parses these records and produces normalized events. Preserve native information and provenance where practical, including useful information with unresolved ECS mappings; do not require every native field to map immediately or silently discard unmapped information. Raw-record retention remains subject to privacy controls.

C++ validates native inputs and outgoing normalized representations; Python independently validates received normalized contracts. Neither IPC endpoint may rely solely on validation at the other endpoint. Exact checks and failure behavior remain open.

The detection engine should not need to understand the original source format. See [Event Schema](event-schema.md).

#### Transport layer

Sends normalized events to the Python backend through a local Unix domain socket.

JSON Lines will be used initially. The detailed event representation is defined in [Event Schema](event-schema.md); the IPC framing and acknowledgment behavior remain open design questions.

Reliability requirements:

- Handle temporary backend unavailability.
- Avoid unbounded memory queues.
- Implement appropriate buffering or local spooling.
- Avoid silently losing events.
- Report collection and transmission failures.
- Support duplicate detection.

### 4.3 Analysis engine (Python)

The Python component receives normalized events and performs analysis.

The long-term event-processing design has five logical modules below, with
correlation deferred to v0.2. Capability and field-coverage responsibilities are described separately above; exact module placement remains open.

| Module | Responsibility |
|---|---|
| Normalized-event receipt (backend ingestion) | Receive normalized C++ events and independently validate their contracts; no native OS collection |
| Enrichment | Add contextual information to events |
| Detection | v0.1: deterministic rules on individual events and their available per-event context |
| Correlation | v0.2 planned: patterns across multiple events, windows and sequences; not a v0.1 module requirement |
| Alerts | v0.1: generate/display traceable single-event findings; v0.2: multi-event aggregation and relationship management |

#### Detection engine

The detection engine should support configurable rules rather than relying on hardcoded conditions.

Rules should be stored independently from the engine implementation.

Potential rule configuration fields:

- Rule identifier.
- Rule name.
- Description.
- Event type.
- Matching conditions.
- Time window (v0.2 correlation only; not a v0.1 rule option).
- Severity.
- Detection indicators from the triggering event; multi-event evidence is v0.2.
- Enabled/disabled state.

YAML is the proposed configuration format. Each rule must declare Required, Important, and Optional evidence by applicable event/role, with independent sensitivity annotations, source-semantic constraints, and explicit missing-data behavior. A missing Required field must not become a negative match or a claim of safety. See [rule field requirements](research/field-discovery.md#9-detection-rule-field-requirements).

#### Correlation engine

**v0.2 planned direction; explicitly excluded from v0.1.** No implementation
commitment, final correlation specification or v0.1 completion dependency is implied.

The correlation engine connects multiple events into potentially suspicious patterns.

Examples:

- Multiple authentication failures followed by a successful login.
- Unexpected process execution followed by privilege escalation.
- Creation of an executable followed by its execution.
- Sensitive configuration changes following suspicious process activity.

Detection and correlation are separate operations.

Detection evaluates individual events in v0.1. Correlation evaluates relationships
between events in v0.2. Recognizing one failed authentication event is v0.1;
repeated failures or failures followed by success require v0.2 analysis. One
process execution matching a simple condition is v0.1; a creation/execution/
privilege-change sequence is v0.2. Rules must not query other events/history in
v0.1; enrichment cannot disguise such a sequence as a single-event match.

#### Alert generation

A v0.1 alert must identify its individual triggering event and generating rule,
explain the matched condition, and retain available provenance and limitations.
The following are proposed presentation concepts, not final field/table contracts:

- Unique alert identifier and rule identity.
- Title, severity and description of the observed event/condition.
- One triggering-event reference with source provenance and available native context.
- Explanation of the condition that matched, missing information and benign explanations.
- Available times with distinct activity/observation/storage meanings; no invented time.
- Alert status and investigation context/suggestions supported by that individual event; no threat-remediation recommendations.

In v0.2 planning, alerts may gain multiple supporting events, evidence aggregation,
relationship management, and richer behavioral explanations/timelines. None of
those systems is a v0.1 prerequisite. A rule match does not prove malicious intent.

Severity and confidence must remain separate concepts.

Severity describes potential impact; confidence concerns interpretation of evidence. HIDS assigns neither numerical confidence scores nor automatic qualitative confidence labels. Preserve detection indicators, matched conditions, and source evidence; present missing information, benign explanations, and limitations. Users interpret findings, potentially with optional future AI assistance. See [evidence policy](confidence.md).

### 4.4 Data storage

SQLite will be the application's primary persistent storage system.

The Python backend will own database writes. The C++ collector will communicate with Python rather than independently modifying the database.

Proposed storage concepts, not finalized database tables. v0.1 requires an alert
to resolve to its one triggering event and preserve provenance; exact storage and
retention behavior still need design. A multi-event join system is not required.

| Table | Purpose |
|---|---|
| `events` | Normalized system events |
| `alerts` | v0.1 individual-event findings, with traceability to one triggering event and rule |
| `alert_events` | Historical proposal retained as a v0.2 candidate for multi-event supporting evidence; deferred, not a v0.1 requirement or approved table |
| `rules` | Detection rule definitions and settings |
| `collector_state` | Collection checkpoints and source state |
| `settings` | Application configuration |

Database requirements:

- Enable Write-Ahead Logging (WAL).
- Index frequently queried fields.
- Implement event deduplication.
- Support configurable data retention.
- Limit database growth.
- Preserve relevant source metadata.
- Use database migrations when the schema changes.

The database should remain entirely local by default.

### 4.5 API design

FastAPI will expose application functionality to the frontend.

Proposed initial endpoints:

| Endpoint | Function |
|---|---|
| `GET /api/events` | Search and retrieve events |
| `GET /api/events/{id}` | Retrieve event details |
| `GET /api/alerts` | Retrieve alerts |
| `GET /api/alerts/{id}` | Retrieve alert details |
| `GET /api/rules` | List detection rules |
| `PATCH /api/rules/{id}` | Enable or disable rules |
| `GET /api/system/status` | Retrieve monitoring health |
| `GET /api/stream` | Receive live updates |

Server-Sent Events (SSE) will initially provide live updates to the dashboard.

The API should:

- Bind to localhost only.
- Validate incoming Host and Origin headers.
- Enforce root-only human access to dashboard and security data through backend authentication and authorization, with appropriate CSRF protections. Authentication and whether sudo-authorized administrators qualify remain undecided. Localhost binding alone is insufficient.
- Keep the backend unprivileged and grant collector permissions only as required per source; root-only human access does not require root services or a root browser.
- Avoid exposing privileged system operations.
- Validate user-supplied queries and configuration changes.

### 4.6 Frontend design

The frontend will use React and TypeScript.

It should prioritize usability and understandable security information over complex visualizations.

Intended [product experience](product-experience.md): Overview is the default
landing page of an approachable security console. Proposed navigation consolidates
the earlier Event Explorer/Process Activity/Authentication views into Activity
filters/details; rule controls belong under Settings or alert detail. Future
investigation capabilities are retained as v0.2 plans, not additional v0.1 menus.

| Proposed navigation | v0.1 purpose |
|---|---|
| Overview | Default landing page; central alert feed ordered by severity then recency, concise collection summary and essential missing-data warnings |
| Alerts | Basic list/detail; matched rule/condition and direct link to one triggering event; multi-event evidence/timelines remain v0.2 |
| Activity | Searchable ordinary events; individual detail and supported process/authentication/source/time filters; native parent IDs are context, not a process graph |
| Sources | First-run discovery, explained recommendations, draft choices/confirmation and selected-versus-actual runtime status |
| System Health | Source access/errors/gaps, backpressure, receiver/database status and assessment freshness |
| Settings | HIDS-owned preferences, approved retention/privacy and simple rule configuration; no arbitrary OS administration |

Proposed display severity bands are Critical / Emergency, High, Moderate, Low and
Informational. Final top-band wording, rule assignments/internal mapping, recency
clock and stable tie-break remain open; do not silently remap historical Medium
examples or invent missing activity time. No numerical confidence/suspiciousness
score is introduced. Ordinary collected events do not automatically become alerts.
Operational notices in health/source views are distinct from security rule findings.

Show clear explanations first and expose technical fields/errno/native diagnostics
on demand, with the same backend authorization on every view/endpoint/SSE stream.
Progressive disclosure must not conceal essential failures. Root-only human access
is retained; neither source selection nor a usable browser experience implies an
all-root backend or root browser. Technical layout/routes remain proposals.

## 5. Repository structure

The following is a proposed target layout, not an inventory of implemented files. Entry points, build files, machine-readable schemas, and the root README shown here do not yet exist. Most application directories remain scaffolding; actual native adapter/test files
are listed in [collector scope](../collector/README.md). See the
[documentation index](README.md) for current documents:

```text
hids/
├── collector/
│   ├── include/
│   │   ├── adapters/
│   │   ├── events/
│   │   └── transport/
│   ├── src/
│   │   ├── adapters/
│   │   ├── normalization/
│   │   ├── transport/
│   │   └── main.cpp
│   └── CMakeLists.txt
├── engine/
│   ├── ingestion/
│   ├── enrichment/
│   ├── detection/
│   ├── correlation/
│   ├── alerts/
│   ├── database/
│   └── main.py
├── rules/
│   ├── authentication/
│   ├── processes/
│   └── filesystem/
├── api/
│   ├── routes/
│   ├── schemas/
│   └── main.py
├── frontend/
│   └── src/
├── shared/
│   └── schemas/
│       └── event-v1.json
├── packaging/
│   ├── systemd/
│   ├── debian/
│   └── configuration/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── detection/
├── docs/
│   ├── architecture.md
│   ├── event-schema.md
│   ├── threat-model.md
│   └── decisions/
└── README.md
```

The repository should contain documentation for architectural decisions and shared interfaces.

## 6. Development roadmap

The owner-approved sequence below replaces the earlier phase numbering. Each
milestone must deliver an independently testable increment; detailed gates remain
in the [implementation plan](implementation/v0.1-implementation-plan.md#l-implementation-milestones).
Only M1 is complete. This roadmap authorizes no implementation beyond existing
explicit approvals and does not amend the M1 contract or interfaces.

| Milestone | Increment / exit evidence |
|---|---|
| M1 — Synthetic pipeline | Complete; owner reports Ubuntu acceptance passed for fixture → C++ → Unix socket/JSON Lines → Python validation → SQLite → retrieval. No live-source claim |
| M2 — Journald integration | Supported real journal records traverse the existing pipeline; test access, cursors, rotation, duplicates and unavailable-source health |
| M3 — Audit, process and authentication | Existing Audit integration plus provisional cn_proc and best-effort `/proc`; verify source permissions, overlapping records, missing context and gaps |
| M4 — Initial detection / ATT&CK | Deterministic individual-event rules, triggering-event/rule traceability and tested Linux technique mappings; no correlation |
| M5 — CIS assessment | Selected Ubuntu 26.04 LTS recommendations with documented read-only verification and limitations; no remediation |
| M6 — Dashboard / investigation | Protected FastAPI/React interface, source discovery/confirmation, event history, alerts and actual collection health; root-only human access |
| M7 — Correlation / explanations | v0.2 planning: time windows, sequences, cross-source relationships, supporting evidence and richer explanations |
| M8 — Remediation / hardening | Future guided remediation, then controlled automatic hardening under the staged safeguards in section 1.3; separate approval required |
| Later — Packaging / deployment | Debian/systemd distribution, approved service identities, production hardening and operational acceptance |

These numbers sequence engineering work, not release versions. ADR-007 remains:
v0.1 completes the minimal protected collection-to-dashboard pipeline with
individual-event detection; correlation/multi-event evidence stay v0.2. M5 is
approved roadmap direction, not an added v0.1 release gate. Packaging/deployment
still require release acceptance under approved identities before production use;
their later scheduling is not permission to ship insecurely. Bounded resources,
source-local degradation, retention/migrations and measured performance remain
cross-cutting gates rather than being deferred to one final milestone.

## 7. Testing and quality requirements

Testing must be incorporated throughout development.

### Unit testing

- Event normalization.
- Schema validation.
- Rule evaluation.
- Correlation logic (v0.2 only; not a v0.1 unit-test dependency).
- Database operations.

### Integration testing

- C++ to Python communication.
- Event persistence.
- Collector restarts.
- API retrieval.
- Dashboard communication.

### Detection testing

- Synthetic event sequences.
- Controlled suspicious scenarios.
- False-positive testing.
- Regression testing.

### Reliability testing

- Backend unavailable.
- Collector restart.
- System restart.
- Journal rotation.
- Database growth.
- Interrupted event transmission.
- Missing, inaccessible and failing sources while other sources and authorized dashboard/stored-data access remain available.
- Affected rule limitations and detectable source recovery without implying historical backfill.

### Performance testing

Lightweight operation is an explicit v0.1 requirement. Use event-driven waiting,
bounded queues/work/memory, incremental log retrieval, efficient bounded SQLite
writes and controlled retention, with backpressure and source-health visibility.

Benchmark idle CPU, typical CPU, memory consumption, disk growth, event bursts and
slow receiver/database behavior under recorded prototype/source/workload conditions.
Establish actual acceptance thresholds after measurement; no CPU/memory budget is
invented by this architecture. Fixture/simulated bursts should precede separately
authorized actual-source runtime tests; no implicit connector stress/concurrent-
subscriber experiment is authorized. See the [benchmark requirement](product-experience.md#lightweight-operation-and-benchmark-requirement).

## 8. Deferred features

The following features are intentionally outside the initial implementation scope.

| Feature | Reason for postponement |
|---|---|
| Multi-event correlation, event counts/windows and sequences | v0.2 planning; first validate the complete v0.1 pipeline |
| Multiple supporting events, evidence aggregation/relationships and richer timelines | v0.2 planning; v0.1 links one alert to one triggering event |
| Advanced/context-dependent behavioral evaluation | v0.2 planning; exact rules/semantics are not finalized |
| Automatic logging/auditing configuration | Stretch goal requiring separate design/approval; the entire initial release preserves existing configuration |
| Optional AI interpretation | Future assistance; independent of deterministic detection and subject to privacy design |
| Additional filesystem monitoring | Evaluate after existing-log pipeline; source/interface choice remains proposed |
| eBPF monitoring | Establish basic collection first |
| Machine-learning detection | Begin with explainable rule-based detection |
| Guided remediation and controlled automatic hardening | Long-term M8 objective with staged authorization, backups, verification and rollback; initial product remains monitoring-only |
| YARA integration | Consider after the detection pipeline works |
| Remote monitoring | Initial target is one host |
| Multiple Linux distributions | Stabilize Ubuntu support first |
| Remote evidence preservation | Requires additional infrastructure |

These features may be reconsidered as the project develops.

The [implementation-readiness plan](implementation/v0.1-implementation-plan.md)
provides proposed component details, permission/decision matrices and gated small
milestones. It is not a new implementation or dependency authorization and does
not change the accepted v0.1/v0.2 boundary.

## 9. Open design questions

The following details require further investigation before implementation:

1. Which exact Linux Audit integration mechanism should the collector use?
2. What minimum privileges does each collector adapter require?
3. What should the initial event retention period and disk usage limits be?
4. What should the final JSON Lines IPC protocol and acknowledgment mechanism look like?
5. What authentication mechanism should protect the local dashboard?
6. What should the initial rule configuration schema support?
7. How should the application handle collection gaps and monitoring interruptions?
8. Does root-only access include sudo-authorized administrators?
9. Which event fields and custom namespace, if any, should become the validated contract?
10. How should capability/field assessments be sampled, stored, refreshed, and connected to rule readiness and recovery?
11. How should missing or unreliable activity timestamps be represented? No fallback policy is finalized.
12. Which concurrency, source-isolation and supervision mechanisms implement the established graceful-degradation requirement?

These questions do not prevent us from proceeding with the overall architecture.

## 10. Initial implementation objective

The first major engineering objective is to establish a complete event pipeline.

A real event generated on Ubuntu should:

1. Be captured by the C++ collector.
2. Be normalized into the canonical event schema.
3. Be transmitted to Python.
4. Be validated.
5. Be stored in SQLite.
6. Be retrievable through the API.
7. Be visible in the local web dashboard.

This is the first meaningful demonstration that the project is a functioning security monitoring application rather than simply a dashboard.

**Development should prioritize a reliable end-to-end pipeline before implementing sophisticated detection rules or frontend features.**

For v0.1 release completion, also demonstrate a basic individual-event rule alert,
its matched condition and traceable triggering event, root-only search/detail and
health views, and graceful degradation/security checks. Correlation, multi-event
evidence management and behavioral timelines are v0.2 plans, not hidden pipeline
acceptance criteria.

## 11. Architecture baseline

The following decisions constitute the initial agreed design baseline:

- Ubuntu 26.04 LTS is the initial target platform.
- The application will be local-first.
- The collector will be written in C++20.
- Python receives/validates normalized C++ events and performs analysis, detection and correlation; native source ingestion/parsing remains in C++.
- SQLite will provide local persistent storage.
- Unix domain sockets will connect the collector and backend.
- JSON Lines will provide the initial IPC serialization format.
- FastAPI will expose the application API.
- React and TypeScript will provide the dashboard.
- Existing journald and available Linux Audit records are initial candidate sources; coverage is not guaranteed.
- Throughout the initial release, HIDS must not modify journald configuration, PAM configuration, auditd configuration, or Linux Audit rules. This applies during installation, startup, discovery, and runtime.
- Graceful degradation must preserve other sources, authorized dashboard/stored-data access, source status reporting, rule limitations, and detectable recovery.
- ECS 9.5.0 is the initial reference: prefer Core and relevant Extended fields; `hids.*` is provisional.
- Root-only human access, least privilege, and evidence-first detection without confidence scores or automatic labels are initial requirements.
- v0.1 detection uses simple deterministic individual-event rules; event correlation and multi-event supporting evidence are deferred to v0.2 by ADR-007.
- The initial product will not automatically remediate threats; future M8 hardening requires separate design and authorization with the safeguards in section 1.3.
- The application will eventually ship as a Debian package with systemd integration.
- Components will communicate through documented and versioned interfaces, with appropriate validation on both sides of IPC.
- Activity time, collection time and processing/storage time remain distinct. Missing/unreliable activity timestamps are an unresolved schema decision; never invent them or silently substitute collection time.

