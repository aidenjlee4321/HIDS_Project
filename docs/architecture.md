# Host-Based Intrusion Detection System (HIDS)
## Architecture

**Document version:** 0.1  
**Status:** Initial design baseline  
**Last updated:** November 4, 2026  
**Target platform:** Ubuntu 26.04 LTS  
**Project name:** TBD

## 1. Project overview

### 1.1 Purpose

The project aims to develop a local-first Host-Based Intrusion Detection System (HIDS) for individual Linux computers.

The application will monitor operating system activity, identify potentially suspicious behavior, and present security information in an understandable dashboard.

Unlike traditional enterprise SIEM platforms, this project focuses on making host-level security monitoring accessible to ordinary computer users.

The primary objectives are:

- Collect and normalize operating system events.
- Monitor process execution, authentication activity, and potentially suspicious system changes.
- Identify suspicious activity through configurable detection rules.
- Correlate related events to identify more complex behavioral patterns.
- Explain security alerts in understandable language.
- Provide searchable event history and an interactive dashboard.
- Store collected information locally by default.

The long-term objective is to produce a properly packaged Linux application that users can install, operate, upgrade, and uninstall without manually configuring its development environment.

### 1.2 Project philosophy

The project prioritizes:

1. **Usability:** Security information should be understandable to users without specialized cybersecurity knowledge.
2. **Reliability:** Monitoring should operate continuously and report failures rather than silently losing events.
3. **Privacy:** Collected information should remain local by default.
4. **Modularity:** Components should communicate through documented interfaces and be independently maintainable.
5. **Efficiency:** The application should have a small resource footprint suitable for ordinary personal computers.
6. **Transparency:** Alerts should explain why they were generated and provide supporting evidence.

### 1.3 Scope

The initial product will be a monitoring and detection application, not an automated remediation system.

The HIDS will identify suspicious activity and recommend investigation steps. It will not automatically terminate processes, block network connections, or attempt malware removal.

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

The architecture should avoid unnecessary Ubuntu-specific dependencies outside the collection and packaging layers. This will make future distribution support easier.

## 3. Technology stack

| Component | Technology | Responsibility |
|---|---|---|
| Event collector | C++20 | Operating system integration and event collection |
| System log integration | systemd journal API | Collect structured system logs |
| Process monitoring | Linux Audit | Capture process execution and audit events |
| Filesystem monitoring | inotify / fanotify | Detect selected filesystem changes |
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

Technology choices may be revised if implementation reveals significant performance, reliability, or compatibility issues.

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

The Python service initially hosts the ingestion, analysis, database, and API functionality. These will be separate internal modules rather than separate network services.

### 4.2 Collection layer (C++)

The collector is responsible for interacting with Linux and capturing system events.

It should be designed around independent source adapters.

#### Journal adapter

Uses the native systemd journal API (`libsystemd`) to retrieve structured journal entries.

Responsibilities:

- Collect system logs.
- Collect authentication-related logs.
- Preserve original timestamps and metadata.
- Maintain journal cursors.
- Handle service restarts and log rotation.

#### Audit adapter

Uses the Linux Audit infrastructure to capture events that are not reliably represented in ordinary system logs.

Initial focus:

- Process execution.
- User and privilege information.
- Relevant security-sensitive operations.

The existing audit daemon (`auditd`) should manage the kernel audit interface.

The collector must not attempt to compete with `auditd` for ownership of the audit event stream. Integration should use an appropriate audit dispatcher mechanism or a carefully implemented audit-log consumer.

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

Converts source-specific records into a common event format.

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

It will initially consist of five logical modules.

| Module | Responsibility |
|---|---|
| Ingestion | Receive, validate, and process incoming events |
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
- Confidence.
- Enabled/disabled state.

YAML is the proposed configuration format.

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
- Confidence.
- Description of what happened.
- Explanation of why the alert triggered.
- Supporting event references.
- Timestamp.
- Suggested investigation steps.
- Alert status.

Severity and confidence must remain separate concepts.

Severity describes the potential impact of the activity. Confidence describes how strongly the available evidence supports the detection.

### 4.4 Data storage

SQLite will be the application's primary persistent storage system.

The Python backend will own database writes. The C++ collector will communicate with Python rather than independently modifying the database.

Initial database tables:

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
- Implement appropriate authentication and CSRF protections.
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

#### Alert Explorer

- Alert list.
- Severity indicators.
- Confidence indicators.
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

The repository is organized as follows:

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

**Acceptance criteria:** Events collected from Ubuntu reliably arrive in SQLite.

### Phase 3: Process and authentication monitoring

- Integrate Linux Audit.
- Capture process execution events.
- Collect authentication activity.
- Enrich events with process and user metadata.

**Acceptance criteria:** The application can demonstrate meaningful visibility into process and authentication activity.

### Phase 4: Detection engine

- Implement rule evaluation.
- Support YAML configuration.
- Implement severity and confidence.
- Generate alerts.
- Build automated detection tests.

**Acceptance criteria:** Controlled suspicious scenarios trigger the expected alerts.

### Phase 5: Dashboard and API

- Implement FastAPI endpoints.
- Build React dashboard.
- Add event search and filtering.
- Add alert investigation.
- Display system health.

**Acceptance criteria:** Users can investigate collected events and generated alerts through a browser.

### Phase 6: Correlation and advanced monitoring

- Implement time-window correlation.
- Associate related events.
- Improve process relationship tracking.
- Add filesystem monitoring.
- Improve alert explanations.

**Acceptance criteria:** The HIDS can recognize and explain meaningful multi-event patterns.

### Phase 7: Packaging and deployment

- Build Debian package.
- Configure systemd services.
- Implement service permissions and hardening.
- Configure automatic startup.
- Implement installation, upgrade, and removal procedures.

**Acceptance criteria:** A clean Ubuntu installation can install and operate the application without requiring the development environment.

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
- Analysis and detection will be implemented in Python.
- SQLite will provide local persistent storage.
- Unix domain sockets will connect the collector and backend.
- JSON Lines will provide the initial IPC serialization format.
- FastAPI will expose the application API.
- React and TypeScript will provide the dashboard.
- Linux Audit and journald will provide the initial event sources.
- Detection will use configurable rules and event correlation.
- The application will not automatically remediate threats.
- The application will eventually ship as a Debian package with systemd integration.
- Components will communicate through documented and versioned interfaces.

**This document is the working architectural baseline for HIDS v0.1.**

Changes should be documented as the project develops, particularly when implementation decisions affect component boundaries, security, or shared interfaces.
