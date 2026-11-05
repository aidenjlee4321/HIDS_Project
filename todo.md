# HIDS TODO

Documentation reconciled November 5, 2026. Completed documentation tasks do not
mean source behavior has been researched or functionality implemented. Currently
only documentation and empty directory scaffolding exist. Owner-reported sudo
experiments are documented; raw fixtures and validated mappings remain pending.

## Completed documentation

- [x] Reconcile architecture and repository guidance with detection-only scope.
- [x] Establish ECS 9.5.0 as initial reference, preferring Core/relevant Extended fields.
- [x] Put the proposed schema at [docs/event-schema.md](docs/event-schema.md); retain the old path as a pointer.
- [x] Document [schema research process](docs/schema-design-process.md) and initial coverage matrix.
- [x] Document [evidence-first policy](docs/confidence.md), preserving indicators without confidence scores or automatic labels.
- [x] Update threat model and amend ADR-004, preserving superseded reasoning.
- [x] Document existing-logging constraint, root-only human access, provisional namespace, and unresolved authentication/sudo eligibility.
- [x] Refresh documentation index, links, and requirement/proposal/implementation distinctions.
- [x] Record initial [sudo authentication observations](docs/research/authentication.md) without claiming parser-ready fixtures.
- [x] Establish [broad field discovery](docs/research/field-discovery.md), independent catalog, scoped availability states, and rule-specific importance/sensitivity.
- [x] Establish separate capability-manager, field-analyzer, detection-engine and dashboard responsibilities (unimplemented).

- [x] Clarify native C++ processing versus Python normalized-event receipt/validation, preserving both IPC validation boundaries.
- [x] Establish graceful degradation and lifecycle-wide logging restrictions; mechanisms remain open.
- [x] Preserve raw/native information without forced ECS mapping; leave missing activity-time policy unresolved.
- [x] Reconcile privilege research status, primary pinned ECS references, ADR-002 access policy, and monitoring-versus-remediation recommendations.

## Source and schema research — not completed

- [ ] Study the pinned ECS 9.5.0 Core and relevant Extended field definitions.
- [ ] Repeat reported sudo cases with complete protected records, exact journal keys/types, timestamps and capture commands; inspect intended collector permissions.
- [ ] Investigate Linux Audit availability, existing records, grouping, and read paths without configuration changes.
- [ ] Establish actual visibility under existing logging; document missing sources/fields and unsupported activities.
- [ ] Collect sanitized representative Ubuntu fixtures, including incomplete/duplicate cases.
- [ ] Map authentication and process records to ECS only where source evidence supports them.
- [ ] Update the coverage matrix with findings; distinguish stock and preconfigured test environments.
- [ ] Compare extracted native fields against the catalog, with per-source/event availability evidence; do not treat unmentioned keys as absent.
- [ ] Investigate existing SSH/console records, cached sudo credentials, retries/cancellation, alternate accounts, and cross-source duplicates.
- [ ] Research startup/periodic source-access probes, freshness, gap detection and recovery without logging configuration changes.

## Open design decisions — require explicit resolution

- [ ] Select root-only authentication; decide whether sudo-authorized administrators qualify.
- [ ] Finalize custom namespace only if ECS gaps justify custom fields; `hids.*` remains provisional.
- [ ] Define event contracts, raw-record representation, and schema compatibility strategy.
- [ ] Research missing/unreliable activity timestamps and explicitly decide representation/handling; no invented time or silent collection-time fallback.
- [ ] Select concurrency, source-isolation and supervision mechanisms for established graceful degradation.
- [ ] Determine minimum per-adapter privileges, service identities, and tested hardening.
- [ ] Define IPC socket ownership, acknowledgments, retry/backpressure, checkpoints, and gap reporting.
- [ ] Set retention and disk limits; decide encryption/key management requirements.
- [ ] Finalize rule configuration format (YAML proposed), supported scenarios, and severity defaults.
- [ ] Select build/dependency tooling and production asset serving/packaging details.
- [ ] Define catalog/assessment versions, persistence, sampling bounds, refresh schedules and component placement/interfaces.
- [ ] Finalize rule requirement syntax, missing-evidence/readiness behavior and recovery/replay semantics.
- [ ] Define protected raw-record references and separate existence discovery from value retention/redaction.

## Implementation — all pending; requires a future implementation task

- [ ] Define machine-readable schemas after source validation.
- [ ] Implement the first C++ journald collector/native parsing/normalization and Python normalized-event receipt/contract validation, with validation on both IPC endpoints.
- [ ] Implement reliable transport and SQLite persistence.
- [ ] Implement evidence-preserving rules and correlation with realistic tests.
- [ ] Implement capability discovery and field analysis only after source/access research and explicit implementation authorization.
- [ ] Provide descriptive field/rule limitation reports, including startup reassessment, source changes, gaps and recovery; no overall security percentage.
- [ ] Implement authorized local API/dashboard and security tests after authentication decisions.
- [ ] Demonstrate a complete real-event pipeline and expose collection limitations.
- [ ] Verify graceful degradation: other sources, authorized dashboard/stored-data access, affected-source status, rule limitations and detectable recovery.
- [ ] Ensure installation, startup, discovery and runtime do not change journald/PAM/auditd configuration or Linux Audit rules; HIDS application setup is distinct.

## Stretch goals / future proposals — not initial-release requirements

- [ ] Investigate additional logging/auditing configuration only with separate design and approval.
- [ ] Evaluate additional filesystem monitoring interfaces after the existing-log pipeline.
- [ ] Consider optional AI interpretation with explicit privacy and data-flow design.

Monitoring coverage recommendations are within initial scope; threat remediation
recommendations and automatic remediation are outside initial scope. Accepted
technology choices remain unchanged and require explicit approval for reconsideration.
No automatic remediation. This backlog does not authorize dependencies, host
changes, or implementation during the documentation-only task.
