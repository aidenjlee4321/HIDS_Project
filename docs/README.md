# HIDS Documentation

This directory contains the design and technical documentation for the HIDS project.

## Documents

| File | Purpose |
|---|---|
| [architecture.md](architecture.md) | Overall system architecture, components, technology stack, roadmap, and implementation objective |
| [event-schema.md](event-schema.md) | Canonical event structure and normalization conventions |
| [threat-model.md](threat-model.md) | Security objectives, privilege model, trust boundaries, privacy requirements, and known limitations |
| [decisions/](decisions/) | Architectural Decision Records (ADRs) explaining significant design choices |

## Architectural Decision Records

| ADR | Decision |
|---|---|
| [ADR-001](decisions/001-language-and-component-responsibilities.md) | Language and component responsibilities |
| [ADR-002](decisions/002-sqlite-storage.md) | Local persistent storage with SQLite |
| [ADR-003](decisions/003-local-ipc.md) | Local inter-process communication |
| [ADR-004](decisions/004-privilege-separation.md) | Privilege separation |
| [ADR-005](decisions/005-platform-and-interface.md) | Initial platform and user interface |

## Documentation conventions

- `architecture.md` describes what the system is and how its major components fit together.
- `event-schema.md` defines the shared event representation.
- `threat-model.md` describes security assumptions, requirements, and limitations.
- ADRs record why significant decisions were made and what remains unresolved.

The documents represent the initial HIDS v0.1 design baseline. Open questions are intentionally marked rather than silently treated as settled decisions.
