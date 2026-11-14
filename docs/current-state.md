# HIDS current state and session handoff

Start here for ongoing work. Read the linked authority for the area being changed;
use chronological chat/evidence only when a decision or result needs tracing.
This summary does not override the owner, AGENTS.md or accepted decisions.

## Current checkpoint

**2026-11-14 first-build trial ready:** final Copilot loader review and four
closed-store/invalid-UTF-8 regressions found no product defect. Candidate `.15`
passed 198 Python/24 client checks, 13 HTTPS assertions, a fresh native build,
fresh/upgrade package acceptance and actual installed native owned-child → private
store → protected browser acceptance. Linux 2 is now normally package-installed;
its prior manual code/units are privately archived. Three new owned-child records
were retained, preserving the old three; M3/M4/policy are unchanged. All seven
source/viewer units are stopped, no grant remains, and choices are empty at
revision 8. The installer/checksum/instructions are on the Linux 2 desktop in
`HIDS First Build`. The owner approved committing/pushing this checkpoint to
`aidenjlee4321/HIDS_Project` on `main`; verify Git/remote state for the resulting
commit. Pause feature expansion for the owner's trial.
[Trial instructions](USER_TRIAL.md), [exact evidence and limitations](validation/first-build-ready.md).

**2026-11-14 dashboard session transport:** Copilot found no concrete defect in
the selected authentication/boundary code. New source-free actual HTTPS acceptance
passed all 13 assertions, including concurrent one-use redemption, deadlines,
logout/revocation, foreign-token and malformed-header refusal. The named workflow
now requires this phase and passed 194 Python/24 client checks plus frontend
validation. Independent preservation passed; collection stays stopped. Runtime
code and the verified `.14` installer are unchanged; no test-only rebuild was made.
[Evidence, source snapshot and limits](validation/dashboard-session-transport.md).

**2026-11-14 source stop ownership:** exact pending grants now cancel under the
runtime owner lock, including after failure; active Stop binds a PID descriptor to
live systemd invocation metadata. Foreign instances and unknown active components
remain untouched. Copilot reviewed the findings and both corrections. Final `.14`
passed 194 Python/24 client checks, actual source-free root/systemd ownership
acceptance and independent fresh-install/upgrade/downgrade acceptance, including
24 installed configuration SIGKILL/retry cases. Original state is intact and all
source/viewer units remain stopped.
[Latest artifact, evidence and limits](validation/source-control-safety.md),
[internal status compatibility](implementation/source-control-status.md).

**2026-11-14 TLS staging:** new keys now remain root-only through crypto validation;
normal backend access follows successful validation, and caught failures retain
private generations. Independent VM evidence found this failure-path hardening
opportunity after the first Copilot review; Copilot reviewed the correction too.
Final `.13` passed 179 Python/24 client checks, ten TLS fault/retry cases, existing
renewal negatives and independent fresh-install/upgrade/downgrade acceptance.
Original state is intact and all source/viewer units remain stopped.
[Latest installer, evidence and limits](validation/tls-staging-safety.md).

**2026-11-14 dashboard publication:** Copilot reviewed the defect and the applied
fix. The publisher now preserves the active selection/TLS binding with a durable
backup and atomic replacement. Final `.12` passed 177 Python/24 client checks,
fresh install/reinstall, `.10`→`.12` upgrade/downgrade refusal and 24 installed
process-kill/retry cases (12 dashboard, 12 source-config). The installed guide is
version-independent and provenance records the exact package version. All original
state is preserved and sources/viewer remain stopped.
[Latest artifact and scoped evidence](validation/dashboard-publication-safety.md).

**2026-11-14 launch cleanup:** verified fixes now stop the viewer on interrupted
preparation, cooperatively terminate/reap the ordinary browser and remove/check
temporary policy even after a failed load. Actual source-free systemd/Chromium
normal and SIGTERM cleanup passed; original HIDS state is intact and stopped.
Latest `.10` installer passed 173 Python/24 client checks and fresh-install,
reinstall, `.9`→`.10` upgrade and downgrade-refusal acceptance.
[Artifact, exact evidence and limits](validation/dashboard-cleanup-safety.md).

**2026-11-14 upgrade safety:** interrupted configuration replacement could reset
source identity on retry. The installer now durably backs up and atomically
replaces the config, and refuses ambiguous missing-config recovery from older
interruptions. Final `.9` passed 168 Python/24 client checks, actual `.7`→`.9`
upgrade, fresh install/reinstall, downgrade refusal and 12 installed SIGKILL/retry
cases across two isolated roots. Original state is preserved; sources/viewer remain
stopped. [Latest installer, hashes and limits](validation/installer-upgrade-crash-safety.md).

**2026-11-14 provider pivot:** owner requested Copilot after student-account
restrictions with Google. Copilot CLI 1.0.112 is installed in a separate restricted
Linux 2 account. Owner GitHub authorization completed and the approved private
VM credential file persisted; the actual restricted probe returned `Hi.` with
zero tool executions or file changes. Initial greeting auto routing offered only
`mai-code-1.1-flash` for this account. No API key or VM clipboard was required.
Source-review integration now passed synthetic and real selected-code review.
Copilot's first independently verified installer finding is fixed; new `.7`
artifact passed 164 Python/24 client checks and independent fresh-install,
reinstall, `.6`→`.7` upgrade and downgrade-refusal acceptance. Twelve reviewer
checks also passed; original HIDS state remains preserved and collection stopped.
[Build, hashes and exact evidence](validation/copilot-build-followup.md),
[review workflow](implementation/copilot-collaboration.md).
The earlier Gemini setup below is historical and does not remain the active path.

**2026-11-14 development collaboration:** owner requested external Gemini review.
The isolated Linux 2 CLI and source-packet bridge were installed; seven unit checks
and actual VM privilege/tool-policy checks passed. Google authorization never
completed; the obsolete login request is stopped. No live Gemini model
response has passed yet. [Setup, boundaries and next probe](implementation/gemini-collaboration.md).
This does not alter product scope or commit/push approval requirements.

**2026-11-13 protected history:** owner D-12c is accepted, implemented and verified.
The bounded HTTPS snapshot displayed 19 events and one informational finding; all
16 old events remain unevaluated. Synthetic gates and real browser/ground-truth
checks passed; independent preservation/cleanup passed. Collection stayed stopped.
All viewer activations are stopped; no CA, normal-profile trust change or Git
publication. [Exact evidence and limits](validation/m4-history-view-acceptance.md).

**2026-11-12 recovery resolved:** remaining Linux 2's guest UUID matches UTM;
the original pinned `.7` endpoint is reachable. All 357 M3 databases pass
quick_check; the v2 M4 store, 16-event v1 backup and key private reports survive.
No HIDS recreation is needed. [Independent inventory and corrected incident](validation/m4-first-rule-acceptance.md).

- Prior pushed checkpoint before the first-build publication: `d921a2bb4e74f245a60723011b36d9f614cde2ef`
  on `main`, GitHub `aidenjlee4321/HIDS_Project`: genuine per-user quota,
  rollback/recovery and privileged-helper fences. Publication was approved and
  remote main verified. Production code remains `f6c0259`; filesystem `bfb4592`,
  native `2c76070`, rotation `19e2bb1`, performance/soak `fc77ca5` precede it.
- Current uncommitted closeout: the quota scope now also drives actual Service
  control/data IPC under the real backend/reader identities. No success ACK after
  denied write; failure stays latched after quota release; restart preserves B,
  interrupts A and requires new authorization. Final eight-phase run passed,
  including 87 M3 + 40 workflow tests and fresh native/parser/crash checks.
  Independent inspection preserved policy, four source prefixes, all 355 original
  databases and 29 installed artifact hashes; private mount/loop cleanup passed.
  See [quota evidence](validation/m3-quota-validation.md).
- [Finite M3 closeout](implementation/m3-closeout.md) and the bounded
  [M4 fixture contract](implementation/m4-pilot-contract.md) were accepted after
  the owner's walkthrough. The isolated pilot is implemented: independently
  validate/store one synthetic event, evaluate a bounded immutable JSON rule and
  atomically save its explained demo alert. 23 pilot tests (including three actual
  SIGKILL recoveries), all 87 M3 Python regressions and the demo passed locally
  and as an ordinary Ubuntu user. [Evidence/commands](validation/m4-pilot-validation.md).
  No live hookup or final production schema/rule/severity approval is implied.
- Published read-only checkpoint: readable history honours WAL; unavailable history
  is not fabricated or opened immutable. Real private Service/root-client IPC and
  all 17 installed live phases passed. [Read-only evidence](validation/m3-readonly-status-validation.md).
- Published native checkpoint: eight successful variants and a rejected failed
  attempt with explicit USER/health background traffic; strict execution validation
  and EOE-only completion. Full live checkpoint passed all 17 phases, 79 M3 + 40
  workflow tests, 26 native groups, 128 native contract cases, 124 allocation cuts,
  11 API faults and 58 actual SIGKILL boundaries. [Native form evidence](validation/m3-native-workload-validation.md).
- Rotation acceptance already passed both real signals, source inode/byte
  preservation, unchanged reader/generation and three known EOE-backed executions,
  including a writer stall. Full live checkpoint passed 17 phases; final component
  checks passed 79 M3 + 40 workflow tests. [Rotation evidence](validation/m3-rotation-validation.md).
- The current plugin source decision supersedes file-tail generations/replay and
  associated retirement mechanics. Do not implement older unchecked backlog items
  as missing plugin behavior. Original Audit logs remain host-administered;
  indefinite preservation under external finite rotation is not guaranteed.
- The owner accepted [M3→M4 handoff architecture](implementation/m4-handoff-contract.md)
  for implementation/synthetic testing. The separate read-only adapter, durable
  destination and bounded worker now pass 19 new implementation cases; all 49 M4
  tests (23 pilot + 7 design + 19 adapter), 87 M3 regressions and demo passed on
  Ubuntu. Four actual worker starts under `hids-ingest` with read-only source and
  hidden production paths preserve late A after B, importing two explicitly
  unevaluated synthetic events with zero enabled rules/alerts.
  [Implementation evidence](validation/m4-handoff-implementation-validation.md).
  Those synthetic results remain scoped; later bounded real-data acceptance is
  recorded below. Original policy/history/install checks passed.
- The owner accepted the [production storage/bounded-trial packet](implementation/m4-production-review.md).
  Fixed-path root configuration, separate live marker/domains and a bounded real
  entry point now pass 53 M4 tests + 87 M3 regressions on Ubuntu. Production-shaped
  synthetic sandbox/negative controls passed before actual access. The first live
  trial then imported all 16 actual kernel executions exactly once, preserving
  metadata/scope: 16 explicitly unevaluated, zero rules/evaluations/alerts.
  [Live evidence](validation/m4-real-data-trial.md). Temporary Audit policy/config
  was restored; all 355 old databases remain plus one new M3 interval (356 total).
  Real M4 store remains private under `/var/lib/hids/m4/store`; the worker is
  stopped, root trial config removed and no M4 unit installed/enabled.
  This is a bounded import pass, not unattended monitoring or supported detection.
- Owner accepted the [first rule/migration packet](implementation/m4-first-rule-review.md).
  Implementation passed 86 M4 tests, 87 M3 regressions and demo on Ubuntu;
  isolated namespace migration/finding acceptance passed. Real migration and
  bounded three-execution trial returned passed/restoration verified: one
  informational finding and the original 16 events unevaluated. Subsequent
  independent verification passed: 357 healthy M3 databases, unchanged 29
  installed hashes/Audit policy/four log prefixes, and intact live/backup M4 history. [Observed evidence and limits](validation/m4-first-rule-acceptance.md).
- Extended v2 recovery/contention acceptance passed: 93 M4 tests, 87 M3
  regressions and demo on Ubuntu; four actual sandboxed worker SIGKILL boundaries,
  real SQLite writer-lock/page-full cases and pinned source WAL visibility.
  Synthetic late A/restart acceptance passed with two findings and 16 old events
  unevaluated. Independent real-state preservation passed; no new live collection.
  [Recovery evidence and exact limits](validation/m4-recovery-contention.md).
- Installed M3 Service/real peer IPC beside sandboxed M4 contention passed:
  16 synthetic events, destination-write overlap barrier, pinned source WAL reader,
  durable ACKs and complete recovery to 16 synthetic findings. Four-sample phase
  ACK medians were 1.789–2.179 ms; these are observations, not thresholds.
  Production database/policy hashes matched; guest-UUID fail-before-setup guard
  passed. [Exact scope/measurements](validation/m4-ipc-contention.md).
- Continuous bounded M4 scheduler measurement passed with actual installed M3 IPC:
  32.410 seconds, three ten-second windows, 16 synthetic events/findings and
  duplicate-free restart. Idle CPU was 0.056034 seconds over 10.009 seconds;
  initial idle state sizes/accounted writes stayed flat. Held-reader checkpoint
  advanced only 74/178 frames; after release private-fixture TRUNCATE completed
  and WAL reached zero. Original contention scope and independent preservation
  checks also passed. [Exact observations/limits](validation/m4-continuous-polling.md).
- Real M4 filesystem failure scope passed on a fenced 1.5 GiB private ext4 image:
  normal guards refused at critical space; real SQLITE_FULL at both import and
  finding transactions preserved progress/pending work; retry completed once.
  Read-only startup refused with EROFS and unchanged history. Namespace negative
  control, loop/mount cleanup and independent production preservation passed.
  [Exact scope/evidence](validation/m4-filesystem-failures.md).
- WAL/state admission scope found and fixed missing runtime backup accounting.
  M4 now uses one bounded private store/backup inventory for runtime/migration;
  shared M3 guard default iteration remains unchanged. 96 local M4 tests passed;
  Ubuntu passed 96 M4 + 87 M3 tests and demo; actual sandbox WAL/state pressure and all
  four crash boundaries passed, then real full/readonly regression passed.
  Independent real inventory stays normal at 196,608 bytes with all history and
  policy preserved. [Fix, measurements and limits](validation/m4-budget-admission.md).
- Actual two-binding sandbox failure/backoff/pagination/recovery passed with
  four synthetic events/findings, unchanged source-A bytes and complete repeat
  sweeps. The production bounded entry remains single-binding. Independent real
  history/install/unit checks passed. [Evidence](validation/m4-binding-isolation.md).
- [M4 bounded backend acceptance review](implementation/m4-acceptance-review.md)
  now reconciles the executed scopes and preserved release gates. Owner D-12a
  accepts explicit UID-0 authorization, including OS-authorized sudo, for each
  new session; group membership alone grants nothing.
  [Accepted eligibility](implementation/dashboard-access-eligibility-review.md);
  [accepted D-12b mechanism](implementation/dashboard-session-mechanism-review.md).
- D-12b synthetic-only pilot now passes 39 component cases and actual root/backend/
  ordinary Firefox acceptance, same-tab reauthorization, logout/revoke/restart and
  real 60-second grant/300-second idle expiry. The root-created socket retains
  0700/0600 permissions; backend is UID 994/zero effective capabilities and real
  data paths are hidden. Existing state/install/policy preservation and pilot
  stop/config-unit cleanup passed. No real-data route, persistent grant, default
  enablement or collection. [Evidence/failures/limits](validation/dashboard-session-pilot.md);
  [private build and workflow](../api/README.md).
- Use the verified workflow whenever applicable. Mac work remains limited to
  authorized project edits/private temporary outputs; ask before system/settings,
  software/credential changes and specific Git publication.
- Canonical repository: `/Users/aidenlee/Downloads/hids`; the chat workspace is a
  different directory. Verify branch, working tree and remote before Git mutations.
- M3 implements root-authorized current-tail Audit execution, separate native
  reader/backend identities, bounded reconstruction, independent validation,
  atomic SQLite/progress, interruption suppression, resource handling, health,
  proactive storage admission, separate event clocks and root rejection diagnostics.
- Previous product acceptance: 70 M3 Python tests, 25 native groups, 124 native
  boundaries, 124 allocation cuts, 11 API faults and 58 actual SIGKILL cases;
  installed live/runtime, load, storage, resource and health tests passed.
  Exact conditions and limits: [M3 evidence](../tests/integration/M3-README.md).
- Dashboard, supported live security rules, full packaging, broader workloads/native
  coverage, release thresholds and distribution/license approval remain unfinished.
  M4 began under explicit owner approval; workflow passes alone do not grant scope
  or close those product gates.

## Authority and workflow rules

1. Prioritize safety, then progress, then avoiding unnecessary interruptions.
2. Reversible implementation/testing and Linux 2 VM work are authorized.
3. Ask for specific commits/pushes, fundamental architecture/product decisions,
   breakage needing owner action or blockers unresolved with available access.
4. For this efficiency task, the owner approved Mac project edits in the canonical
   repository and private temporary build/snapshot/test outputs. Ask before Mac
   settings changes, software installation, credential configuration or other
   modifications outside that scope. VM authorization is broader.
5. Preserve C++ native collection/normalization, Python validation/SQLite ownership,
   protocol boundaries, least privileges, root-only human security-data access,
   local-first behavior, no automatic remediation and no evidence deletion.
6. Product installation/runtime must not change Audit/journald/PAM policy. Explicit
   lab live-policy tests are separate, opt-in and must restore their exact baseline.
7. Keep secrets, raw security data and private test logs outside Git. Do not paste
   credentials into documentation, reports, SSH options or command strings.

Full constraints: [AGENTS.md](../AGENTS.md). Scope: [ADR-007](decisions/007-initial-release-scope.md).
M3 authority: [specification/register](implementation/m3-linux-audit-spec.md).

## VM and next-run prerequisites

- UTM guest name Linux 2; Ubuntu 26.04 AArch64; SSH user `ivy`.
  Previously observed address `192.168.64.7` may change. Verify reachability and
  the existing pinned host key; do not disable host-key checks to get past failure.
- Password/other authentication stays in the existing authorized access channel,
  never in this file. The runner accepts interactive SSH/sudo authentication and
  neither installs keys nor changes Mac SSH configuration.
- Previous staging: `/home/ivy/hids-m3-runtime.6MmspJ2L`; matching pre-existing Audit
  headers are in its `headers/` directory. The runner verifies dependencies and
  creates a new complete source snapshot/staging directory for each VM invocation.
- Installed application `/usr/lib/hids`, state `/var/lib/hids/m3`, configuration
  `/etc/hids/m3.json`; resolve service accounts through NSS, not hardcoded IDs.
- The persistent VM-only lab activation budget was deliberately raised from
  256 to 512 for continuing acceptance, preserving all prior history. Exact old
  configuration: `/root/hids-workflow-budget.9sdud64k/config.json` (root-only).
  After the first import and rule trials, 357 SQLite files including control remain
  (all 355 previous files plus the two trial activations). The workflow restores the 512 baseline after each run. Check remaining capacity
  before further runs; never delete history to make room.
- Two source rotations left four Audit log files, highest suffix `.3`, under the
  original five-file ROTATE policy. Repeating the two-rotation experiment now
  correctly fails safe preflight. Do not weaken that guard or remove old logs.
- VM workflow requires M3/checker units already inactive and Audit already active.
  It never takes over an active collection session or reboots automatically.

## Normal work cycle

Use [the M3 workflow guide](m3-workflow.md). Run focused tests during iteration;
component tests for affected boundaries; one applicable checkpoint suite once code
settles. Re-run checks after fixes according to the affected scope. Native or
privilege-boundary changes require Ubuntu evidence; Mac passes cannot substitute.

Every run keeps a private report/log directory. Link results and limitations from
this summary; append detailed evidence only for meaningful new behavior or results.
Record the current task and next action before a handoff. Source/build hashes,
exit codes and cleanup checks establish reproducibility; a test count alone does not.

## Next product work

**Rotation guard resolved:** the reviewed lab helper now finds rotated originals
only within their original directory and still requires original inode numbers,
exact recorded prefixes/hashes and safe regular files. Twelve tests and repeated
actual privileged preservation checks passed. No logs were copied/deleted, no
baseline was rewritten and no logging configuration changed.

The first protected retained-history slice is complete under
[accepted D-12c](implementation/m4-history-view-review.md). It is a frozen snapshot,
not live monitoring. [Acceptance](validation/m4-history-view-acceptance.md) records
290 Python tests, 14 client tests, synthetic and real read-only service/browser
trials and independent cleanup. The original 16 events remain unevaluated; all 357
M3 databases, M4 history/backup, installed artifacts and Audit state are preserved.
Do not recreate state or re-evaluate old events. No viewer or collector is running.

Owner accepted [D-14a](implementation/first-run-control-review.md). The bounded
setup implementation now passes 376 Python checks (including 30 design-model),
19 client tests, actual config-writer crash/FULL/readonly and root-peer/M3-control
IPC tests, synthetic browser/root-terminal acceptance and the real empty-selection
trial. [Exact evidence/limits](validation/first-run-acceptance.md). The browser
stages choices; root CLI rechecks and confirms/starts/stops. Preferences survive;
collection does not automatically resume after restart. Stop is required before
editing held choices, and known unmanaged M3 or M2 services block confirmation.

Real saved preferences are empty at revision 2; both immutable revisions remain
under `/etc/hids/setup`, root:backend 0440. No active ownership/source exists.
All source/viewer/test processes are stopped and temporary activation removed;
independent preservation/cleanup passed. No actual native source was initialized
in this first-run trial: Audit is blocked under existing configuration, cn_proc
is runtime/identity-unverified, and journal control is not deployed/enabled.
Do not turn those gates green by changing OS logging or assigning new privileges.

Next prepare intended-account live process-adapter validation/deployment and
production access/certificate lifecycle, preserving the selected-source consent
policy. Actual Audit reader startup/shutdown under the new controller, when
already configured, remains a separately unexercised combination; the synthetic
IPC test used real M3 Service/Runtime with unit lifecycle/native presence stubs.
Broader source identity/live tests need their own reviewed scope. Existing source
approvals, event schemas and no-logging-change restriction remain in force.

Production access/certificate lifecycle and source-confirmation work still preserve
explicit selection before collection and honest monitoring-health/unavailable states. Existing D-12c/D-14a authority does not
approve a CA, normal-browser trust changes, automatic collection, broader event fields,
SSE/search/export, unattended deployment or release thresholds. Broader measurements
can proceed independently under their approved bounded scopes. The no-CA path
requires a new HOME/NSS and user-data directory; Firefox is optional and its
peer-only trust path failed. Do not silently substitute a CA.

M4 backend bounded evidence remains in the
[acceptance review](implementation/m4-acceptance-review.md). Retention, resource/
coverage evidence, broader rules, complete dashboard, packaging and release gates
remain open; D-12/D-13/D-15 are not wholly closed by this trial. Current changes are
uncommitted; specific commit/push approval remains required. Mac access remains
project/private-temp only. Use verified snapshots/private Ubuntu tools and focused
regressions; do not weaken storage guards or delete unrelated files to save space.

### Approved process pipeline (November 13)

Owner approved [C-01–04](implementation/process-live-pipeline-review.md). The new
C++→private Unix IPC→independent Python validation→separate SQLite process pipeline
is implemented and its bounded installed owned-child trial passed: three real
fork/exec/exit records, no invented activity time, ACK=false/delivery=true and a
clean stopped interval. [Evidence, provenance and limits](validation/process-pipeline-acceptance.md).
Root confirmation/start/stop, one-use grants, separate zero-capability identities,
old selection-catalog compatibility and no-grant restart refusal passed. All
services retain RestrictSUIDSGID; the root coordinator is reduced to CAP_CHOWN.

The VM interruption/restart did not repeat collection. The persisted successful
report was recovered, the new DB integrity/three rows rechecked, and all old
Audit/M3/M4 preservation checks passed again. Preferences are empty at revision 6;
all old revisions and 357 M3 databases remain. All process/M3 units are stopped.
Native payloads remain private on the VM. The source trial's original no-ACK and
unconfirmed IGNORE-completion limitations remain; no sustained reliability claim.

The focused failure/boot-directory checkpoint passed all 17 phases (83 Python,
native and 42 cross-language cases), followed by a stopped update and real backend
namespace/no-grant checks. See the final checkpoint in the evidence record.

Owner authorized continuation of [P-01–P-04](implementation/first-build-dashboard-review.md):
closed dashboard:read, frozen process/M4 presentation, explicit-root local leaf
lifecycle and local development packaging. Implement synthetic gates before actual
stored-data/browser/install acceptance. New source/rule meanings remain separate.
First installable Ubuntu build is the owner's priority, then reassessment before
extras. No commits/pushes are authorized for this checkpoint. Use the existing
workflow/test venv and strict console-verified SSH fingerprint.


### Combined dashboard retained-data checkpoint (November 13)

The approved P-01/P-02 frozen combined view now passed 146 Python tests, client
regressions and three frontend builds, then actual Linux 2 API/ordinary Chromium
acceptance over the existing three process and 19 M4 records. The informational
finding still links to its triggering event; 16 old events remain unevaluated.
No collection was repeated. All old preservation checks and process/M4 DB/WAL
byte comparisons passed after cleanup. [Exact reports and limits](validation/combined-dashboard-acceptance.md).
P-03/P-04 explicit launch lifecycle and development packaging remain in progress;
the first installable build is not complete yet. No commit/push authority follows.


### First installable development checkpoint (November 13 local / November 14 UTC)

P-01–P-04 bounded development acceptance is complete. The delivered Ubuntu 26.04
AArch64 artifact is `hids-development_0.1.0~dev20261113.6_arm64.deb`, 3,055,096 bytes,
SHA-256 `79f55d29fa022a3f8450ca51509abff67af6b148636de2e35ac119602be9db95`.
Verified temporary Mac copy: `/private/tmp/hids-first-build/` (not installed on Mac).
[Final source/reports, superseded attempts and limits](validation/combined-dashboard-acceptance.md).
[Install/operator guide](../packaging/DEVELOPMENT.md).

Final named scope passed 161 Python and 24 client tests, TypeScript and three
frontend builds. Actual retained-data browser/API, explicit root/private-pipe
launch, valid/near-expired/expired leaf handling, reproducible 301-file external
browser preparation and independent copy-on-write Ubuntu installation/restart/
version-upgrade/downgrade-refusal checks passed. Final payload inspection excludes
VM identities, private keys, runtime data and lab documentation. This is not a
fresh full-VM boot test or full v0.1 release. Fresh installation provides process
Activity, not a supported process security rule. Existing M4 history is optional;
no imports/evaluations or new source/rule meanings were added.

Linux 2's old installation/history remains preserved and source units stopped;
choices remain empty at revision 6, process history three events, M4 19 events/
one informational finding/16 old unevaluated events. The standard Ubuntu NSS
certificate-tool package was added without library upgrades/removals; the exact
external browser was recreated at `/opt/hids-browser`. No global trust or Mac
system setting changed. The old manual HIDS installation was not silently adopted
by the new package. No commits/pushes were made.

**Next owner stopping point: reassess project scope before extras.** Do not infer
new detector/enrichment/source approvals or Git authority from this checkpoint.
Use `scripts/combined_dashboard_workflow.py` for the named synthetic scope and
`scripts/build_development_deb.py` for verified offline artifacts; keep native
reports and real payloads private on the VM. Post-build handoff documentation may
be newer than the immutable artifact source snapshot; runtime inputs remain fixed.
