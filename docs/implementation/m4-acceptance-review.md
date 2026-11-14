# M4 bounded backend acceptance review

Status: evidence review for the implemented scope, not a declaration that the
entire M4 roadmap, unattended operation or release is complete. Date: 2026-11-12.
Preserve the owner's existing rule/schema/storage/activation approvals.

## Current delivered behavior

Committed M3 Audit execution → independent Python validation → separate protected
M4 storage → one explicitly selected immutable one-event rule → explained
informational finding. Live collection authorization, C++ normalization, source
scope/profile, clocks and root-only human-data access remain separate boundaries.
The first supported condition is only the approved exact dash/euid-0/success
watchpoint. It does not establish maliciousness, ATT&CK coverage or a generic
security-rule catalog. Default rule activation remains disabled.

## Acceptance coverage and its limits

| Handoff requirement | Executed evidence | Boundary still preserved |
|---|---|---|
| Selected binding/schema/provenance | Closed source validation, root config negatives and exact generation/source scope | Unknown/replaced/unavailable input refuses; no invented history |
| Late commits, pagination, repeat/restart | A after B, durable sweeps, one-event pages and actual sandbox repeat starts | No historical auto-import or temporal ordering claim |
| Rejected/incomplete/unknown input | Independent component cases and supported metadata/profile gates | Unknown evidence is not a clean result or guessed attribution |
| Identity and clocks | Exact native scope/payload/metadata equality; reused native ID across intervals remains distinct | No global ECS/clock contract inferred |
| Import/finding atomicity | Actual SIGKILL before/after both commits; genuine filesystem FULL at both writes; pending retry | Selected crash/VFS paths, not every power-loss/device failure |
| Least privilege | Actual owner identity, read-only source, hidden sockets, root-owned config/rule and no added capabilities | Source privileges and root-only human access are unchanged |
| Contention/resource admission | Installed Service/peer IPC, external reader, destination lock, continuous idle/burst, WAL/state refusal, backup accounting | Short observations and tested budgets are not release thresholds |
| Failed-binding isolation | Actual two-binding sandbox, per-binding backoff, healthy pagination, access restoration | Production root entry stays single-binding/bounded |
| Protected storage/live scope | Owner-approved DDL/migration/backup and controlled real import/finding | No downgrade, deletion, default enablement or unattended service |

Evidence: [first rule](../validation/m4-first-rule-acceptance.md),
[recovery](../validation/m4-recovery-contention.md),
[installed IPC](../validation/m4-ipc-contention.md),
[continuous loop](../validation/m4-continuous-polling.md),
[filesystem failures](../validation/m4-filesystem-failures.md),
[WAL/state fix](../validation/m4-budget-admission.md) and
[binding isolation](../validation/m4-binding-isolation.md).
Latest complete component scope: 96 M4 + 87 M3 tests and demo on Ubuntu.

## Real retained state

Linux 2 UUID `46330e53-4a53-4a94-b9d4-0adefd192ab7` retains 357 M3 SQLite files.
Real M4 is schema v2: 19 events, one rule, three evaluations (one matched/two
no_match), one non-demo informational finding, and 16 old events unevaluated.
The protected v1 backup retains the original 16 rows unchanged. Installed 29
artifact hashes and source/Audit preservation checks passed. No current M4 worker
or host trial config remains. No recreation or data deletion is needed.

## Work that does not follow automatically from this review

- Unattended monitoring, automatic source selection or broader rule activation.
- Additional rule meanings, ATT&CK labels or a finalized severity taxonomy.
- Retention/expiry, broader quotas/VFS behavior or resource-release thresholds.
- Root-only HTTP authentication/session design, API/UI, packaging and distribution.
- CIS assessment scope or a change to accepted collection/privacy architecture.

The next useful product integration is a protected read-only API/dashboard view of
already stored events/findings and honest pending/unavailable state. The existing
D-12 register requires owner decisions on human eligibility and authentication
before exposing that data. The owner has now accepted
[explicit root/sudo eligibility](dashboard-access-eligibility-review.md). The
[concrete session mechanism](dashboard-session-mechanism-review.md) was separately
approved and its synthetic-only pilot [passed](../validation/dashboard-session-pilot.md).
M4 evidence alone does not approve real-data HTTP routes or production origin trust.
The dashboard should use an ordinary browser; backend remains unprivileged and
source confirmation remains a separate action that authentication cannot bypass.


## Subsequent D-12c integration

Owner D-12c separately accepted the exact protected stored-history contract. That
slice is implemented and its bounded synthetic/real Linux 2 trials passed:
[history acceptance](../validation/m4-history-view-acceptance.md). Root/sudo sessions,
unprivileged service/browser, direct-leaf HTTPS and a finite read-only selection
expose 19 retained events/one informational finding, keeping the old 16 unevaluated.
All activations are stopped and baseline state is preserved. This supersedes the
next-step wording above for that slice only; it does not grant collection, broader
rules, CA trust, unattended deployment or complete the product/release gates.
