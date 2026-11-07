# HIDS TODO

Documentation reconciled November 5, 2026. Completed documentation tasks do not
mean source behavior has been researched or functionality implemented. Currently
documentation, empty application scaffolding and temporary research utilities exist;
a narrow native C++ process adapter and offline tests are implemented, while
integration remains pending. Owner-reported sudo, SSH and cn_proc experiments are documented; raw fixtures and validated mappings remain pending.

Release planning follows [release scope](docs/release-scope.md) and
[ADR-007](docs/decisions/007-initial-release-scope.md). v0.1 is the minimal complete
pipeline with individual-event rules; v0.2 correlation/evidence work is planned,
not committed. Planning labels below do not authorize implementation in the
current documentation-only task.

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

- [x] Record additional SSH journald observations, sanitized message excerpts, native keys, query overlap and unresolved logout semantics; retain candidate mappings.

- [x] Define accepted v0.1 scope and completion criteria; defer correlation and multi-event evidence to v0.2 while preserving per-event provenance and alert/rule traceability.

- [x] Record owner-reported Ubuntu production-adapter offline validation and prepare the [v0.1 readiness plan](docs/implementation/v0.1-implementation-plan.md) with permission/decision gates; no new application functionality.

- [x] Document the agreed [product experience](docs/product-experience.md): confirmed source subsets before collection, Overview/Activity/alert-feed direction, progressive disclosure and measured lightweight operation.

## Research tooling — separate from HIDS

- [x] Add [temporary inventory/process utilities](scripts/research/README.md) with private timestamped reports, bounded read-only checks and optional scoped sudo reads.
- [x] Check Bash syntax, local simulated report permissions/failure continuation and owned-child cleanup; these are not Ubuntu source tests.
- [ ] Run both scripts as an ordinary user on Ubuntu 26.04; compare optional privileged reads, verify no leftover child, and inspect permissions/diagnostics.
- [ ] Review and sanitize VM reports; collect complete representative source fixtures separately when bounded reports are insufficient.
- [ ] Consider future authentication, filesystem, service, privilege-change and network research scripts; none are implemented now.

- [x] Add a separate single-subscription [C++ process connector experiment](scripts/research/process-connector-test.cpp), with explicit unsubscribe, child-only output and offline ARM64 validation.
- [x] Record the owner-reported Ubuntu ordinary-user cn_proc run: all three child lifecycle types, exact timestamps, ACK/cleanup limits and two diagnostic discontinuities; [research record](docs/research/process-connector.md).
- [x] Review first-observation/per-CPU accounting offline without repeating the kernel experiment; displayed child trace alone yields zero, so the aggregate two remains unattributed.
- [ ] Obtain original sanitized report, compiler identity/version, exact build flags and source/binary digest; preserve provenance without rerunning merely to change diagnostics.

## Source and schema research — not completed

- [ ] Study the pinned ECS 9.5.0 Core and relevant Extended field definitions.
- [ ] Repeat reported sudo cases with complete protected records, exact journal keys/types, timestamps and capture commands; inspect intended collector permissions.
- [ ] Investigate Linux Audit availability, existing records, grouping, and read paths without configuration changes.
- [ ] Establish actual visibility under existing logging; document missing sources/fields and unsupported activities.
- [ ] Collect sanitized representative Ubuntu fixtures, including incomplete/duplicate cases.
- [ ] Map authentication and process records to ECS only where source evidence supports them.
- [ ] Update the coverage matrix with findings; distinguish stock and preconfigured test environments.
- [ ] Compare extracted native fields against the catalog, with per-source/event availability evidence; do not treat unmentioned keys as absent.
- [ ] Capture full sanitized SSH journal exports with exact commands/windows, per-record keys/types and cursor/boot/time values; validate `sshd-session` selection across versions and methods.
- [ ] Distinguish overlapping-query duplicates from paired PAM/SSH failure records and correlated activities; validate attempt boundaries with retries/failure followed by success.
- [ ] Research the SSH logout error and normal closure evidence; compare corresponding existing Audit records and distinct systemd/Audit session identities.
- [ ] Investigate console/other login paths, SSH methods/invalid users/disconnects, cached sudo credentials, cancellation, alternate accounts and cross-source duplicates.
- [ ] Research metadata/non-collecting startup probes and periodic access freshness; actual field samples/subscriptions only after confirmed selection or separately authorized research. Keep gap/recovery evidence distinct without logging changes.

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
- [ ] Resolve recommendation eligibility, confirmation persistence, draft/apply/retry and boot-resume policy without unconfirmed collection (readiness D-14).
- [ ] Review proposed severity labels/mapping, alert-feed recency clock/tie-break and Sources navigation without finalizing event/IPC/DB contracts.
- [ ] Define benchmark protocol and set acceptance thresholds after prototype measurement, with no invented CPU/memory budgets (D-15).

## v0.1 implementation — native adapter exists; complete pipeline pending

- [x] Authorize and implement a narrow C++ cn_proc adapter/native parser with bounded polling, explicit cleanup, source status/diagnostics and offline tests; [adapter scope](collector/README.md).
- [x] Record successful Ubuntu 26.04.1 / kernel 7.0.0-42-generic / aarch64 / GCC 15.2.0 strict compilation, both offline unit suites and complete production link smoke test; [validation evidence](docs/validation/collector-ubuntu-validation.md).
- [ ] Validate live production connector operation, intended service-account access, shutdown and runtime reliability under a separately approved bounded plan; neither offline tests nor the research experiment closes this gate.
- [ ] Review the [readiness decision register](docs/implementation/v0.1-implementation-plan.md#decision-register) and approve the constrained fixture pilot before production envelope/IPC/SQLite integration.
- [ ] Design best-effort `/proc` enrichment, process/boot identity and privacy policy; no automatic collection of arguments or environments.
- [ ] Resolve shared normalization/IPC contracts and integration after the native milestone.

- [ ] Define machine-readable schemas after source validation.
- [ ] Implement the first C++ journald collector/native parsing/normalization and Python normalized-event receipt/contract validation, with validation on both IPC endpoints.
- [ ] Implement reliable transport and SQLite persistence.
- [ ] Implement simple deterministic individual-event rules/basic categorization with positive, negative and incomplete tests; no event counts/windows/sequences.
- [ ] Link each v0.1 alert to its one triggering event and generating rule; explain the matched condition, provenance and limitations without a multi-event evidence manager.
- [ ] Implement separate metadata-only discovery, availability assessment, explained usable-source recommendations and individual draft selection/confirmation under root-only authorization; no payload sampling or collector initialization before confirmation.
- [ ] Enforce selected-only collector start in backend/C++ orchestration, test failed initialization/subset operation and expose actual runtime status separately from static support/configuration.
- [ ] Add observed-field analysis only after confirmation or separately authorized research; preserve unknown/unverified fields before collection.
- [ ] Provide descriptive field/rule limitation reports, including startup reassessment, source changes, gaps and recovery; no overall security percentage.
- [ ] Implement the root-authorized Overview landing and proposed Alerts/Activity/Sources/System Health/Settings views; use progressive disclosure and keep ordinary events out of the alert feed.
- [ ] Test severity-first, recency-second alert order and event/rule/condition links after final label/clock decisions; no confidence/suspiciousness score.
- [ ] Demonstrate a complete real-event pipeline and expose collection limitations.
- [ ] Verify graceful degradation: other sources, authorized dashboard/stored-data access, affected-source status, rule limitations and detectable recovery.
- [ ] Ensure installation, startup, discovery and runtime do not change journald/PAM/auditd configuration or Linux Audit rules; HIDS application setup is distinct.

- [ ] Benchmark idle CPU, typical CPU, memory, disk growth, event bursts and slow receiver/database behavior; record conditions/results, then approve and validate actual acceptance thresholds before v0.1 release. Offline/simulated bursts first; no implicit connector stress test.
- [ ] Validate all [v0.1 release completion criteria](docs/release-scope.md#v01-completion-criteria), including root-only search/detail/basic alerts and source health; no criterion depends on correlation.

## v0.2 planning — deferred, not an implementation commitment

- [ ] Separately design multi-event relationships, time windows, repeated-failure/success authentication sequences, cross-source and process/behavioral correlation.
- [ ] Design multiple supporting events per alert, aggregation and evidence relationship management; the historical `alert_events` table remains a candidate, not an approved schema.
- [ ] Plan richer investigation timelines/behavioral explanations and advanced/context-dependent evaluation with explicit timing/gap/missing-data semantics.
- [ ] Review v0.2 scope, contracts, bounded storage/retention and candidate acceptance tests before implementation; preserve v0.1 identifiers and provenance without building graphs/aggregation early.

## Stretch goals / future proposals — separate from v0.1 and v0.2 planning

- [ ] Investigate additional logging/auditing configuration only with separate design and approval.
- [ ] Evaluate additional filesystem monitoring interfaces after the existing-log pipeline.
- [ ] Consider optional AI interpretation with explicit privacy and data-flow design.

Monitoring coverage recommendations are within initial scope; threat remediation
recommendations and automatic remediation are outside initial scope. Accepted
technology choices remain unchanged and require explicit approval for reconsideration.
No automatic remediation. This backlog does not itself authorize dependency installation, host changes or
new implementation or benchmarking during the current product-direction documentation task. The native adapter
was previously authorized; future v0.1 pipeline work needs a subsequent implementation
task, and v0.2 remains a planned direction requiring separate design/approval.
