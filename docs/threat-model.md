# HIDS Threat Model

**Document version:** 0.4.0  
**Status:** Initial threat-model baseline  
**Last updated:** November 11, 2026 (scoped implementation reconciliation)\
**Target platform:** Ubuntu 26.04 LTS

## 1. Purpose

This document records the initial security assumptions, trust boundaries, privilege requirements, privacy requirements, and known limitations of the HIDS itself.

The HIDS is a security application, so its own architecture must avoid introducing unnecessary security risks.

This model combines requirements with scoped implemented protections. M3 now has
actual Ubuntu evidence for separated reader/backend identities, authenticated IPC,
root activation, bounded parsing, durable storage/recovery and a separate checker.
M4 has read-only source access, a private destination and backend-identity
sandbox evidence, followed by an approved bounded 16-event real import trial. [Current state](current-state.md) and linked
validation records distinguish those scopes from the unfinished product/API/UI.
This is not a complete threat analysis; detailed attacker capabilities, attack
trees and risk ratings remain to be developed.

The checker's CAP_AUDIT_CONTROL is broader than its fixed query and remains a
residual risk. The M4 worker shares the backend UID: direct-path read-only sandbox
tests do not establish protection from compromised same-UID/root processes or
shared CPU/storage interference. Base64 exe/comm is sensitive retained data, not
encryption. M4 has since passed the approved bounded real-data import/storage trial;
unattended monitoring, supported security rules and dashboard authentication
remain gated. See [real-data evidence](validation/m4-real-data-trial.md).

## 2. Product Security Scope

The initial product is a host-based monitoring and detection application for an individual's Ubuntu computer.

The HIDS will:

- Collect and normalize operating-system events.
- Identify activity matching configured detection rules.
- In v0.2 planning, correlate related events; v0.1 uses individual-event rules.
- Generate v0.1 alerts traceable to one triggering event and matched rule condition; multi-event evidence is v0.2 planning.
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

### First-run consent and source-control boundary

The accepted [product experience](product-experience.md#first-run-experience)
requires explicit authorized confirmation before security-event collection.
Discovery results, source recommendations, selection/configuration and runtime
health are protected security data. The ordinary-user usability goal does not
relax root-only human access or require a root browser/backend.

Pre-confirmation discovery may inspect recognized-source metadata/configuration
and non-collecting access evidence under the intended service identity. It cannot
sample log payloads, subscribe to cn_proc, initialize an event reader or inspect
unrelated process context to prove field presence. Read-only payload reads are
still collection. Static support or prior authorized evidence is not demonstrated
current runtime function; unverified fields must remain labeled as such.

Treat draft, confirmed selection, initialization results and runtime status as
separate facts. Backend and collector orchestration must reject unconfirmed,
unselected, stale/unauthorized source-start requests and arbitrary paths/commands;
frontend checkbox state alone is not authorization. New sources/permission changes
must not silently expand collection. Exact confirmation persistence, restart,
edit/retry and control-contract behavior remain open in D-14 of the
[readiness register](implementation/v0.1-implementation-plan.md#decision-register).

Selections control HIDS collection only: never change journald/PAM/auditd settings,
Audit rules, kernel settings, service privileges or OS logging services. A selected
source can fail; show actual runtime status and preserve the functioning confirmed
subset plus authorized configuration/history access. Disabled or awaiting-confirmation
is not an intrusion finding or proof of a healthy system. No hidden initialization,
privilege escalation or automatic configuration repair is authorized.

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
[ADR-007](decisions/007-initial-release-scope.md) defers correlation/multi-event
evidence to v0.2 without weakening these boundaries or root-only access. The
backend's eventual correlation ownership is not a v0.1 module requirement.

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

**Owner decision D-12a, November 12, 2026:** each new dashboard session may be
authorized by an explicit HIDS access action executed as UID 0, including through
OS-authorized `sudo`. Ordinary local access, administrator-group membership and
prior sessions grant no automatic access. This does not prove the initiating
human identity or require a fresh password prompt when OS sudo policy permits
cached authorization. No sudo/PAM policy change is implied. The
[accepted eligibility record](implementation/dashboard-access-eligibility-review.md)
and separately accepted [synthetic-only mechanism](implementation/dashboard-session-mechanism-review.md)
now have [bounded acceptance evidence](validation/dashboard-session-pilot.md).
Real-data routes and production origin trust still require review before exposure.

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

D-12a/D-12b define the accepted root/sudo synthetic session mechanism; its bounded
acceptance alone does not authorize real-data exposure. Owner-accepted
[D-12c](implementation/m4-history-view-review.md) separately authorizes a bounded,
frozen view of selected retained data over verified HTTPS, with direct peer trust
in an isolated ordinary-user Chromium HOME/NSS/user-data environment.
[Acceptance](validation/m4-history-view-acceptance.md) verified per-route history
scope, read-only mounts, closed database before serving, lossless/text-only detail,
logout/stale-response handling, TLS negatives and production preservation. No CA,
normal-profile trust, collection or unattended deployment follows authentication.
The ordinary browser/account and backend UID remain entrusted; same-UID malware,
root/backend/browser compromise and previously copied data are outside this claim.

### 7.4 Independent process observation

The [owner-reported cn_proc experiment](research/process-connector.md) successfully
subscribed to a system-wide process-notification interface as an ordinary user,
without sudo, on Ubuntu 26.04.1 / kernel 7.0.0-42-generic ARM64. The report printed
only its controlled child. It does not establish access to every other user's
activity or every Linux configuration, but it demonstrates that dashboard
credentials are not necessarily required to obtain process notifications directly
from the kernel on this tested environment.

Root-only dashboard/API and file access protect HIDS-retained history, enriched
data and analysis; they do not prevent an independent local listener from observing
available lifecycle timing and identifiers. Combining such observations can expose
usage patterns and process relationships. This does not mean the tested mask
provided executable paths, arguments or credentials. Protect any enrichment and
stored correlation separately, minimize values and avoid public debug/stdout
streams. Service-account permissions and other-user visibility need scoped testing.
Do not weaken root-only HIDS access or change kernel/logging permissions to conceal
this limitation. No confidentiality guarantee against independent OS-level
observation is asserted.

### 7.5 Encryption at rest

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

cn_proc is a provisional live source, not a checkpointed historical log. The
initial native adapter reports errors and interruption diagnostics without
promising replay, exact loss counts or service recovery. Kernel cleanup concerns
require serialized controls, explicit unsubscribe and no automatic reconnect or
privilege retry. A missing ACK and observed delivery are separate status facts.
A failed process source must not terminate other functioning source adapters;
whole-application isolation and availability are not verified by this component.

[Capability and field discovery](research/field-discovery.md) must distinguish
source availability/access from fields actually observed and from rule readiness.
Reassess at startup, periodically, and after source changes; identify gaps and
failures and explain recovery limits. Empty history does not establish a healthy
collector. Check actual service identities without automatically granting access.
Protect capability inventories and coverage reports as security data.

An attacker who can impair collection or alter local records may undermine the HIDS even without obtaining access to the dashboard.

### Resource exhaustion and lightweight acceptance

v0.1 must use bounded queues/work/memory, incremental/event-driven collection,
efficient bounded SQLite writes and controlled disk retention, with visible
backpressure and source/receiver/database health. Source selection is not permission
to consume unbounded resources; disabled/unconfirmed sources must not perform
background event reads. Benchmark idle/typical CPU, memory, disk growth, event
bursts and slow database/receiver behavior under recorded conditions. Establish
actual acceptance thresholds after prototype measurement; no CPU/memory budgets
are asserted here. Benchmarks are not confidence/safety scores and do not authorize
live connector stress tests or changes to Ubuntu settings.

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

[Release scope](release-scope.md) requires only simple deterministic individual-
event rules in v0.1. One failed authentication event can be recognized/categorized;
repeated failures and failure-to-success sequences require multi-event analysis
and are v0.2 plans. The historical scenarios/severities below are retained as
proposals, not finalized rules, security guarantees or mandatory v0.1 coverage.

| Rule ID | Historical candidate | Release boundary | Proposed severity |
|---|---|---|---|
| AUTH-001 | Repeated authentication failures | v0.2 correlation planning | Medium |
| AUTH-002 | Successful login following repeated failures | v0.2 correlation planning | High |
| PROC-001 | Execution from suspicious temporary locations | v0.1 candidate only if one execution event's supported context satisfies a simple condition | Medium |
| PRIV-001 | Unexpected privilege-related activity | Single-event conditions may be considered; behavioral sequences are v0.2; no committed rule definition | Medium |
| FILE-001 | Modification of selected sensitive system files | Source-dependent future candidate, not a new mandatory v0.1 collector or finalized rule | High |

No candidate proves malicious intent. A v0.1 alert links its one triggering event
and rule identity/condition; evidence aggregation, multi-event relationships and
behavioral timelines remain deferred. Existing privilege/privacy and local kernel
observation limitations are unchanged by the smaller release scope.

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
