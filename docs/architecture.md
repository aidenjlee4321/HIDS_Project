# Host-Based Intrusion Detection System (HIDS)
## Architecture

**Document version:** 0.4.0
**Status:** Initial design baseline  
**Last updated:** November 5, 2026  
**Target platform:** Ubuntu 26.04 LTS  
**Project name:** TBD

## Status and interpretation

Only documentation and empty directory scaffolding exist; no collection, detection,
storage, API, dashboard, or tests are implemented. Accepted technology choices are
an architecture baseline, not working functionality. Detailed fields, endpoints,
tables, rules, and layouts below are proposals unless explicitly identified as
requirements. Roadmap phases are planned work, not completed milestones.

Initial-release requirements: consume existing Ubuntu logging and auditing without
modifying journald configuration, PAM configuration, auditd configuration, or Linux
Audit rules during installation, startup, discovery, or runtime; detect and
explain only; preserve indicators and supporting evidence without confidence
scores or automatic confidence labels; restrict human security-data access to root;
maintain least privilege; store data locally and minimize sensitive collection.
Additional logging/auditing configuration is a stretch goal requiring separate design and approval. Changes to HIDS application files and its own service units are distinct from changes to Ubuntu logging configuration.

## 1. Project overview

### 1.1 Purpose

The project aims to develop a local-first Host-Based Intrusion Detection System (HIDS) for individual Linux systems.

The application will monitor operating system activity, identify potentially suspicious behavior, and present security information in an understandable dashboard.

This project focuses on making host-level security monitoring accessible to ordinary computer users.

The primary objectives are:

- Collect and normalize operating system events.
- Monitor process execution, authentication activity, and potentially suspicious system changes.
- Identify suspicious activity through configurable detection rules.
- Correlate related events to identify more complex behavioral patterns.
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

### 1.3 Scope

The initial product is strictly a monitoring and detection application.

The HIDS will identify potentially suspicious activity, generate
security alerts, and explain the evidence behind each detection.

It will not automatically remediate threats or provide prescriptive
instructions for stopping or removing them.

Remediation functionality and threat remediation recommendations are outside the initial scope. Monitoring coverage recommendations are within scope: explain missing fields, unavailable sources and limitations, and identify information that would improve monitoring. Recommendations do not authorize automatic configuration changes or remediation.

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
| Process monitoring | Existing Linux Audit records, where available | Observe only activity already recorded; coverage requires research |
| Filesystem monitoring (future proposal) | inotify / fanotify | Candidate additional monitoring; outside the initial existing-log baseline |
| Process information | /proc | Retrieve process metadata |
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

C++ owns source collection, source-native ingestion/parsing, normalization, and collection-side event processing. Python receives normalized events from C++, validates their contracts, and owns detection, correlation, security analysis and SQLite writes. Python does not independently collect native OS records.

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

Support initial startup discovery, periodic reassessment, source changes,
collection failures/gaps, and recovery when sources return. Restored access does
not prove missing historical events were recovered. An empty history does not
prove monitoring is healthy or that activity did not occur.

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
See [field discovery](research/field-discovery.md) for methodology and examples.

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

#### Audit adapter

The proposed adapter consumes existing Linux Audit records where available. Do not assume auditd is installed, enabled, or recording a particular activity. Missing sources or fields must be reported as visibility limitations, not interpreted as absence of activity.

Candidate activities, subject to existing records and source validation:

- Process execution.
- User and privilege information.
- Relevant security-sensitive operations.

The existing audit daemon (`auditd`) should manage the kernel audit interface.

The collector must not attempt to compete with `auditd` for ownership of the audit event stream. Initial integration must use an already available read path, such as an existing audit log, without changing auditd or Audit rules. A dispatcher requiring configuration changes is a future option, not an initial installation step.

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

The initial event-processing design has five logical modules below. Capability and field-coverage responsibilities are described separately above; exact module placement remains open.

| Module | Responsibility |
|---|---|
| Normalized-event receipt (backend ingestion) | Receive normalized C++ events and independently validate their contracts; no native OS collection |
| Enrichment | Add contextual information to events |
| Detection | Evaluate individual events against rules |
| Correlation | Identify patterns across multiple events |
| Alerts | Generate, group, and manage security alerts |

#### Detection engine

The detection engine should support configurable rules rather than relying on hardcoded conditions.

Rules should be stored independently from the engine implementation.

Potential rule configuration fields:

- Rule identifier.
- Rule name.
- Description.
- Event type.
- Matching conditions.
- Time window.
- Severity.
- Detection indicators and supporting evidence.
- Enabled/disabled state.

YAML is the proposed configuration format. Each rule must declare Required, Important, and Optional evidence by applicable event/role, with independent sensitivity annotations, source-semantic constraints, and explicit missing-data behavior. A missing Required field must not become a negative match or a claim of safety. See [rule field requirements](research/field-discovery.md#9-detection-rule-field-requirements).

#### Correlation engine

The correlation engine connects multiple events into potentially suspicious patterns.

Examples:

- Multiple authentication failures followed by a successful login.
- Unexpected process execution followed by privilege escalation.
- Creation of an executable followed by its execution.
- Sensitive configuration changes following suspicious process activity.

Detection and correlation are separate operations.

Detection evaluates individual events. Correlation evaluates relationships between events.

#### Alert generation

Every generated alert should contain:

- Unique alert identifier.
- Associated detection rule.
- Title.
- Severity.
- Detection indicators and supporting evidence.
- Description of what happened.
- Explanation of why the alert triggered.
- Supporting event references.
- Timestamp.
- Suggested investigation steps.
- Alert status.

Severity and confidence must remain separate concepts.

Severity describes potential impact; confidence concerns interpretation of evidence. HIDS assigns neither numerical confidence scores nor automatic qualitative confidence labels. Preserve detection indicators, matched conditions, and source evidence; present missing information, benign explanations, and limitations. Users interpret findings, potentially with optional future AI assistance. See [evidence policy](confidence.md).

### 4.4 Data storage

SQLite will be the application's primary persistent storage system.

The Python backend will own database writes. The C++ collector will communicate with Python rather than independently modifying the database.

Proposed initial database tables:

| Table | Purpose |
|---|---|
| `events` | Normalized system events |
| `alerts` | Generated security alerts |
| `alert_events` | Relationships between alerts and events |
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

Proposed dashboard sections:

#### Overview

- Total events collected.
- Active alerts.
- Recent security activity.
- Monitoring health.
- Collector status.
- Descriptive source and field coverage, affected rule requirements, assessment freshness, and gap/recovery explanations; no overall security percentage.

#### Alert Explorer

- Alert list.
- Severity indicators.
- Detection indicators, matched conditions, and evidence limitations.
- Alert explanations.
- Supporting event references.
- Investigation suggestions.

#### Event Explorer

- Searchable event history.
- Filtering by timestamp, type, source, user, and process.
- Detailed event inspection.

#### Process Activity

- Process execution history.
- Parent-child process relationships where available.
- Executable paths.
- Associated users.

#### Authentication

- Successful and unsuccessful logins.
- Repeated authentication failures.
- Relevant privilege activity.

#### Detection Rules

- Enabled and disabled rules.
- Rule descriptions.
- Severity configuration.
- Rule management.

#### Settings

- Data retention.
- Monitoring configuration.
- Application status.
- Privacy settings.

## 5. Repository structure

The following is a proposed target layout, not an inventory of implemented files. Entry points, build files, machine-readable schemas, and the root README shown here do not yet exist. Existing directories are scaffolding; see [documentation index](README.md) for current documents:

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

Development should proceed incrementally, with every milestone producing a functional and testable result.

### Phase 0: Architecture and specifications

- Finalize architecture.
- Document the threat model.
- Define the canonical event schema.
- Define the IPC protocol.
- Establish repository structure.
- Document component responsibilities.
- Establish the candidate catalog and rule-specific field requirements; define capability/field-assessment interfaces after research.

**Acceptance criteria:** The architecture and interfaces are documented sufficiently to begin implementation.

### Phase 1: Initial event collection

- Implement C++ collector.
- Integrate with journald.
- Normalize collected events.
- Implement basic event transmission.

**Acceptance criteria:** Real system events can be collected and converted into the canonical format.

### Phase 2: Ingestion and storage

- Implement Python receiver.
- Validate incoming events.
- Implement SQLite database.
- Store and retrieve events.
- Implement collector checkpointing and basic reliability mechanisms.

**Acceptance criteria:** Events collected from Ubuntu reliably arrive in SQLite. Source unavailability must not stop functioning sources or authorized dashboard/stored-data access; source status, affected rule limitations, and detectable recovery must be demonstrated.

### Phase 3: Process and authentication monitoring

- Consume existing Linux Audit records where available, without logging configuration changes.
- Observe process execution only where source records support it; report coverage gaps.
- Collect authentication activity.
- Enrich events with process and user metadata.

**Acceptance criteria:** Supported process and authentication visibility is demonstrated against actual existing Ubuntu records, with unavailable activity and fields explicitly reported.

### Phase 4: Detection engine

- Implement rule evaluation.
- Finalize rule format; YAML remains proposed.
- Implement severity, detection indicators, traceable supporting evidence, and limitations; no confidence scores or automatic labels.
- Generate alerts.
- Build automated detection tests.

**Acceptance criteria:** Controlled suspicious scenarios trigger the expected alerts.

### Phase 5: Dashboard and API

- Implement FastAPI endpoints.
- Build React dashboard.
- Add event search and filtering.
- Add alert investigation.
- Display system health, source/access changes, descriptive field coverage, and detection limitations.

**Acceptance criteria:** Users can investigate collected events and generated alerts through a browser.

### Phase 6: Correlation and advanced monitoring

- Implement time-window correlation.
- Associate related events.
- Improve process relationship tracking.
- Evaluate additional filesystem monitoring as future work outside the initial existing-log scope.
- Improve alert explanations.

**Acceptance criteria:** The HIDS can recognize and explain meaningful multi-event patterns.

### Phase 7: Packaging and deployment

- Build Debian package.
- Configure systemd services.
- Implement service permissions and hardening.
- Configure automatic startup.
- Implement installation, upgrade, and removal procedures.

**Acceptance criteria:** A clean Ubuntu installation can install and operate the application without the development environment or changes to journald configuration, PAM configuration, auditd configuration, or Linux Audit rules at installation, startup, discovery, or runtime. Limited source availability is reported explicitly.

## 7. Testing and quality requirements

Testing must be incorporated throughout development.

### Unit testing

- Event normalization.
- Schema validation.
- Rule evaluation.
- Correlation logic.
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

Monitor:

- CPU utilization.
- Memory consumption.
- Disk usage.
- Event processing throughput.
- Storage growth.

The HIDS should be lightweight enough for continuous operation on ordinary personal computers.

## 8. Deferred features

The following features are intentionally outside the initial implementation scope.

| Feature | Reason for postponement |
|---|---|
| Automatic logging/auditing configuration | Stretch goal requiring separate design/approval; the entire initial release preserves existing configuration |
| Optional AI interpretation | Future assistance; independent of deterministic detection and subject to privacy design |
| Additional filesystem monitoring | Evaluate after existing-log pipeline; source/interface choice remains proposed |
| eBPF monitoring | Establish basic collection first |
| Machine-learning detection | Begin with explainable rule-based detection |
| Automatic remediation | Initial product is monitoring-only |
| YARA integration | Consider after the detection pipeline works |
| Remote monitoring | Initial target is one host |
| Multiple Linux distributions | Stabilize Ubuntu support first |
| Remote evidence preservation | Requires additional infrastructure |

These features may be reconsidered as the project develops.

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
- Detection will use configurable rules and event correlation.
- The application will not automatically remediate threats.
- The application will eventually ship as a Debian package with systemd integration.
- Components will communicate through documented and versioned interfaces, with appropriate validation on both sides of IPC.
- Activity time, collection time and processing/storage time remain distinct. Missing/unreliable activity timestamps are an unresolved schema decision; never invent them or silently substitute collection time.

