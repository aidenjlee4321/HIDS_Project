# HIDS v0.1 product experience

**Status:** Accepted product direction; navigation/severity labels are proposals  
**Recorded:** November 7, 2026  
**Scope:** Intended v0.1 experience, not implemented functionality

## Product vision and access boundary

HIDS should be a lightweight, locally operated host intrusion detection system
that makes security monitoring accessible to ordinary computer users. A person
should be able to install HIDS, select available monitoring sources and operate
it without understanding Linux logging infrastructure. Plain explanations should
help them understand what was observed and what monitoring cannot establish.

Accessible operation describes usability, not broader account eligibility.
Root-only human dashboard and security-data access remain required. First-run
results, configuration, source diagnostics and history are security data protected
by backend authorization. An ordinary browser need not run as root; Python stays
unprivileged and C++ source permissions remain individually justified. Root-only
authorization now includes an explicit UID-0 HIDS action per new session,
including OS-authorized sudo (owner D-12a, November 12, 2026). Group membership
alone grants nothing. The [session mechanism](implementation/dashboard-session-mechanism-review.md)
is accepted for a synthetic-only pilot, with
[bounded acceptance](validation/dashboard-session-pilot.md). D-12c subsequently
accepted the [bounded protected stored-history view](validation/m4-history-view-acceptance.md).
Setup/control scopes and production origin/lifecycle remain separate gates;
localhost alone is not authentication. [D-14a](implementation/first-run-control-review.md)
is now accepted: remember choices, fresh root activation after collection-runtime
restart, browser-staged drafts/root CLI control and stop before held-choice edits.
[Bounded implementation acceptance](validation/first-run-acceptance.md) passed;
that trial does not complete every source or the whole first-run product.

The accepted [release scope](release-scope.md) and
[ADR-007](decisions/007-initial-release-scope.md) remain in force: v0.1 has simple
individual-event rules and one triggering event per alert; v0.2 correlation and
multi-event evidence are not added by this product direction. The existing native
adapter/offline tests are not a first-run workflow or a working dashboard.

## First-run experience

After the user satisfies the chosen root-only authorization policy, the intended
flow is:

1. Perform **read-only discovery** of recognized monitoring sources.
2. Assess availability, permissions under the intended service identity, documented
   capabilities and potentially useful fields, with explicit evidence boundaries.
3. Present results in plain language, with details available when requested.
4. Preselect sources that are recommended and usable according to the available
   preflight evidence; make clear that runtime functionality is not yet demonstrated.
5. Explain each recommendation, useful information it could provide, privacy/
   permission considerations and known limitations.
6. Identify unavailable, partially available, unsupported and unverified sources
   separately. A failed permission check is not proof of unsupported functionality.
7. Allow individual HIDS sources to be enabled or disabled in a **draft selection**.
8. Have the user review and explicitly confirm the selection.
9. Initialize only the confirmed selected collectors.
10. Report their actual initialization and runtime status, including failures,
    unconfirmed subscriptions, observed delivery and any incomplete intervals.

No HIDS security-event collection begins before confirmation. Preselected is not
running, confirmed selection is not successful initialization, and initialized is
not proven delivery. A selected source may fail to initialize; keep that failure
visible and allow other functioning confirmed sources to operate. Users may choose
a subset of available sources without an all-or-nothing setup requirement. If no
source is selected, show that monitoring is not collecting; retain authorized
configuration/health/history access rather than displaying a healthy verdict.

### Pre-confirmation discovery versus event sampling

Read-only does not mean consent-free collection: reading an existing journal's
messages is still security-event collection even though it changes no OS settings.
The pre-confirmation pass is limited to recognized-source metadata, existing
configuration/capability information and non-collecting access checks. It must not
open a live subscription, initialize an event reader, scan security-event payloads,
or inspect unrelated per-process arguments/context to learn which fields exist.
cn_proc LISTEN and live receipt occur only after confirmation.

Before confirmation, useful-field information can be documented candidate meanings
or explicitly scoped prior authorized evidence, labeled with provenance/freshness.
Uninspected fields remain unverified/Unknown; do not label them Observed from a
build option or header. Current record-based field assessment follows confirmation
for selected sources, or a separate explicit research authorization outside first
run. A source that needs initialization to prove usability must say so rather
than being silently probed. Existing research observations do not prove access
for a new service identity.

Recommendation/preselection means preflight evidence indicates usable information
without a known blocking condition; it is not a guarantee of runtime success or
comprehensive coverage. If access cannot be established, explain the uncertainty
instead of claiming the source usable. Partially usable sources need a concrete
explanation of which portion is accessible, what remains unverified and why the
usable portion is recommended. Detailed eligibility rules remain a design question;
do not invent a universal source ranking or coverage percentage.

### What source selection changes

Selections control **HIDS collection only**. They do not enable auditd, change
journald/PAM/auditd configuration, create Audit rules, change kernel settings,
install missing packages, grant privileges or modify OS logging. Monitoring
limitations are explained, not silently repaired. Selecting a source does not
authorize changing its required OS configuration or escalating privileges.

The confirmation gate must be enforced by the backend and collector orchestration,
not just a disabled frontend button. Unconfirmed, unselected or newly discovered
sources cannot start because of a crafted API call, a UI default or a permission
change. Application-owned configuration may record confirmed choices once its
format/access controls are approved. Consent persistence across restart, later
edit/apply behavior and retry handling remain unresolved; installation/first launch
cannot assume an initial confirmation. No policy may silently expand collection
beyond confirmed choices. A prior confirmed configuration is distinct from the
current user's unconfirmed draft.

## Central security console

The default landing page is **Overview**, designed as an approachable security
console rather than a wall of diagnostics. Its central alert feed is ordered by
**severity first, then recency within the same severity**. Severity describes
potential impact, not certainty that activity is malicious.

Proposed ordered severity bands:

| Display band, highest first | Status |
|---|---|
| Critical / Emergency | Proposed top-band label; final wording remains open |
| High | Proposed |
| Moderate | Proposed |
| Low | Proposed |
| Informational | Proposed |

These are proposed display categories, not finalized rule severities, numerical
values, ECS mappings or a suspiciousness/confidence score. Historical example
labels such as Medium are not silently remapped. Final naming/mapping and exact
rule assignments require review. No automatic numerical or qualitative confidence
assessment is introduced.

The recency clock and stable tie-break must be chosen explicitly. Alert creation
observation time is a candidate for alert-feed recency; activity time is separate
and may be absent or monotonic. Do not invent activity time or silently use another
clock as though it were activity time. The UI must label the clock used and disclose
missing values; exact timestamp/sort contracts remain unresolved.

Ordinary collected events belong in **Activity**, not automatically in the alert
feed. An alert requires an approved deterministic individual-event rule finding
and must identify its **triggering event, detection rule and matched condition**.
A source becoming unavailable or a slow receiver also needs an operational notice
in Sources/System Health; that notice need not masquerade as a security alert.
No threshold across events, behavioral sequence, cross-source correlation or
multi-event supporting evidence is required to explain a v0.1 alert.

## Proposed navigation and progressive disclosure

| Navigation | Intended purpose |
|---|---|
| Overview | Default landing page, severity/recency alert feed and concise monitoring-status summary |
| Alerts | Basic security alert list/detail, generating rule and direct link to one triggering event |
| Activity | Searchable/filterable collected-event history and individual event details; process/authentication are filters or details, not required top-level consoles |
| Sources | First-run recommendations, source selection/confirmation, limitations and selected-versus-runtime status |
| System Health | Collection interruptions, access errors, backpressure, receiver/database health and assessment freshness |
| Settings | HIDS-owned preferences/configuration and retention choices when approved; no general-purpose OS administration |

This navigation is proposed, not a finalized route/component layout. Put concise
plain-language explanations first. Reveal native fields, source identities, errno,
per-CPU sequences and detailed diagnostics through authenticated detail views.
Missing-data/runtime warnings must remain visible without forcing users to inspect
raw records. Progressive disclosure cannot hide essential failures or weaken
backend authorization on technical endpoints, status or SSE.

## Lightweight operation and benchmark requirement

Resource efficiency is an explicit v0.1 requirement, not an existing measured
property. Prefer event-driven collection and waiting, bounded queues/memory/work,
incremental log retrieval with appropriate source progress, efficient bounded
Python-owned SQLite writes, controlled retention/disk growth, graceful backpressure
and timely source/transport/storage health reporting. Do not poll or rescan entire
logs to make the UI appear live. Disabled/unconfirmed collectors must not perform
background event reads.

v0.1 must be benchmarked for:

| Measurement | Conditions to record |
|---|---|
| Idle CPU usage | Installed service with no active collection and confirmed selected sources under quiet input, distinguished clearly |
| Typical CPU usage | Representative selected-source mix, input rate, enrichment/rule workload and dashboard use |
| Memory consumption | Collector, receiver/writer/API and UI contributions, queue behavior and sustained growth |
| Disk growth | Events, alerts, database sidecars, checkpoints/spool and bounded retention behavior |
| Event bursts | Fixture-driven bursts first; measure queue depth, latency, drops/incomplete reporting and return to steady state |
| Slow database or receiver | Backpressure, bounded work/memory, other-source responsiveness and visible failure/recovery limits |

Record prototype/build/environment, identities, selected sources, input conditions,
measurement method/duration, limitations and results. No CPU or memory budget or
acceptance threshold is invented here. Establish actual acceptance thresholds after
measuring the prototype, record the rationale and validate them before claiming
v0.1 resource acceptance. An arbitrary example frame/queue limit is not a product
CPU/memory budget. This requirement authorizes neither a benchmark run now nor
live connector stress/concurrent-subscriber experiments; use offline/simulated
workloads first and separately authorize any actual-source runtime validation.

## Completion checks and open decisions

The [release completion criteria](release-scope.md#v01-completion-criteria) must
include first-run and resource evidence:

- No confirmed selection: no subscription, security-event reader or payload sample.
- Recommended defaults are explained and editable; unverified fields/runtime are
  labeled honestly and unavailable/partial/unsupported are not conflated.
- Confirming a subset initializes only that subset; a selected source can fail
  while the rest and authorized history/configuration remain usable.
- Backend/collector enforcement rejects unauthorized or unconfirmed start requests;
  changing a checkbox/default or finding a new source cannot bypass confirmation.
- Overview is the landing page, the feed sorts severity then recency using an
  explicitly chosen clock, ordinary events stay in Activity, and each alert links
  its event/rule/condition. Technical details remain available behind authorization.
- Required benchmarks are recorded and acceptance thresholds are chosen from
  measured prototype results, not assumed budgets.

Still open: recommendation eligibility for partially usable sources; confirmation
record/access controls, startup/resume and edit/retry semantics; source scheduling/
supervision; final severity wording/mapping, recency clock and tie-break; actual
resource thresholds and benchmark protocol. Existing service-identity, root-only
authentication, event/IPC/database schema, timestamp, retention and recovery
decisions remain open in the [implementation-plan register](implementation/v0.1-implementation-plan.md#decision-register).
No extra event fields, wire messages, database tables or dependencies are approved
by this product document.
