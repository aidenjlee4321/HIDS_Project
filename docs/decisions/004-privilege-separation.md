# ADR-004: Privilege Separation

**Status:** Accepted for initial architecture baseline  
**Date:** November 4, 2026

## Context

The HIDS needs access to operating-system monitoring sources, some of which may require elevated permissions.

At the same time, the application includes an analysis engine, database, and local web API that should not need broad system privileges.

## Decision

Do not run the entire application as root.

- Privileged installation and configuration operations may create service accounts, configure systemd units and audit rules, establish permissions, and install files.
- The C++ collector runs with the minimum permissions required for its monitoring sources.
- The Python backend runs as an unprivileged service account and owns database writes, detection processing, alert generation, and API operations.
- The dashboard must not expose privileged administrative functionality.

Evaluate collector permissions separately for journald, audit, and filesystem monitoring.

## Rationale recorded in the architecture

The security model explicitly requires that the entire application not run as root and that the collector use minimum required permissions.

The backend is designed to operate as an unprivileged service account.

## Consequences

- Installation and service configuration must establish appropriate accounts and permissions.
- Each collector adapter needs a documented permission requirement.
- systemd hardening must be tested against actual monitoring requirements.
- The API must not become a route to privileged system operations.

## Potential systemd hardening options

- `NoNewPrivileges`
- `ProtectSystem`
- `ProtectHome`
- `PrivateTmp`
- `CapabilityBoundingSet`
- `ReadOnlyPaths`
- `ReadWritePaths`

These are candidates to test, not a list to enable blindly.

## Open questions

- Exact service users and groups.
- Exact capabilities or group memberships required by each adapter.
- Whether separate systemd units are needed for collector and backend.
- Exact systemd sandboxing configuration.
