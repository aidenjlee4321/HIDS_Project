# ADR-007: Minimal v0.1; defer correlation and multi-event evidence

**Status:** Accepted  
**Date:** November 6, 2026  
**Scope definition:** [Release scope](../release-scope.md)

## Context and reasoning

The project has invested considerable effort in architecture and Ubuntu source
research, and now has a narrow native process adapter. It does not yet have a
usable collection-to-dashboard pipeline. Earlier architecture descriptions included
correlation, multi-event evidence and sophisticated analysis alongside initial
features, creating a risk that the first usable product would depend on too many
unfinished components.

A smaller initial feature set reduces implementation complexity and delivers a
complete usable product sooner. Validate real collection, normalization, transport,
receipt validation, persistence, security and dashboard use before introducing
complex analysis. Useful identifiers, native information and provenance can be
preserved without prematurely implementing their future consumers.

## Accepted decision

HIDS v0.1 is a minimal functional single-machine HIDS: cn_proc live lifecycle
(following provisional ADR-006), best-effort `/proc` context, supported existing
authentication/system logs, source-health reporting and graceful degradation;
C++20 native collection/parsing/normalization; Unix domain socket JSON Lines IPC;
Python normalized-event receipt with independent validation and Python-owned
SQLite persistence; simple deterministic individual-event rules; and a root-only
local dashboard with searchable history, basic alerts and individual event details.

Each v0.1 alert must identify its generating rule, explain the matched condition
and be traceable to its one triggering event and available source provenance.
Preserve event identifiers, original types/native information, timestamp meanings
and available process/parent IDs under privacy controls. Do not invent activity
time or finalize speculative schemas merely to anticipate future features.

Defer to v0.2 planning: multi-event relationships/correlation, counting/time-window
and sequence-based detection, authentication/process behavioral sequences,
cross-source correlation, multiple supporting events per alert, aggregation,
evidence relationship management, richer timelines and advanced/context-dependent
behavioral evaluation. v0.2 is a direction, not an implementation commitment or
finalized specification. No correlation graph or multi-event evidence system is
required to ship v0.1.

## Detection boundary

Recognizing one failed authentication event or matching a simple condition on one
process execution belongs in v0.1. Detecting repeated failures, failures followed
by success, or process creation/execution/privilege-change sequences belongs in
v0.2. v0.1 rules cannot inspect other events/history or hide behavioral correlation
inside enrichment or a synthetic normalized event. Source-defined multi-record
parsing, transport deduplication and source-health timing remain operational
responsibilities; they are not permission for multi-event security analysis.

## Consequences and compatibility with existing decisions

- The v0.1 completion gate is a usable, validated end-to-end pipeline with basic
  individual-event rules and protected dashboard access, not an isolated adapter
  or a correlated detection demonstration.
- v0.1 storage needs a traceable individual triggering-event reference; the
  earlier proposed `alert_events` relationship table is a v0.2 design candidate,
  not a v0.1 requirement or approved schema. Exact schemas and IDs remain open.
- Preserve future architectural reasoning as labeled v0.2 plans. Existing roadmap
  phase numbers are engineering steps, not release-version numbers.
- ADR-001–006 are unchanged. Correlation stays within Python's eventual ownership,
  but is deferred from v0.1. C++/Python validation boundaries, Unix sockets/JSON
  Lines, Python-owned SQLite writes, FastAPI, React/TypeScript/Vite, SSE and the
  Debian/systemd direction remain accepted.
- Root-only human security-data access, privilege separation, least privilege,
  local-first storage, ECS 9.5.0 foundations, evidence-first explanations and the
  prohibition on numerical/automatic qualitative confidence scoring remain.
- No automatic remediation, Ubuntu logging/PAM/auditd configuration changes, Audit
  rule changes or mandatory additional collection configuration are introduced.
- v0.1 makes fewer behavioral claims; it does not become comprehensive monitoring
  and cannot claim that one failure proves malicious intent. Missing sources,
  enrichment races, timing limitations and collection gaps must stay visible.

## Open design work and authorization

Select the supported v0.1 normalized/IPC contracts incrementally; resolve activity-
time handling, service identities, root-only authentication, retention/backpressure,
packaging and operational validation using the existing process. v0.2 will require
separate correlation semantics, evidence relationships, storage and resource design.
This accepted scope changes planning, not implementation status. The current task
is documentation-only and does not authorize new application functionality,
dependencies, host changes or Git operations.
