# HIDS Threat Model

**Document version:** 0.4.0  
**Status:** Initial threat-model baseline  
**Last updated:** November 5, 2026  
**Target platform:** Ubuntu 26.04 LTS

## 1. Purpose

This document records the initial security assumptions, trust boundaries, privilege requirements, privacy requirements, and known limitations of the HIDS itself.

The HIDS is a security application, so its own architecture must avoid introducing unnecessary security risks.

These are requirements and design assumptions, not implemented protections. The repository currently contains documentation and directory scaffolding only. This is an initial baseline, not a complete threat analysis. Detailed attacker capabilities, attack trees, and risk ratings remain to be developed.

## 2. Product Security Scope

The initial product is a host-based monitoring and detection application for an individual's Ubuntu computer.

The HIDS will:

- Collect and normalize operating-system events.
- Identify activity matching configured detection rules.
- Correlate related events.
- Generate alerts with supporting evidence.
- Explain which observations and rule conditions produced an alert.
- Present event history and alerts through a local dashboard.

The initial product will **detect and explain only**.

It will not:

- Automatically terminate processes.
- Block network connections.
- Modify system configuration to stop a suspected threat.
- Disable accounts or services.
- Automatically quarantine or delete files.
- Provide prescriptive instructions for stopping or removing threats as a product feature.

Remediation, threat remediation recommendations, and intrusion prevention are outside initial scope. Monitoring coverage recommendations are within scope: explain missing fields, unavailable sources, limitations, and information that would improve monitoring. They do not authorize automatic configuration changes or threat remediation.

## 3. Security Objectives

The architecture establishes the following objectives:

- Do not run the entire application as root.
- Give each component only the permissions it needs.
- Keep the database local and restrict direct database access.
- Keep network services bound to localhost.
- Avoid exposing privileged system operations through the API.
- Validate user-supplied queries and configuration changes.
- Report collection and transmission failures rather than silently losing events.
- Handle collected sensitive information carefully.
- Restrict human access to collected security information to root.
- Prevent unauthenticated access to the dashboard and API.
- Protect database files, backups, and application configuration against ordinary local users.
- Preserve the distinction between observed events, rule matches, and interpretations.

## 4. Assets and Sensitive Information

The application may collect or store:

- System and authentication logs.
- Process execution history.
- Usernames and user IDs.
- Process IDs and parent process IDs.
- Executable paths and command-line arguments.
- Filesystem change information.
- IP addresses and other source metadata, where available.
- Generated alerts and their supporting event references.
- Detection rules and their configuration.
- Collection checkpoints and application configuration.
- Original source records retained for troubleshooting or future normalization.

Command-line arguments, usernames, filenames, IP addresses, and original log records may contain sensitive information and should be handled accordingly.

The confidentiality, integrity, and availability of collected records are all relevant. An attacker who can delete or alter records may impair the HIDS even if they cannot read them.

## 5. Components and Trust Boundaries

The initial architecture has these major boundaries:

1. **Operating system to collector:** The collector reads system logs, audit information, process metadata, and eventually selected filesystem activity.
2. **Collector to Python backend:** Normalized events cross a local Unix domain socket using the initial JSON Lines serialization format.
3. **Python backend to SQLite:** The backend independently validates normalized C++ events, performs detection/correlation/security analysis, and owns database writes. It does not independently ingest native OS records. C++ validates native input and outgoing normalized representations; preserve validation on both IPC endpoints.
4. **Browser to local API:** The dashboard communicates with the FastAPI service, which is intended to bind to localhost only.
5. **Application to local user:** Dashboard and API access must be authenticated and authorized according to the root-only access policy.

The permissions, validation requirements, and failure behavior at each boundary must be tested and documented during implementation.

## 6. Privilege Model

### 6.1 Installation and configuration

Privileged installation operations may:

- Create service accounts.
- Configure HIDS application systemd units.
- Establish filesystem permissions.
- Install application files.

Throughout the initial release, HIDS must not modify journald configuration, PAM configuration, auditd configuration, or Linux Audit rules. This applies during installation, startup, discovery, and runtime.
It uses existing Ubuntu logging and auditing infrastructure. Automatically
configuring additional logging or auditing is a stretch goal requiring separate design and approval. Changes to HIDS application files and its own service units are distinct from changes to Ubuntu logging configuration. The earlier baseline
allowed audit-rule configuration; that permission is superseded as recorded in
[ADR-004](decisions/004-privilege-separation.md).

These operations do not imply that the application services should run as root.

### 6.2 C++ collector

The C++ collector owns source collection, native ingestion/parsing, normalization and collection-side event processing, with the minimum permissions required for its monitoring sources.

Its privileges should be evaluated individually for journald, audit, and filesystem monitoring.

The collector should not receive broad administrative privileges merely for convenience.

### 6.3 Python backend

The Python backend runs as an unprivileged service account.

It owns:

- SQLite database writes.
- Detection processing.
- Alert generation.
- API operations.

The backend requires access to the database to perform its work. This service-account access is distinct from human authorization to view HIDS data.

A compromise of the backend may expose or modify data accessible to its service account. Privilege separation limits the scope of that compromise but does not eliminate the risk.

### 6.4 Dashboard

The dashboard is a local web interface and must not expose privileged administrative functionality.

The browser should not need to run as root merely to display the dashboard. The authentication design must enforce the root-only policy without treating frontend visibility as authorization.

## 7. Data Confidentiality and Access Control

### 7.1 Access policy

The initial release will restrict human access to collected security information to root only.

This includes:

- Collected system events.
- Authentication and process history.
- Generated security alerts.
- Alert explanations and supporting evidence.
- Detection rules and their configurations.
- Application security and monitoring status.

Multiple-user access is explicitly outside the scope of the initial release.

The precise definition of root-only access must be settled before authentication is implemented. In particular, the project must decide whether access means the root account (UID 0) exclusively or also includes users authorized through `sudo`. Ordinary local users must not receive access by default.

### 7.2 Database and file protection

The SQLite database contains potentially sensitive information about system activity and security state.

Requirements:

- Database files must not be readable or writable by ordinary users.
- Direct database access must be restricted to the designated application service account and root.
- Database backups must receive equivalent protection.
- Application configuration and sensitive files must have restrictive filesystem permissions.
- Temporary files and exports containing event data must receive equivalent protection.
- Database access must not be exposed through unauthenticated API endpoints.

The Python backend requires database access to process and store events. This does not grant ordinary human users permission to access the database directly.

### 7.3 Dashboard and API authorization

All dashboard and API access involving security information must require authentication and authorization.

Requirements:

- Only access authorized under the root-only policy may retrieve security information.
- Authentication and authorization must be enforced by the backend, not merely the frontend.
- Sensitive API endpoints must enforce authorization independently.
- Unauthenticated requests must not expose event contents, alerts, detection rules, or sensitive system metadata.
- Localhost-only network binding must not be treated as sufficient authentication.
- Authentication failures must not reveal sensitive information.

The exact authentication mechanism remains undecided and must be specified before dashboard implementation.

### 7.4 Encryption at rest

Encryption at rest is a potential additional protection.

Its purpose would be to protect collected information if someone obtains an offline copy of the database or storage device.

However, encryption at rest does not protect against an attacker with root privileges while the application is running and its encryption keys are accessible.

The encryption implementation and key-management strategy remain open design questions.

## 8. API and Local Browser Security

The FastAPI backend is a security-sensitive component.

Although the API is intended to bind exclusively to localhost, local network isolation must not be treated as sufficient protection. Local processes and browser-based attacks may still interact with local services.

Potential attack scenarios include:

- Unauthorized local processes accessing the API.
- Browser-based attacks targeting localhost.
- Authentication bypass.
- Broken authorization checks.
- SQL injection.
- Command injection.
- Path traversal.
- Denial of service or resource exhaustion.
- Sensitive information disclosure.
- Exploitation of vulnerable dependencies.
- Unsafe handling of untrusted event data.

Security requirements:

1. Enforce authentication and authorization on the backend, not merely in the frontend.
2. Restrict access to security information according to the root-only policy.
3. Use parameterized database queries.
4. Validate all incoming data.
5. Do not expose arbitrary SQL execution.
6. Do not expose arbitrary shell command execution.
7. Do not expose unrestricted filesystem operations.
8. Restrict request sizes and resource consumption.
9. Validate Host and Origin headers.
10. Implement appropriate CSRF protections for the chosen authentication design.
11. Avoid exposing sensitive information through errors and application logs.
12. Keep dependencies updated and conduct security testing.
13. Treat event content and other collected source data as untrusted input when displaying or processing it.

The API should expose narrowly defined application operations rather than general-purpose system access.

A compromise of the API or Python backend may expose the security information accessible to that component. The backend's unprivileged service account and filesystem restrictions should limit the potential impact of such a compromise.

Localhost binding does not protect against a fully compromised local operating system.

## 9. Service Hardening

Potential systemd hardening options include:

- `NoNewPrivileges`
- `ProtectSystem`
- `ProtectHome`
- `PrivateTmp`
- `CapabilityBoundingSet`
- `ReadOnlyPaths`
- `ReadWritePaths`

These restrictions must be tested against actual monitoring requirements. Applying them without testing could prevent required collection operations.

The application should not grant broad privileges merely for convenience. Each service should receive only the filesystem access, capabilities, and group memberships it needs.

## 10. Reliability and Monitoring Integrity

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

Graceful degradation is an initial-release requirement. If a collection source
is missing, inaccessible, or failing, other functioning sources must continue
operating. The dashboard and stored data must remain accessible under the existing
authorization policy. Report the affected source's status and limitations of rules
that require unavailable information; recovery must be detectable. This does not
promise historical backfill. Concurrency, process isolation, and supervision
mechanisms remain undecided.

The precise acknowledgment mechanism, gap detection behavior, and recovery guarantees remain open design questions.

[Capability and field discovery](research/field-discovery.md) must distinguish
source availability/access from fields actually observed and from rule readiness.
Reassess at startup, periodically, and after source changes; identify gaps and
failures and explain recovery limits. Empty history does not establish a healthy
collector. Check actual service identities without automatically granting access.
Protect capability inventories and coverage reports as security data.

An attacker who can impair collection or alter local records may undermine the HIDS even without obtaining access to the dashboard.

## 11. Privacy Requirements

Privacy is a core design requirement.

Initial principles:

- No cloud dependency.
- No external telemetry by default.
- Local database storage.
- Configurable retention.
- Avoid unnecessary collection of sensitive information.
- Restrict direct database access to the application account and root.
- Keep network services bound to localhost.
- Document exactly what information is collected.
- Protect raw source records, exports, and backups.
- Sanitize test fixtures before committing them to the repository.
- Distinguish discovery of field existence/types from retention of actual values;
  broad catalogs do not authorize indiscriminate collection.
- Arguments, environment variables and original messages may contain credentials;
  usernames, IP addresses and linked identifiers also need privacy review.
- Preserve representative raw research records only in a protected environment,
  under bounded retention; avoid leaking sensitive payloads through diagnostics.

The initial event retention period and disk usage limits remain open design questions.

Source availability is not guaranteed: do not assume auditd is present or that
process execution or filesystem changes are recorded. Report missing sources,
fields, collection gaps, and resulting visibility limitations. Missing records
are not proof that activity did not occur.

## 12. Initial Detection Scope

The following are proposed initial scenarios and severity defaults, not implemented rules or guaranteed initial-release coverage. Each requires source feasibility research under the existing-logging constraint:

| Rule ID | Detection | Initial severity |
|---|---|---|
| AUTH-001 | Repeated authentication failures | Medium |
| AUTH-002 | Successful login following repeated failures | High |
| PROC-001 | Execution from suspicious temporary locations | Medium |
| PRIV-001 | Unexpected privilege-related activity | Medium |
| FILE-001 | Modification of selected sensitive system files | High |

These are initial classifications, not universal judgments. The scenarios are not proof that an attack occurred. Rules should be configurable, and false positives should be treated as an important engineering concern.

Preserve detection indicators, matched conditions, and supporting evidence. Do not assign numerical confidence scores or automatic qualitative confidence labels; severity is separate from confidence. Users interpret findings, potentially with optional AI assistance. See [confidence.md](confidence.md).

The initial HIDS is detection-only. It must not automatically remediate, block, terminate, quarantine, or modify the system in response to these detections.

## 13. Known Threat-Model Limitations

A locally running HIDS cannot guarantee trustworthy evidence or confidentiality against an attacker with full root privileges.

Such an attacker may be able to:

- Read the database and application memory.
- Access encryption keys available to running services.
- Modify application configuration.
- Disable monitoring services.
- Modify or delete collected events and alerts.
- Replace or tamper with application binaries.

The application must not claim to provide tamper-proof evidence or protection against a fully compromised host.

Remote evidence preservation is deferred and would require additional infrastructure.

## 14. Open Threat-Model Questions

The following items require further investigation:

1. What minimum privileges does each collector adapter require?
2. Which exact Linux Audit integration mechanism should the collector use?
3. How should the application detect and communicate collection gaps?
4. What authentication mechanism can enforce root-only dashboard access without requiring the browser or entire application to run as root?
5. Does root-only access mean UID 0 exclusively, or should sudo-authorized administrators also qualify?
6. What retention limits should apply to potentially sensitive event data?
7. Should the SQLite database use encryption at rest, and how should encryption keys be managed?
8. What should happen if local database files or application configuration are modified?
9. Which attacker capabilities are in scope for the first release, beyond the known root-compromise limitation?
10. What protections are needed for local browser-to-API requests, including Host, Origin, and CSRF handling?
11. What is the recovery behavior when the collector, backend, or database becomes unavailable?
12. Which concurrency, isolation and supervision mechanisms will implement graceful degradation without coupling source availability?

## 15. Related Documents

- Architecture: `architecture.md`
- Event representation: `event-schema.md`
- Schema research and evolution process: `schema-design-process.md`
- Detection evidence and interpretation: `confidence.md`
- Privilege separation and security decisions: `decisions/004-privilege-separation.md`
