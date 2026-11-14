# First-run consent and source-control review — D-14a

**Status: accepted by the owner in the continuation following the explicit
first-run policy question. Implementation and acceptance results remain separate.**
This packet prepares the next feature after the accepted
[D-12c stored-history view](../validation/m4-history-view-acceptance.md).
It preserves the accepted [first-run product direction](../product-experience.md)
and [D-14 decision register](v0.1-implementation-plan.md#decision-register).
The synthetic model below is design evidence, not a new source, API or permission.

## Recommended decision

For the first build, **remember confirmed source choices, require a fresh root/sudo
activation after restart, and keep privileged confirmation/start/stop in a narrow
root CLI**. The ordinary authorized browser may inspect preflight and stage a draft;
it cannot save authoritative choices or start/stop collectors. Require confirmed
stop before editing an active selection in this first slice. Hot edits and
unattended boot/resume remain later work.

These are user-visible consent/control decisions. General VM access and permission
to implement reversible details do not settle whether saved preferences authorize
future collection or whether a browser bearer can control privileged processes.
One approval of this packet covers the bounded implementation/trial below; no
commit, push, CA, normal-profile trust change or Mac system change follows.

| Question | Recommended first-build policy | Tradeoff |
|---|---|---|
| What survives a restart? | Confirmed choices survive; process authority/receipts do not. Show activation required and obtain a fresh explicit UID-0 action | Deliberate restart step; no surprise resumed collection |
| Who changes collection? | Browser stages a draft only. Root CLI independently checks/reviews it, saves the selection and invokes fixed HIDS controls | Extra terminal confirmation for this first build; no HTTP start/stop capability |
| Editing active choices | Confirmed stop of held/unconfirmed source instances before changing the configuration | Hot edits deferred; prevents mixing old/new consent during partial shutdown |
| Initialization failure | Report each selected source separately; keep other successfully initialized confirmed sources operating | Failure is visible; no silent privilege, source or logging fallback |
| Refresh/recovery | Reassessment never selects/starts a new source. Failed initialization has no automatic retry; fresh root action is required | No unattended recovery promise in this slice |

The accepted minimal-stack, C++ collection/Python validation/SQLite ownership,
root-only human access, no correlation/remediation/confidence labels and existing
logging restrictions remain unchanged. Root-owned application JSON configuration
is separate from Python-owned event SQLite. M4 rule/import activation is not implied
by a source selection; the approved rule plan/defaults remain unchanged.

## Repository evidence and current VM metadata

Existing production controls already provide useful building blocks:

- `m3_service.Service.control` verifies the root-only control boundary and accepts
  bounded explicit activate/deactivate requests. `m3_runtime.Runtime.activate`
  creates a fresh scoped interval, refuses an already ended activation and applies
  storage/admission limits. Reuse these boundaries; do not replace their leases,
  generation handling, suppression, capacity checks or interruption semantics.
- M2 also has root peer controls, but its component/lifecycle evidence is separate
  from M3. The process connector has offline production code and historical
  owner-reported ordinary-user research, not current intended-account acceptance.
- D-12c is a finite `history:read` surface. It does not authorize source metadata,
  drafts, configuration writes, source start/stop, automatic refresh or new sources.
- The product direction requires metadata-only preflight, explicit confirmation,
  independent source status and continued authorized history access. D-14 explicitly
  leaves confirmation storage, retry and restart policy open.

A new **lab metadata inventory** checked Linux 2's pinned UUID and current kernel
`7.0.0-43-generic`, AArch64. Private evidence:
`/var/tmp/hids-first-run-preflight.qwfhwl2o/report.json` and
`installed-metadata.json`. Audit is active; all four M3 service/socket/checker/timer
units are inactive. M2 ingest/journal units are not installed. Service identities
exist: Audit reader UID 993/GID 970, backend 994/971, journal reader 997/973; no
supplementary group membership was observed for these accounts. These numeric IDs
are observations, not constants to copy into the product.

Kernel configuration reports `CONFIG_CONNECTOR=y` and `CONFIG_PROC_EVENTS=y`;
connector headers and journal directories exist. These facts do not prove a live
subscription, field availability, journal-read access or intended-account operation.
No event sampling, connector subscription, collector initialization, permission/group
change or source repair was performed. The independent lab preservation check
reads/hashes previously authorized Audit source-prefix bytes and HIDS artifacts;
that check is separate from source preflight and must **not** be called by product
first-run discovery. No payload examples were retained/exposed.

The two specifically checked HIDS plugin config paths are absent; the installed
manifest confirms all 29 original artifacts, including `hids-audit-plugin`,
`hids-audit-launcher` and `hids-m3-health`, still match. An initial guessed
`hids-audit-reader` pathname was absent; it is not the installed plugin's name and
is not evidence of missing HIDS software. Existing history/backups/policy match
the original baseline; no recreation or deletion is needed.

| Recognized candidate | Evidence boundary | First-run treatment now |
|---|---|---|
| Audit execution | M3 bounded pipeline accepted/tested; service stopped and checked HIDS plugin configuration absent | Report blocked/not configured for a normal activation; never enable auditd/plugin/rules to make a green result |
| Process lifecycle | Existing production adapter offline-tested; current kernel/header metadata present | Runtime/intended identity unverified. No automatic recommendation or LISTEN probe |
| Journal authentication | M2 components/lifecycle exist; service units not installed; intended-account payload access not established here | Explain installation/access not established. No journal sample, package install or group change |

A source is preflight-eligible only when its recognized adapter/identity/policy and
non-collecting access checks have no known blocking condition. That still means
**runtime unproven**. Unknown, blocked, unsupported and known clean failure remain
distinct. Candidate field descriptions come from labeled documentation/prior
scoped evidence, never from unconfirmed sample reads. No ranking/coverage score.

## Bounded implementation contract proposed for approval

1. Add a separate setup trial entry using the accepted verified direct-leaf HTTPS,
   isolated ordinary-user HOME/NSS/user-data and root-per-session mechanism. Retain
   TLS verification/sandbox, existing expiry/capacity, Host/Origin/CSRF/body/header
   limits and private evidence. Port 18765 remains exclusive/manual; no CA, HTTP
   fallback, installed normal-browser trust or enabled boot service. Reuse existing
   pinned dependencies and service accounts; do not grant a new source identity.
2. A one-shot trusted root assessor uses a fixed recognized-source registry, NSS,
   file/config metadata and non-collecting access checks. It must not instantiate
   collectors/writer-opening stores, connect activation sockets as a usability
   probe, read event payloads, gather per-process context, subscribe, install,
   elevate an adapter or modify logging. Root/role accessibility is not usability.
   Produce a protected bounded snapshot, not an unauthenticated host endpoint.
3. Proposed setup fields: format/version, random assessment ID, assessment time
   (preparation time), confirmed selection/revision, recognized source IDs, static
   labels, implementation state, preflight state, scoped check/reason codes and
   documented limitations/provenance. No event values, raw config, user-supplied
   paths, process identifiers/context, exports or automatic health verdict. These
   are setup fields, not a global ECS/event schema.
4. Use a separate root-issued `setup:draft` scope. `history:read`/`pilot:read`
   cannot use setup routes; setup scope cannot read history or control sources.
   Proposed routes are `GET /v0/setup` and `POST /v0/setup/draft`. The latter accepts
   only current assessment ID, expected confirmed revision and a unique subset of
   the fixed registry. Browser drafts are volatile; max one/session, four/process,
   60-second lifetime, bounded 1 KiB request. Replace/logout/revoke/restart discards
   drafts. Return an opaque one-use review reference, not collection authority.
   Bound snapshot/response at 64 KiB, diagnostic strings at 1 KiB and registry at
   the three recognized candidates. Render text; no arbitrary source/plugin loader.
5. A narrow root/sudo CLI obtains the draft over root-only Unix control, displays
   exact choices/consequences in a private terminal, independently rechecks current
   facts, and rejects changed assessment/config revisions. Its fixed operations
   are review, confirm/start and stop. No user-supplied unit/path/command/SQL.
   Read review references through private terminal input, not argv/environment or
   logs. The reference alone and a browser bearer confer no root authority.
6. Persist only a closed root-owned application selection under a fixed private
   `/etc/hids/setup` directory, root:backend 0750 with regular 0440 records. Proposed
   record: version, revision, sorted recognized selected IDs and registry hash;
   max 4 KiB. Retain earlier confirmed revisions, up to 16 in this bounded trial;
   refuse further writes instead of automatic deletion. Write/flush atomically,
   reconcile uncertain outcomes, and never activate after unconfirmed persistence.
   No migration or write to M3/M4 event databases. No activation receipt/runtime
   permission in the persisted preferences. Exact names are a versioned trial
   configuration contract, not global schema decisions.
7. Confirmation and initialization remain separate transitions even when one
   explicit root command performs both. Consume a bounded one-use activation
   receipt before initialization; bind current process epoch, selection/config
   revision and fresh assessment. Empty selection invokes nothing and reports
   not collecting. Invoke only an eligible selected **implemented** fixed adapter;
   leave cn_proc/journal disabled until their own live/identity gates are met.
   Reuse existing M3 root controls. No hidden historical M4 import or rule enablement.
8. Preserve per-source initialization failure/unconfirmed cleanup separately from
   successful initialization. Initialization alone is not delivery; delivery needs
   current source/generation evidence. Stop affects HIDS instances, never auditd/
   journald/PAM or host logging rules. Unconfirmed stop stays visible and prevents
   conflicting configuration/activation. Refuse a trial with an existing unmanaged
   active collector; never take it over or stop it to clear a preflight failure.
   Stop only the exact source/activation owned by the confirmed operation.
   Drafts/reassessment/UI logout do not
   start, stop or revoke an independently confirmed active collection interval.
   After a process/boot restart, retained choices need fresh root activation.
9. The setup display is a labeled snapshot. Root reassessment/review produces a
   new snapshot/session; do not promise live health/SSE or a hot-edit workflow.
   Authorized history remains independently available through its existing entry;
   switching trial modes at the shared port requires explicit stop/start. The
   production access/renewal/lifecycle UX remains separate work.

## Design evidence and execution gates

`tests/unit/test_first_run_design.py` contains only an in-memory proposal model,
synthetic source initializers and 30 invariant cases. It exercises saved choice vs
activation, empty selection, root-only simulated actions, stale revisions/assessment,
forged/expired/replayed receipts, restart invalidation, per-source clean/uncertain
failure, independent delivery proof, confirmed stop, active-edit rejection and no
automatic retry/selection expansion. It opens no source, socket, file or database
and is not imported by the product. A passing model does not prove Linux peer
credentials, actual source isolation, cleanup, atomic filesystem writes or HTTP.

After approval, implement and test the missing actual pieces in this order:

1. Closed registry/snapshot/config validators, root durable selection and crash/
   disk/permission failure behavior using synthetic/private namespaces.
2. Root Unix control/CLI, ordinary-user denial, stale/replay checks and fixed adapter
   orchestration; synthetic partial failures and confirmed cleanup first.
3. Setup HTTP scope/draft/UI with full boundary, text, expiry and late-response
   tests, reusing the current browser/TLS stack. Existing history remains a regression.
4. Linux 2 metadata/empty/blocked-source trial under a ten-minute supervisor, all
   collectors stopped initially, no OS logging changes. Test actual source starts
   only if already eligible under unchanged policy and covered by its accepted
   adapter contract; otherwise report the missing prerequisite and preserve it.
   Do not manufacture a pass by adding Audit configuration or treating a mock as live.
5. Recheck original production preservation, stop/revoke/remove trial activation and
   retain private evidence. Record exact working behavior and remaining source gates.

No production setup endpoint, source-selection file, new service, draft/control
scope, source activation or certificate change has been created by this review.
The owner decision is the recommended consent/control policy and bounded scope,
not another approval for routine VM tools or reversible implementation details.


## Executed review evidence

All 30 synthetic model cases passed on Ubuntu and macOS. The verified Ubuntu
snapshot/report and current lab metadata/preservation boundaries are recorded in
[design validation](../validation/first-run-design-validation.md). The private
`scope-notes.json` clarifies that independent lab prefix hashing is separate from
metadata-only source assessment. No production setup code or source activation
was implemented. The next action is the owner's consent/control decision above.


## Implemented bounded outcome

Following the owner's approval, the setup registry/snapshot, root immutable
preferences, scoped volatile drafts, root terminal coordinator and setup UI were
implemented and passed the gates recorded in
[first-run acceptance](../validation/first-run-acceptance.md). This supersedes the
historical proposal-only statements above for that exact scope. The current real
trial confirms empty choices only; it does not prove a new native source works.
A collection-runtime restart needs fresh root activation; restarting the independent
viewer invalidates its grants/drafts without revoking another confirmed interval.
The reviewed rotation guard now preserves original inode/prefix requirements across
renamed files; no source copying or baseline relaxation occurred.
