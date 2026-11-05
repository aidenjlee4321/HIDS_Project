# ADR-002: Local Persistent Storage with SQLite

**Status:** Accepted for initial architecture baseline  
**Date:** November 4, 2026

## Context

The HIDS is intended for an individual's computer and should store collected information locally by default.

The application needs persistent storage for normalized events, alerts, alert/event relationships, detection rules, settings, and collector state.

## Decision

Use SQLite as the initial persistent database.

The Python backend owns database writes. The C++ collector sends events to Python rather than independently modifying the database.

Enable SQLite Write-Ahead Logging (WAL), index frequently queried fields, implement event deduplication and configurable retention, limit database growth, preserve relevant source metadata, and use database migrations when the schema changes.

## Rationale recorded in the architecture

SQLite provides local persistent storage and supports the local-first design.

The Python backend is the single owner of database writes.

## Consequences

- The backend receives normalized events from C++ and independently validates their contracts before persistence; this does not assign native source collection to Python.
- Database schema changes need migrations.
- Retention and disk usage limits need implementation.
- Direct database access must be restricted to the designated application service
  account and root; ordinary users must not read or write database files. Service
  access is separate from human dashboard authorization, as in the
  [threat model](../threat-model.md#7-data-confidentiality-and-access-control).

## Clarification — November 5, 2026

The earlier consequence said access was restricted to "the application account."
The current wording explicitly includes root and distinguishes human authorization
from service-account access. Python-owned writes and the local-storage rationale
are unchanged.

## Open questions

- Initial retention period.
- Disk usage limits and behavior when limits are reached.
- Exact indexes and migration strategy.
