# HIDS Threat Model

**Document version:** 0.1  
**Status:** Initial threat-model baseline  
**Last updated:** November 4, 2026  
**Target platform:** Ubuntu 26.04 LTS

## 1. Purpose

This document records the initial security assumptions, trust boundaries, privilege requirements, privacy requirements, and known limitations of the HIDS itself.

The HIDS is a security application, so its own architecture must avoid introducing unnecessary security risks.

This is an initial baseline, not a complete threat analysis. Detailed attacker capabilities, attack trees, and risk ratings remain to be developed.

## 2. Security objectives

The architecture establishes the following objectives:

- Do not run the entire application as root.
- Give each component only the permissions it needs.
- Keep the database local and restrict access to the application account.
- Keep network services bound to localhost.
- Avoid exposing privileged system operations through the API.
- Validate user-supplied queries and configuration changes.
- Report collection and transmission failures rather than silently losing events.
- Handle collected sensitive information carefully.

## 3. Assets and sensitive information

The application may collect or store:

- System and authentication logs.
- Process execution history.
- Usernames and user IDs.
- Process IDs and parent process IDs.
- Executable paths and command-line arguments.
- Filesystem change information.
- IP addresses and other source metadata, where available.
- Generated alerts and their supporting event references.
- Collection checkpoints and application configuration.

Command-line arguments, usernames, filenames, and IP addresses may contain sensitive information and should be handled accordingly.

## 4. Components and trust boundaries

The initial architecture has these major boundaries:

1. **Operating system to collector:** The collector reads system logs, audit information, process metadata, and eventually selected filesystem activity.
2. **Collector to Python backend:** Normalized events cross a local Unix domain socket using the initial JSON Lines serialization format.
3. **Python backend to SQLite:** The backend validates and processes events, then owns database writes.
4. **Browser to local API:** The dashboard communicates with the FastAPI service, which is intended to bind to localhost only.

The permissions, validation requirements, and failure behavior at each boundary must be tested and documented during implementation.

## 5. Privilege model

### 5.1 Installation and configuration

Privileged installation operations may:

- Create service accounts.
- Configure systemd units.
- Configure required audit rules.
- Establish filesystem permissions.
- Install application files.

### 5.2 C++ collector

The collector runs with the minimum permissions required to access its monitoring sources.

Its privileges should be evaluated individually for journald, audit, and filesystem monitoring.

### 5.3 Python backend

The Python backend runs as an unprivileged service account.

It owns:

- SQLite database writes.
- Detection processing.
- Alert generation.
- API operations.

### 5.4 Dashboard

The dashboard runs as part of the local application and must not expose privileged administrative functionality.

## 6. Service hardening

Potential systemd hardening options include:

- `NoNewPrivileges`
- `ProtectSystem`
- `ProtectHome`
- `PrivateTmp`
- `CapabilityBoundingSet`
- `ReadOnlyPaths`
- `ReadWritePaths`

These restrictions must be tested against actual monitoring requirements. Applying them without testing could prevent required collection operations.

The application should not grant broad privileges merely for convenience.

## 7. API and local browser security

The API should:

- Bind to localhost only.
- Validate incoming Host and Origin headers.
- Implement appropriate authentication and CSRF protections.
- Avoid exposing privileged system operations.
- Validate user-supplied queries and configuration changes.

Localhost-only binding is an architectural requirement, not a substitute for the other browser and API protections.

The exact authentication mechanism remains an open design question.

## 8. Reliability and monitoring integrity

A monitoring application should report when its own collection or transmission is impaired.

The collector and ingestion pipeline should:

- Handle temporary backend unavailability.
- Avoid unbounded memory queues.
- Implement appropriate buffering or local spooling.
- Avoid silently losing events.
- Report collection and transmission failures.
- Support duplicate detection.
- Maintain collection checkpoints.
- Handle collector and system restarts.

The precise acknowledgment mechanism, gap detection behavior, and recovery guarantees remain open design questions.

## 9. Known threat-model limitation

A locally running HIDS cannot guarantee trustworthy evidence against an attacker with full root privileges.

Such an attacker may disable monitoring services or modify local records.

The application must not claim to provide tamper-proof evidence against a fully compromised host.

Remote evidence preservation is deferred and would require additional infrastructure.

## 10. Privacy requirements

Privacy is a core design requirement.

Initial principles:

- No cloud dependency.
- No external telemetry by default.
- Local database storage.
- Configurable retention.
- Avoid unnecessary collection of sensitive information.
- Restrict database access to the application account.
- Keep network services bound to localhost.
- Document exactly what information is collected.

The initial event retention period and disk usage limits remain open design questions.

## 11. Detection scope relevant to the threat model

The first version is intended to detect a small set of useful, testable scenarios:

| Rule ID | Detection | Initial severity |
|---|---|---|
| AUTH-001 | Repeated authentication failures | Medium |
| AUTH-002 | Successful login following repeated failures | High |
| PROC-001 | Execution from suspicious temporary locations | Medium |
| PRIV-001 | Unexpected privilege escalation | Medium |
| FILE-001 | Modification of selected sensitive system files | High |

These are initial classifications, not universal judgments. The scenarios are not proof that an attack occurred. Rules should be configurable, and false positives should be treated as an important engineering concern.

## 12. Open threat-model questions

The following items require further investigation:

1. What minimum privileges does each collector adapter require?
2. Which exact Linux Audit integration mechanism should the collector use?
3. How should the application detect and communicate collection gaps?
4. What authentication mechanism should protect the local dashboard?
5. What retention limits should apply to potentially sensitive event data?
6. What should happen if local database files or application configuration are modified?
7. Which attacker capabilities are in scope for the first release, beyond the known root-compromise limitation?

## 13. Related documents

- Architecture: `architecture.md`
- Event representation: `event-schema.md`
- Privilege separation and security decisions: `decisions/004-privilege-separation.md`
