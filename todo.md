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

## M3 offline build and production decisions

- [x] Build and test offline reconstruction, provisional RAW lexical checks, and EOE-closed EXECVE completeness. See [M3 build and verification](tests/integration/M3-README.md).
- [x] Verify the original offline reconstruction build on Ubuntu AArch64, with and without sanitizers.
- [x] Validate the synthetic execution fixture end to end and produce a sanitized internal event on macOS.
- [x] Rerun the expanded semantic fixture suite on Ubuntu AArch64 with and without sanitizers.
- [x] Smoke-test the installed Ubuntu libauparse runtime with synthetic BUFFER input.
- [x] Exercise offline durable admission, interleaved checkpoint advancement, restart suppression, and transaction rollback in SQLite.
- [x] Commit sanitized fixture executions atomically with their checkpoint and verify lost-ACK retry after reopen.
- [x] Exercise the linked C++ libauparse adapter with synthetic fixtures on Ubuntu AArch64.
- [x] Connect the C++ fixture producer to Python over private pipes and kill the producer before and after final commit.
- [ ] Implement the production Unix socket protocol, bounded progress tracking, lease and generation checks. Exercise actual backend termination, rotation, and live reader acceptance.
- [x] Observe a scoped native Ubuntu execution with fragmented EXECVE and restore the VM Audit configuration.
- [x] Resolve the live source/completion conflict. The owner approved an outbound auditd plugin and retained EOE-only completion.
- [x] Add bounded framing for auditd string-mode plugin input and test split/coalesced reads and incomplete input.
- [x] Verify plugin framing, live EOE delivery and a non-root probe on Ubuntu. Require the observed EOE delimiter in the plugin profile.
- [x] Verify a bounded Linux 2 auditd-to-C++-to-authenticated-named-socket-to-SQLite execution, including fragmented EXECVE and distinct non-root reader/backend identities. See [M3 validation](tests/integration/M3-README.md#ubuntu-named-socket-and-live-delivery).
- [x] Add durable M3 activation and restart state, a root control/data service loop, launcher/current-tail gate and source systemd artifacts. Validate 31 local and Ubuntu Python tests and 17 linked native sanitizer groups on Ubuntu.
- [x] Validate the installed runtime on Linux 2 with systemd, real root control/service identities, pre-activation exclusion, live revocation, backend SIGKILL/restart, storage contention, source-failure reports and configured capacity limits. See [installed-runtime acceptance](tests/integration/M3-README.md#installed-runtime-ubuntu-acceptance).
- [x] Compare quiet-source EOE delivery after clean Audit startup versus plugin removal/re-addition by reload. Reproduce the Audit 4.1.2 one-record delay with an independent metadata observer, verify durable timeout/gap reporting and no late acceptance, and preserve EOE-only completion. See [quiet-source evidence](tests/integration/M3-README.md#quiet-source-delivery-and-dispatcher-reload-regression).
- [x] Implement separate monotonic inactivity/lifetime checks and nested intentional-pause accounting; freeze both during production durable admission/finalization waits. Exact thresholds remain provisional.
- [x] Add atomic per-event timeout evidence/rejection, durable late-position suppression, independent event continuation and safe native payload retirement behind durable progress. Verify 35 Python tests, 21 native sanitizer groups, complete installed-runtime acceptance and paired real-source quiet probes. Known incomplete/late evidence survives revocation/reopen; no resurrection or automatic tombstone deletion.
- [x] Run 4,096-execution full-speed and five-minute paced installed workloads with exact identity/position/frontier checks and measured memory/database growth. Exercise 32 real bounded SQLite writer locks over 16.744/17.001 wall seconds while an incomplete A and independent B events remain correctly handled. See [load evidence](tests/integration/M3-README.md#per-event-timeouts-and-sustained-workloads). Multi-hour/mixed real-host workloads and release thresholds remain open.
- [x] Implement and validate the owner-approved separate privileged health checker: scoped health-only IPC, passive kernel/dispatcher snapshots, bounded durable baselines/incidents, freshness/reset/gap handling, schema migration, failure isolation and backend-bound lifecycle. Verify 46 Python tests, native metadata sanitizers, actual unit isolation, fresh/stale/malformed/symlink cases, real periodic reports, source continuity during health failures, and checker shutdown on backend SIGKILL. See [health acceptance](tests/integration/M3-README.md#installed-health-checker-acceptance). Kernel samples work on the current host; dispatcher freshness depends on externally published reports and remains unknown with the restored default report_interval=0.
- [x] Implement bounded live resource discard at the provisional 16 MiB/event and 32 MiB aggregate limits, durable incident-before-release, independent event retirement and unknown historical counters. Validate actual Ubuntu limits, oldest-blocker fallback, EOE/late suppression and incident-write failure; 52 Python tests and 24 native sanitizer groups pass. See [resource acceptance](tests/integration/M3-README.md#installed-resource-pressure-acceptance). Release thresholds and broader crash/host workload evidence remain open.
- [x] Add and run 55 deterministic actual SIGKILL cases locally and on Ubuntu across registration/EOE, execution/rejection, timeout/resource causes, late suppression, activation orphan files and control/event reconciliation. Verify exact rollback/committed state, independent B preservation, no resurrection, lost-ACK deduplication and fresh authorization after restart. See [crash acceptance](tests/integration/M3-README.md#deterministic-process-crash-acceptance). Power-loss/device faults and broader native/source injection remain separate.
- [x] Exercise actual Linux 2 reboots with committed B/unresolved A and kernel-health history; preserve evidence, interrupt A, require fresh generation/lease, and commit C after explicit authorization. Fix persistent tmpfiles provisioning, prove automatic directory creation on a second reboot, and fix unknown historical health age for overlapping boot uptimes. Verify 53 Python tests and installed checker failure/lifecycle isolation. See [reboot acceptance](tests/integration/M3-README.md#reboot-provisioning-and-recovery).
- [x] Add 124 native-profile boundary cases and actual AArch64 UAPI assertions; run them linked to Ubuntu libauparse with sanitizers. Fix typed allocation failure handling and parser-unavailability interruption; verify 124 allocation cuts, 11 API faults, both installed native gap paths, 54 Python tests, 24 linked native groups and full live/capacity regression. Record target library/header provenance and remaining narrow-grammar/distribution limits. See [parser acceptance](tests/integration/M3-README.md#native-contract-boundaries-and-parser-failure-acceptance).
- [x] Review current M3 authorization, privilege boundaries, durability/replay and test/documentation claims. Fix interrupted replay EOE integrity; pass 55 M3 tests and the 55-case Ubuntu crash matrix. Verify a pinned-reader WAL growth gap and record missing per-event observation/receipt/persistence timestamps, explicit architecture provenance and ordinary rejection causes. Reconcile stale M1-only guidance without weakening existing approvals. See [focused review](tests/integration/M3-README.md#focused-m3-build-review).
- [ ] Verify native RAW field coverage, sentinels, encodings, and libauparse behavior before emitting normalized M3 events.
- [x] Consolidate the [canonical M3 specification/register](docs/implementation/m3-linux-audit-spec.md#11-owner-decision-register) using **Owner-approved**, **Provisional**, **Evidence-dependent** and **Future goal**, without implementation authorization.
- [x] Record **Owner-approved** RAW local files/native AArch64 execution, root activation/current-tail/no-backfill intervals, EOE-only completion, absent/incomplete EXECVE rejection, required identities/GID omission, strict fields and fresh BUFFER/temporary truncation.
- [x] Record **Owner-approved** exe/comm byte-preserving Base64, no argc/argv or CWD/PATH/PROCTITLE contents, presence/count metadata, additive M3 protocol/database routing, conservative source-position scanning, atomic Python persistence, rename rotation and no automatic deletion/cleanup.
- [x] Supersede earlier assembly candidates with **Provisional** owner-approved 16 MiB/event and 32 MiB aggregate ceilings; exe/comm decoded-byte ceilings 4096/256, tuning pending. Keep other approved transport bounds explicit.
- [ ] **Evidence-dependent:** actual RAW coverage, non-root read permissions, package/header/ABI/license, Event metadata, fragment/encoding grammar, ranges/sentinels and remaining native/parser/diagnostic limits.
- [x] Document the [owner-approved state-machine addendum](docs/implementation/m3-linux-audit-spec.md#12-owner-approved-evidence-and-state-machine-addendum): independent collection/event lifecycles, EOE-only completeness, interruption discard/report, durable sanitized admission, bounded suppression, generation transitions and resolved-range/frontier transactions.
- [ ] **Evidence-dependent:** exact progress-ledger batching/registration/ACK ordering, suppression/range schema and bounds, complete-but-uncommitted reconciliation, safe oversize/aggregate continuation and failure-injection proof before implementation. Never reconstruct interrupted events into acceptance.
- [ ] Run the separately authorized [M3 state-machine acceptance plan](docs/implementation/v0.1-implementation-plan.md#m3-state-machine-acceptance-plan--future-tests-only) only after implementation/test authorization: crash at every durable boundary, interrupted suppression, independent B preservation, physical replay versus late records, paused monotonic deadlines, resource fallback and storage/core isolation.
- [ ] **Evidence-dependent:** actual service/endpoint/filesystem controls, additive routing/control/configuration and SQLite schema/migrations, same-activation reset/reboot recovery, resource/storage thresholds and independent health evidence.
- [ ] **Future goal:** incomplete EXECVE, separate failed-execution representation, PROCTITLE completion, validated-discard unknown fields, compressed archives and a separately reviewed fallback M3 worker if justified.
- [ ] **Future goal:** exe/comm encryption/key management and independent category retention/collection controls. Exact toggle policy and later archival remain deferred; initial privacy/no-automatic-deletion rules continue.
- [x] Record **Owner-approved** original Audit source preservation and no automatic source deletion/cleanup/overwrite; durable full-generation coverage and ranges/frontiers establish processing, never deletion permission. See [source preservation](docs/implementation/m3-linux-audit-spec.md#64-original-source-evidence-and-retirement-eligibility).
- [ ] **Evidence-dependent:** verify owner-observed finite Auditd ROTATE retention and external cleanup, safest supported preservation configuration, terminal-boundary/full-generation coverage without backfill, and source/database capacity and suspension thresholds. No configuration changes authorized.
- [ ] After separate test authorization, verify multi-rotation lag/unprocessed preservation, interruption blocking retirement until durable resolution, restart identity, missing-generation gaps and exhaustion without deletion.
- [ ] **Future goal:** verified original-generation archival handoff with complete coverage, integrity/provenance, durable retrieval and recoverable state; failed/incomplete/corrupt archives cannot qualify. Exact archive/privacy and any later cleanup policy need separate review/approval.

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
- [x] Owner approved constrained synthetic M1 P-01–08 on November 7, 2026; broader production decisions remain in the [readiness register](docs/implementation/v0.1-implementation-plan.md#decision-register).
- [ ] Complete [M1 acceptance](docs/validation/m1-pilot-validation.md): synthetic implementation and local boundary tests exist; actual Ubuntu two-process/failure-suite and retrieval evidence remain pending.
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
No automatic remediation. This backlog is not execution authorization. The owner's
later M3 implementation, testing and Linux 2 VM approvals supersede the historical
M1-only task restriction; consult [current repository guidance](AGENTS.md#working-constraints)
and the active user instructions. Preserve existing approvals and limits. New
fundamental architecture/product decisions and specific commits/pushes still need
owner approval; future milestone entries do not grant additional scope by themselves.


### M3 review continuation (November 11)

- [x] Enforce EOE classification during interrupted-position replay.
- [x] Add proactive state/WAL/free-space admission, non-deleting checkpoints,
  recovery reserves and readable status-only degraded startup.
- [x] Persist separate collector observation/backend receipt/persistence-start
  clocks and native architecture/profile without guessing historical values.
- [x] Atomically retain closed sanitized rejection reasons and bounded root diagnostics.
- [ ] Approve broader release workloads/thresholds, distribution and remaining
  milestone gates; the scoped checks above do not close these requirements.

Executed evidence and compatibility details are in the
[M3 continuation record](tests/integration/M3-README.md#storage-admission-and-event-metadata-continuation).


### Development-efficiency workflow

Current task details and standing approvals: [session handoff](docs/current-state.md).
Historical M3 evidence remains chronological. Broad unchecked research/release items
above refer to remaining coverage, not a reversal of later scoped implementation
and acceptance results; use the current summary to distinguish them.

- [x] Add compact current checkpoint/authority/VM handoff.
- [x] Reuse verified snapshots and include timer plus the explicit sanitized fixture.
- [x] Add VM preflight, dependency-aware matched build/deploy and cleanup runner.
- [x] Define test tiers, private structured reports, bounded failure output and binary cache.
- [x] Index current documentation separately from chronological evidence.
- [x] Complete actual safe-failure/retry and uncached/cached full live VM pilot measurements;
  all required phases passed twice, cleanup verified, six cached builds avoided.
  See [workflow acceptance](docs/validation/m3-workflow-validation.md).

Do not infer product-release sign-off from completion of these tooling tasks.
