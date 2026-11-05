# HIDS Documentation

This directory contains the design and technical documentation for the HIDS project.

## Documents

| File | Purpose |
|---|---|
| [architecture.md](architecture.md) | Overall system architecture, components, technology stack, roadmap, and implementation objective |
| [event-schema.md](event-schema.md) | Proposed canonical event structure and normalization conventions; ECS reference is established, detailed contract is not |
| [schema-design-process.md](schema-design-process.md) | Research workflow, event-family research matrix, and schema evolution |
| [research/field-discovery.md](research/field-discovery.md) | Broad candidate catalog, capability/field-discovery responsibilities, availability states, rule requirements and descriptive coverage |
| [research/authentication.md](research/authentication.md) | Owner-reported sudo experiments; observations and candidate ECS mappings, not raw fixtures or implemented coverage |
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

## Documentation conventions

- `architecture.md` describes what the system is and how its major components fit together.
- `event-schema.md` proposes the shared event representation; exact fields and `hids.*` remain provisional.
- `threat-model.md` describes security assumptions, requirements, and limitations.
- ADRs record why significant decisions were made and what remains unresolved.

## Current status and decision boundaries

As of November 5, 2026, only documentation and directory scaffolding exist.
No HIDS functionality, build setup, machine-readable event schema, or executable
tests are implemented. Initial sudo observations are documented; complete raw
fixtures, validated mappings, and comprehensive event-family research remain pending.

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
correlation, security analysis and SQLite writes. Both IPC endpoints validate
appropriately; Python ingestion does not mean native OS collection. Native records
need not map immediately into ECS. Monitoring coverage recommendations are within
scope; threat remediation recommendations are outside initial scope. Additional
logging configuration requires separate design and approval; HIDS files and its
own services are distinct from Ubuntu logging configuration. Accepted technology
choices above require explicit approval before reconsideration.

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
