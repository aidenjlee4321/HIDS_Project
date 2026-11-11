# HIDS current state and session handoff

Start here for ongoing work. Read the linked authority for the area being changed;
use chronological chat/evidence only when a decision or result needs tracing.
This summary does not override the owner, AGENTS.md or accepted decisions.

## Current checkpoint

- Latest pushed product checkpoint: `ff9049801ed536d0c9f276e2ef87c137442d55c9`
  on `main`, GitHub `aidenjlee4321/HIDS_Project`.
- Latest pushed workflow checkpoint: `febf25fa810c342c2c4f08ac2a76ca8f16a6f9b0` on `main`.
- Completed checkpoint approved for commit/push to `main`: controlled M3 performance
  review, accounting optimization and longer-workload acceptance.
  The owner requests the new workflow whenever applicable going forward.
  A guarded accounting optimization passed component and paired performance tests;
  the two-hour varied load and full live checkpoint passed.
  Two independent detached jobs verified shared-cache reuse; final restoration
  and installed-file checks passed. Focused suites: 71 M3 + 39 workflow tests.
  Do not treat dispatch/running as a pass or deploy other work over an active test.
  [Current evidence](validation/m3-performance-validation.md) records completed
  comparisons, the 7200.018-second workload and remaining release gates.
  Check Git history/remote for the approved checkpoint identifier and publication status.
  Next project work: rotation/source-preservation testing under existing approvals.
  Mac work remains limited to authorized project edits and private temporary outputs;
  ask before Mac system/settings/software/credential changes and specific Git publication.
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
- Dashboard, detection rules, full packaging, broader workloads/native coverage,
  release thresholds and distribution/license approval remain unfinished. Passing
  this tooling workflow does not close those product gates or begin M4 by itself.

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
- Before tooling acceptance, 127 SQLite files including control were retained.
  The VM-only lab activation budget was deliberately raised from 128 to 256; the
  original is protected at `/root/hids-workflow-budget.8035odje/config.json`.
  After the performance/soak checkpoint, 244 SQLite files including control are retained.
  A full checkpoint reserves 30 new intervals: choose a deliberate larger VM-only
  lab activation budget for future full runs, preserving all retained history.
  The runner restores that new 256-budget baseline after each run. Check interval capacity
  before additional runs. Preserve all history; increasing a lab budget is a
  deliberate VM setting, not automatic deletion or silent capacity repair.
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

## Next product work after tooling acceptance

Review the remaining M3 gates against the specification and measured evidence:
broader representative workloads/native forms, controlled performance comparison,
remaining source-retention/rotation cases, release thresholds and reproducible
packaging/distribution. Preserve owner approvals; do not reopen settled decisions
because an older backlog checkbox is still empty.
