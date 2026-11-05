# ADR-004: Privilege Separation

**Status:** Accepted; installation-time audit-rule permission partially superseded November 5, 2026  
**Date:** November 4, 2026

## Context

The HIDS needs access to operating-system monitoring sources, some of which may require elevated permissions.

At the same time, the application includes an analysis engine, database, and local web API that should not need broad system privileges.

## Amendment — November 5, 2026

The owner's clarified initial-release scope supersedes the original permission to
configure audit rules during installation. Throughout the initial release, HIDS must not modify journald configuration, PAM configuration, auditd configuration, or Linux Audit rules. This applies during installation, startup, discovery, and runtime. Use existing Ubuntu logging and auditing and communicate visibility limits. Additional logging configuration is a stretch goal requiring separate design and approval.

Privilege separation remains accepted: root-only human access to the initial
dashboard and security data is distinct from service privileges. Python remains
an unprivileged service account; collector permissions are evaluated per adapter.
Authentication and whether sudo-authorized administrators qualify remain open.

## Decision (current)

Do not run the entire application as root.

- Privileged installation and configuration operations may create service accounts, configure HIDS systemd units, establish permissions, and install files.
- The C++ collector runs with the minimum permissions required for its monitoring sources.
- The Python backend runs as an unprivileged service account and owns database writes, detection processing, alert generation, and API operations.
- The dashboard must not expose privileged administrative functionality.

Evaluate collector permissions separately for journald, audit, and filesystem monitoring. Permitted setup of HIDS application files, accounts, permissions and its own service units does not authorize changes to Ubuntu logging configuration.

## Historical record (superseded clause)

The November 4 baseline permitted privileged installation to "configure systemd
units and audit rules." Only the audit-rule permission is superseded for the
initial release. The original reasoning was that privileged installation can
establish monitoring access without making every running component root. That
reasoning remains valid for application accounts, units, and file permissions;
it does not authorize changes to logging infrastructure.

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
